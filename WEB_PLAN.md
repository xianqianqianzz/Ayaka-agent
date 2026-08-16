# 神里绫华 Agent — Web 方案 v2（重新设计）

> 本文档替代初版 Web 方案（旧版可从 git 历史回溯）。
> 初版的骨架——网关为中心、能力路由、分期推进、FastAPI + 纯 SPA——经 P0/P1 验证有效，**全部保留**；
> 本版在其基础上修正数据归属、把网关从「转发代理」升级为「适配器网关」、新增任务系统与人格层，并补齐工程化地基。

---

## 0. 现状盘点（代码事实）

| 模块 | 状态 | 缺口 |
|---|---|---|
| 脚手架（frontend / backend / deploy） | ✅ 已上云跑通 | Redis 部署了但闲置 |
| 认证（注册 / 登录 / JWT） | ✅ | 单长 token 自用够用；CORS 全开，上线前需收紧 |
| Provider / Model CRUD + Key 加密存储 | ✅ | **全局共享，无用户隔离**，与 BYOK、多用户预留矛盾 |
| 远程模型拉取 + 能力关键词推断 | ✅ | 推断粗糙（保留人工改能力即可，不追求自动完美） |
| `/chat/completions` SSE 流式转发 | ✅ | 只通 chat 一种能力；无计量；无会话持久化 |
| 前端 | ✅ 单页可管模型 + 试聊 | 无应用外壳与页面结构；未引入组件库与请求层 |
| 数据库 | `create_all` 启动建表 | **无 Alembic**，schema 一变就得清库，必须先补 |

结论：P0/P1 的验证目标达成，证明了「网关直通」可行。P2 之前先做一轮**地基修正**，否则后面每个阶段都要为隔离和迁移还债。

---

## 1. 定位与心智模型

**一句话**：一个平台跑通「训练 → 管理/编排 → 应用」全链路，绫华人格贯穿始终。

```
                    ┌──────────── 上游 · 实验室 ────────────┐
                    │  LLM 复现 / 文生图 / 文生视频 / 语音    │
                    │  （学习性质，产出注册回网关）            │
                    └───────────────┬───────────────────────┘
                                    │ 产物注册
┌──────────── 下游 · 应用 ──────────│───────┐        ┌────── 中游 · harness ──────┐
│  对话 / TTS / 生图 / 生视频 /     ▼       │        │  模型资产管理（registry）   │
│  Vibe Coding                     │        │        │  评估（evals）              │
│  统一按「能力」调用 ─────────────┼────────┼───────▶│  工作流编排（orchestration）│
└──────────────────────────────────┼────────┘        └─────────────┬──────────────┘
                                   ▼                               │ 消费
                        ╔═══════════════════╗                      │
                        ║   模型网关（枢纽） ║◀─────────────────────┘
                        ║  适配器 · 能力路由 ║
                        ║  计量 · 降级       ║
                        ╚═══════════════════╝
```

- **一个枢纽**：模型网关。下游不直连各家 API，上游产物注册进来即可被无差别调用。
- **三层域**：下游应用是用户摸得到的界面；中游 harness 是平台内核（资产管理 + 网关 + 评估 + 编排）；上游实验室是学习性质的训练模块。
- **一条主线（绫华）**：绫华不只是配色。她是平台内置的默认人格（persona），未来上游语音训练（SoVITS）为她配专属声音，桌面桌宠是她未来的实体形态。视觉主题、角色人格、语音、桌宠共用同一条角色线。

---

## 2. 总体架构

```
用户浏览器（SPA）
   │ HTTPS（买域名后；现阶段 HTTP + IP/端口）
   ▼
Nginx（frontend 容器）
   ├── /            → 静态前端（Vite 产物）
   ├── /api/*       → backend:8000（FastAPI）
   └── /artifacts/* → 生成产物（共享 volume，只读）
                        │
   backend ─────────────┼──────────────┬───────────────┐
      │                 │              │               │
  PostgreSQL         Redis          本地磁盘          各厂商 API
  业务表+计量        限流/缓存      data/artifacts/   （经适配器调用）
                                   （jobs 产物）
```

**两条关键链路**：

1. **同步链路（对话）**：前端 → `/chat/completions` → 网关解析模型 → 适配器 → 厂商 SSE → 逐 token 透传，同时落 `usage_logs`。
2. **异步链路（生成）**：前端 → `POST /generate/{image|tts|video}` → 写 `jobs` 表立即返回 job id → 进程内执行器调适配器跑任务 → 产物落盘 → 前端轮询 `GET /jobs/{id}` 拿结果 URL。

---

## 3. 核心抽象

### 3.1 Provider / Model / Capability（修正：归属用户）

- `Provider`：模型来源 + 凭证。`user_id` 归属个人（BYOK 天然 per-user）；`user_id = NULL` 预留为「平台内置」，本期不实现。
- `Model`：挂在 Provider 下，带 `capability`（`text-chat / embedding / tts / text-to-image / text-to-video / asr`）。新增 `enabled`（上下架）与 `priority`（同能力多模型时的选择顺序），`params`（JSONB，存默认 temperature 等模型级参数）。
- **能力路由**：下游声明「我要 tts」，网关在「enabled + capability 匹配」的模型里按 priority 选；也可显式指定模型名绕过路由。

### 3.2 适配器（新增：网关的心脏）

现状是 OpenAI 直通代理，非 OpenAI 兼容的厂商（生图 / 语音 / 视频大多如此）进不来。重新设计为适配器层：

```python
class ProviderAdapter(Protocol):
    async def list_models(self, provider) -> list[str]: ...
    async def chat(self, model, payload, stream) -> ...: ...      # text-chat
    async def generate_image(self, model, params) -> JobResult: ...
    async def tts(self, model, params) -> JobResult: ...
    # 未实现的能力 = 该 Provider 不支持，注册模型时校验拦截
```

- `openai / deepseek / ollama / custom / self-hosted` 全部映射到同一个 `OpenAICompatibleAdapter`（现状代码即其雏形）。
- 新厂商 = 新增一个 Adapter 文件，不动路由与应用层。接入顺序按下游需要：先 1 家生图 + 1 家 TTS 打通，不贪多。
- 上游训练产物 = `self-hosted` Provider（本地 vLLM / SoVITS 推理服务），天然复用适配器。

### 3.3 Job 任务系统（新增）

生成类能力（慢、贵、可能分钟级）统一生命周期：

```
pending → running → succeeded / failed
```

- `jobs` 表：类型、模型、入参（JSONB）、状态、产物 URL、错误信息、耗时。
- **执行器分两期**：本期用 FastAPI 进程内 asyncio 执行器（单机自用足够）；并发或长任务出现后再迁 Redis 队列（arq），**API 不变，前端无感**。
- 所有生成应用（studio）与未来的工作流节点共用这一套。

### 3.4 Persona 人格层（新增：绫华是一等资源）

- `personas` 表：`name / system_prompt / avatar / theme_key / voice_model_id（未来挂 SoVITS 产物）/ is_builtin`。
- 内置默认人格「神里绫华」（迁移脚本写入，人设参考 PLAN.md：白鹭公主、大和抚子、第一人称「わたくし」）。
- 对话应用创建会话时绑定 persona（系统提示词注入）；用户可克隆修改，做自定义角色。
- 价值闭环：上游语音训练的**第一个落地目标**就是给绫华 persona 配上专属 TTS 声音——上游成果直接可被下游感知。

### 3.5 UsageLog 计量（新增：评估与计费的地基）

每次经网关的调用落一条 `usage_logs`：用户、模型、能力、token 数、延迟、成败。成本极低，现在就做——它是中游「评估」、dashboard 用量展示、以及未来计费（如果做）的共同数据源。

---

## 4. 后端设计

### 4.1 模块划分（单体，按域分包）

```
app/
├── core/            config / db / security（已有）+ logging
├── models/          SQLAlchemy 表（见 4.3）
├── schemas/         Pydantic 契约
├── services/        领域逻辑（gateway 路由、job 执行器、persona 注入）
│   └── adapters/    Provider 适配器（openai_compatible.py 等）
├── api/             路由层：auth / gateway / chat / generation / personas / usage
└── main.py
```

### 4.2 模块清单

| 模块 | 内容 | 状态 |
|---|---|---|
| `auth` | 注册 / 登录 / JWT | ✅ 已有 |
| `gateway` | Provider / Model CRUD、模型拉取、能力路由、统一推理、计量 | ✅ 雏形，待加固 |
| `chat` | 会话 / 消息持久化、persona 注入 | P2 新增 |
| `generation` | jobs、image / tts / video 适配执行 | P3 新增 |
| `personas` | 人格 CRUD + 内置绫华 | P2 新增 |
| `usage` | 计量查询 / dashboard 汇总 | P2 新增 |
| `agent` | Vibe Coding 运行时 | P4 |
| `evals` | 题集、跑分、对比 | P5 |
| `workflow` | 编排引擎 | P6 |
| `training` | 训练任务管理 | P7 |

### 4.3 数据模型（目标 schema）

```sql
users(id, username, hashed_password, created_at)

providers(id, user_id → users NULL,  -- NULL 预留=平台内置
          name, kind, base_url, api_key_enc, created_at)
models(id, provider_id → providers,
       name, display_name, capability, enabled, priority, params JSONB, created_at)

personas(id, user_id NULL,  -- NULL=内置（绫华）
         name, system_prompt, avatar, theme_key, voice_model_id NULL, is_builtin, created_at)

conversations(id, user_id, persona_id NULL, model_id, title, created_at, updated_at)
messages(id, conversation_id, role, content, model_id NULL, token_count NULL, created_at)

jobs(id, user_id, type, model_id, input JSONB, status,
     result JSONB NULL, error NULL, created_at, finished_at NULL)

usage_logs(id, user_id, model_id, capability,
           prompt_tokens, completion_tokens, latency_ms, status, created_at)

-- 后续阶段：workflows / workflow_runs / evals / eval_runs / trainings / datasets
```

所有权说明：Model 经 Provider 传递归属用户，自身不冗余 `user_id`；会话 / 任务 / 计量直接挂用户。

### 4.4 API 一览（前缀 `/api/v1`）

| 分组 | 端点 | 状态 |
|---|---|---|
| 认证 | `POST /auth/register` `POST /auth/login` `GET /auth/me` | ✅ |
| 网关管理 | `GET/POST/PUT/DELETE /providers`、`GET /providers/{id}/models`（拉远程） | ✅ 待加隔离 |
| 网关管理 | `GET/POST/PUT/DELETE /models`（+enabled/priority） | ✅ 待扩展 |
| 统一推理 | `POST /chat/completions`（OpenAI 兼容 + SSE，保持生态兼容：任何 OpenAI 客户端都能直连本网关） | ✅ |
| 对话 | `GET/POST /conversations`、`GET/POST /conversations/{id}/messages`、`DELETE` | P2 |
| 生成 | `POST /generate/{image or tts or video}` → job；`GET /jobs`、`GET /jobs/{id}` | P3 |
| 产物 | `GET /artifacts/...`（nginx 直出） | P3 |
| 人格 | `GET/POST/PUT/DELETE /personas` | P2 |
| 用量 | `GET /usage/summary` | P2 |
| 后续 | `/evals`、`/workflows`、`/trainings` | P5–P7 |

### 4.5 工程化地基（P2 必须先做）

1. **Alembic**：废弃 `create_all`，首版 migration = 当前 schema + `user_id` 等修正列。此后所有表结构变更走迁移。
2. **Redis 启用**：登录与网关调用的限流；会话缓存。队列等 P3 之后再说。
3. **CORS 收紧**：同源反代后只允许自身域名 / IP。
4. **错误约定**：统一 `{detail: string}` 业务错误 + HTTP 状态码，前端 `api()` 已按此解析，保持。
5. **日志**：`logging` 统一格式，网关调用记 model / latency / status（与 usage_logs 互补：日志排障，计量统计）。

---

## 5. 前端设计

### 5.1 应用外壳与页面地图

从「单页大杂烩」重构为「侧边栏外壳 + 页面」：

```
/login        登录 / 注册（已有，换主题）
/             Dashboard：应用入口、用量概览、最近任务
/chat         对话（旗舰）：左会话列表 / 右流式对话，顶栏选模型与 persona
/studio       生成工作室：图像 / 语音 / 视频工作台 + 任务历史墙
/models       模型资产：Provider 与 Model 管理（现页面迁入并升级）
/settings     个人设置
后续          /workflows（编排画布）、/lab（训练）、/admin
```

落地页不做——自用阶段登录页即门面；将来买域名对外开放时再补。

### 5.2 设计系统（绫华主题）

- 引入 **shadcn/ui + lucide 图标**，主题 token 沿用并扩展现有 `ayaka-ice / ayaka-blue / ayaka-deep`：冰蓝主色 + 和风留白 + 衬线标题字体；暗色模式随 shadcn 主题机制预留。
- 原则：工具型页面（models / studio）保持高密度、克制装饰；角色氛围集中在 chat 与 dashboard（头像、问候语、和风云纹点缀）。
- 圆角 ≤ 8px，不用渐变卡片堆砌。

### 5.3 契约与状态

- **类型契约**：FastAPI 的 `/openapi.json` → `openapi-typescript` 生成 TS 类型，构建期校验，前后端不脱节。
- **请求层**：现有 `api()` 封装保留；服务端状态上 **TanStack Query**，会话内 UI 状态用 **Zustand**。
- **SSE**：POST + 鉴权头走不了 EventSource，用 fetch `ReadableStream` 手动解析（现 ChatBox 已是此模式，提炼为共用 hook）。

---

## 6. 中游 harness 概念澄清（补领域知识）

进入中游前，先把四个概念分清（它们常被混为一谈）：

| 概念 | 回答的问题 | 在本平台的载体 |
|---|---|---|
| 模型资产管理（registry） | 我有哪些模型？什么能力？可用吗？ | Provider / Model 表 + enabled / priority + 远程模型拉取 |
| 推理网关（gateway） | 调用怎么统一、怎么计量、失败怎么办？ | 适配器 + 能力路由 + usage_logs |
| 评估（evals） | 哪个模型擅长什么？质量如何？ | P5：固定题集跑分 + 同题多模型对比，结果反哺 priority |
| 工作流编排（orchestration） | 多次调用怎么组合成流程？ | P6：节点 = 一次能力调用 / 工具，边 = 数据流 |

关系：**harness = 资产管理 + 网关 + 评估**；编排是网关的消费者（节点调用全部走能力路由），不是网关的一部分。上游训练产物经注册进入资产管理，随即被评估、被编排、被应用消费——这就是「跑通上下游」的完整语义。

---

## 7. 三层落地映射 + 绫华主线

| 层 | 落地 | 阶段 |
|---|---|---|
| 下游 | Dashboard / 对话 / 生成工作室 / Vibe Coding | P2–P4 |
| 中游 | 网关（✅）→ 评估 → 工作流 | P5–P6 |
| 上游 | 训练任务 → 产物注册进网关（首个目标：SoVITS 绫华语音） | P7 |

**绫华主线**：P2 内置 persona（人格）→ P3 TTS 先用通用声音 → P7 SoVITS 产出专属声音挂到 persona → P8 桌面桌宠（PLAN.md，接同一套 API，成为人格的实体形态）。配色主题全程贯穿所有页面。

---

## 8. 分期路线图

> 节奏约定（沿用 AGENTS.md）：每个阶段完成后，先完成云服务器同步与测试，再进入下一阶段。

| 阶段 | 内容 | 验收标准 | 状态 |
|---|---|---|---|
| P0 | 脚手架 + 部署骨架 | 云上可访问 | ✅ |
| P1 | 认证 + 网关 v1（chat 转发） | 配 Provider/Model 能流式对话 | ✅ |
| **P2** | **地基修正 + 对话应用**：Alembic；per-user 隔离；usage_logs；conversations/messages；personas + 内置绫华；前端外壳重构（侧边栏 + shadcn/ui + TanStack Query + OpenAPI 类型） | 对话历史刷新不丢；两账号资产互不可见；每次调用有计量；对话页可选 persona | ⬅ 当前 |
| P3 | **生成工作室**：jobs 执行器；生图 + TTS 适配器（各先接 1 家）；产物落盘 + `/artifacts/`；studio 页 | 生图 / TTS 端到端跑通，任务历史可查，产物可下载播放；视频按 API 可用性视情加入 | |
| P4 | **Vibe Coding V1**：对话式编程（代码块高亮、多文件上下文、复制导出），不做沙箱执行 | 能围绕代码文件问答并导出结果 | |
| P5 | **评估（evals）**：题集管理、批量跑分、同题对比视图 | 同一题集对 ≥2 个模型出对比结果 | |
| P6 | **工作流编排 alpha**：React Flow 画布 + 顺序执行引擎，节点走能力路由 | 跑通「LLM → TTS」两节点流程 | |
| P7 | **上游实验室**：训练任务管理（首个 = SoVITS 语音）；产物注册进网关 | 训练产物以 self-hosted Provider 注册并被对话/TTS 调用 | |
| P8 | **形态扩展**：买域名 + HTTPS（certbot）；桌面桌宠接本平台 API | 桌宠通过网关对话，复用 persona | |

Vibe Coding 完整形态（沙箱执行、文件树、diff 视图）体量大，V1 验证需求后再单独立项细化。

---

## 9. 部署与运维

- 维持 docker-compose 单机（Ubuntu 24.04）：`db / redis / backend / frontend(nginx)`。
- P3 起加 `artifacts` 共享 volume：backend 写、nginx 只读直出。
- 域名购买后置（下游成熟后）；购入前 HTTP + IP 访问，购入后 certbot 上 HTTPS 并收紧 CORS。
- PG 数据卷定期备份（自用阶段手动 `pg_dump` 即可）。

---

## 10. 决策记录（v2 相对 v1 的变化）

**保留**：FastAPI 一以贯之；纯 SPA 不用 Next.js；docker-compose 单机起步；网关为中心 + 能力路由 + OpenAI 兼容端点；BYOK 优先不做计费；下游优先分期推进。

**修正**：
1. Provider / Model 全局共享 → **per-user 隔离**（`user_id`，NULL 预留平台内置）。
2. 启动 `create_all` → **Alembic 迁移**。
3. capability 仅作标签 → **真正参与调度**（enabled + priority）。
4. Redis 闲置 → **启用限流与缓存**（队列后置）。

**新增**：
1. **适配器层**：非 OpenAI 兼容厂商可接入，网关从代理升级为调度中枢。
2. **Job 任务系统**：生成类能力统一生命周期，进程内执行器起步、队列后置。
3. **Persona 人格资源**：绫华从「配色」升级为一等公民，串起上下游。
4. **usage_logs 计量**：评估 / 用量展示 / 未来计费的共同地基。
5. **前端外壳 + shadcn/ui + TanStack Query + OpenAPI 类型生成**。
6. **evals 纳入中游定义**（harness = 资产管理 + 网关 + 评估）。

---

## 11. 风险与开放问题

- **生成 API 差异大**（同步/异步、轮询方式各异）→ 适配器逐个写，每期只接 1–2 家，打通再扩。
- **视频生成贵且慢** → P3 可只做生图 + TTS，视频视 API 可用性视情加入。
- **训练算力来源**（用户提供资源：本地 GPU？云 GPU 按需？）→ P7 前不定死，先定契约：训练 → 产物 → 注册进网关。
- **多用户与计费** → 自用稳定 + 有真实需求再做，schema 已预留（per-user + usage_logs）。
- **桌宠后端复用** → PLAN.md 中桌宠直连 LLM 的设计，届时改为走本平台网关，桌宠 = 平台的一个客户端。
