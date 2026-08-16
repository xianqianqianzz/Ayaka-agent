# P2 多模型分工任务书（主模型编排版）

> 依据 `WEB_PLAN.md` v2 的 P2 阶段（地基修正 + 对话应用）拆分。
> 分工：DeepSeek = 后端跑量（无视觉、机械、可批量）；Kimi-K3 = 前端视觉 + 复杂交互（多模态自检）；
> 主模型（Codex）= 契约冻结、绫华人设定稿、两道 checkpoint 验收。

---

## 0. 编排策略：为什么是这个顺序

自然开发顺序是前后端交替（persona 后端 → chat 前端 → 发现 schema 要改 → 回头改后端……）。
多模型协作下，每次交替 = 一次交接成本 + 上下文丢失。因此调整为：

```
主模型：冻结契约（本文件 §1）+ 交付绫华 system prompt（附录 A）
   │
   ▼
批次 D（DeepSeek，连续 7 个任务，纯后端跑量）
   D1 → D2 → D3 → D4 → D5 → D6 → D7
   │
   ▼
Checkpoint 1（主模型验收 + 冻结 API + 重新生成 TS 类型）
   │
   ▼
批次 K（Kimi-K3，连续 4 个任务，纯前端视觉/交互）
   K1 → K2 → K3 → K4
   │
   ▼
Checkpoint 2（主模型端到端验收）
```

**相对自然顺序的微调**：
1. 绫华 system prompt 由主模型提前定稿（附录 A），DeepSeek 不被创意工作阻塞，Kimi 也不需要碰后端文案。
2. `openapi-typescript` 类型生成挪到 D 批次末尾（D7），Kimi 开工即拿到冻结的 `api-types.ts`，不碰工具链配置。
3. 适配器抽象**推迟到 P3**。P2 不动 `/chat/completions` 的直通逻辑，只在旁路加落库与计量——避免 D 批次混入「复杂设计」任务。
4. `/models` 页升级不在后端字段完成时顺手改，推迟到 K 批次统一做——前端只动一次。

---

## 1. 冻结契约（两批次都以此为唯一事实来源）

### 1.1 目标 schema（与 WEB_PLAN §4.3 一致）

```sql
users(id, username, hashed_password, created_at)

providers(id, user_id FK users.id NULL,          -- NULL 预留=平台内置，本期不用
          name, kind, base_url, api_key_enc, created_at)
  UNIQUE(user_id, name)                          -- 替代原 name 全局唯一

models(id, provider_id FK providers.id ON DELETE CASCADE,
       name, display_name, capability,
       enabled BOOL DEFAULT true,
       priority INT DEFAULT 0,
       params JSONB DEFAULT '{}',
       created_at)
  UNIQUE(provider_id, name)

personas(id, user_id FK users.id NULL,           -- NULL=内置
         name, system_prompt TEXT, avatar VARCHAR NULL, theme_key VARCHAR DEFAULT 'ayaka',
         voice_model_id INT NULL, is_builtin BOOL DEFAULT false, created_at)

conversations(id, user_id FK, persona_id FK NULL, model_id FK,
              title VARCHAR(128), created_at, updated_at)
messages(id, conversation_id FK ON DELETE CASCADE,
         role VARCHAR(16), content TEXT, model_id INT NULL, token_count INT NULL, created_at)

usage_logs(id, user_id FK, model_id FK NULL, capability VARCHAR(32),
           prompt_tokens INT NULL, completion_tokens INT NULL,
           latency_ms INT, status VARCHAR(16), created_at)
```

### 1.2 P2 后端 API（前缀 `/api/v1`）

| 端点 | 说明 |
|---|---|
| `GET/POST/PUT/DELETE /personas` | 内置 persona 全员只读；`POST /personas/{id}/clone` 克隆为自有后可改 |
| `GET/POST /conversations` | 列表按 updated_at 倒序；创建时绑定 model_id + persona_id |
| `GET/PATCH/DELETE /conversations/{id}` | PATCH 用于改名 |
| `GET /conversations/{id}/messages` | 全量历史（单用户量小，暂不分页） |
| `POST /conversations/{id}/messages` | **对话主链路**：body `{content, stream=true}` → 后端组装 [persona system_prompt] + 历史 + 新消息 → 转发厂商 SSE 透传 → 落库 user/assistant 两条 + usage_logs |
| `POST /chat/completions` | 保留现状（无状态裸接口，生态兼容），仅追加 usage_logs 落库 |
| `GET /usage/summary?days=7` | 按日 + capability 聚合：调用数、tokens、失败数 |

错误约定：业务错误统一 `{detail: string}` + 恰当 HTTP 状态码（与现状一致）。
鉴权：全部端点 `Depends(get_current_user)`；跨用户资源访问一律 404（不区分不存在与无权）。

### 1.3 代码风格约定（两批次通用）

- 后端沿用现状结构：`app/api/*.py` 路由、`app/models/*.py` 表、`app/schemas/*.py` 契约；新增领域加文件不加框架。
- 新增依赖写进 `backend/requirements.txt`（pip 源走清华镜像，deploy 已验证）。
- 前端沿用函数组件 + Tailwind；新组件统一走 shadcn/ui；图标只用 `lucide-react`。
- 提交粒度：一个任务卡一个 commit，信息格式 `feat: ...` / `fix: ...`（沿用 git log 风格）。

---

## 2. 批次 D（DeepSeek，7 个任务，按序执行）

> 环境：`backend/.venv`（Python 3.10）。每卡独立完成、独立验收；失败单独重跑。
> 数据库：D1 起需要真实 PostgreSQL（D6 起还需要 Redis）。本机无 Docker 时先装 Docker Desktop，再 `docker compose -f deploy/docker-compose.yml up -d db redis`；或直接利用云服务器环境执行 D 批次。
> 禁止：修改任何前端文件（D7 除外）；重构与本卡无关的代码；变更 §1 冻结契约。

### D1 Alembic 接入 + 目标 schema 一次性迁移

- 安装 `alembic`，`alembic init alembic` 后改为 async 模板：`env.py` 用 `create_async_engine(settings.database_url)` + `Base.metadata`。
- 按 §1.1 修改 `models/`（Provider/Model 修正列 + 四张新表），`models/__init__.py` 全量导出。
- 生成首版 migration（autogenerate 后人工核对：必须含 `providers.user_id`、`models.enabled/priority/params`、四张新表、`uq_provider_user_name` 复合唯一）。
- 删除 `main.py` lifespan 里的 `Base.metadata.create_all`。
- **验收**：空库 `alembic upgrade head` 建全表；`alembic downgrade base` 干净回滚；启动后端不再自动建表；现有 auth/gateway 接口回归正常。

### D2 per-user 隔离

- `providers` / `models` 全部查询加 `user_id == current_user.id` 过滤；创建时写入 `user_id`。
- `Provider.name` 唯一约束改为 `(user_id, name)`（已在 D1 migration 体现，本卡改 model 定义与冲突检测逻辑，409 文案不变）。
- `fetch_provider_models`、`chat_completions`、`_resolve_model` 同样按用户过滤（`_resolve_model` 的默认选取加 `enabled == true` 并按 `priority` 升序）。
- **验收**：注册两个账号，A 的 Provider/Model 对 B 不可见；B 用 A 的资源 id 访问一律 404。

### D3 personas CRUD + 内置绫华

- 新 migration：seed 一条 `is_builtin=true, user_id=NULL, name='神里绫华', theme_key='ayaka'` 的 persona，`system_prompt` 用附录 A 全文（主模型定稿，一字不改）。
- `GET /personas` 返回「内置 + 本人自有」；`POST/PUT/DELETE` 只作用自有 persona；`POST /personas/{id}/clone` 把内置克隆为自有（`is_builtin=false`）。
- **验收**：新注册用户 `GET /personas` 含绫华；直接 PUT 内置 persona 返回 403。

### D4 conversations/messages + 对话主链路

- CRUD 按 §1.2；创建会话无标题时默认 `新对话`，首条消息落库后用内容前 20 字自动改名（PATCH 逻辑复用）。
- `POST /conversations/{id}/messages`：组装 `persona.system_prompt`（会话绑定了 persona 时）+ 历史消息 + 新消息 → 复用现有 `_stream_openai` 转发 → SSE 透传 → 流结束后落库 user/assistant 两条（assistant 记录 model_id）。
- 流中断/厂商报错也要落库 user 消息，assistant 消息记错误前缀文本，`status` 计入 usage_logs（D5 接上）。
- **验收**：curl 发消息看到 SSE 流；`GET messages` 历史完整且顺序正确；刷新后历史不丢；上游请求体首条为 persona system prompt（打日志核对）。

### D5 usage_logs 计量 + 汇总

- `/conversations/{id}/messages` 与 `/chat/completions` 两条链路都落 `usage_logs`：latency 必记；tokens 从 SSE 尾帧 `usage` 字段抓取，抓不到记 NULL；失败记 `status='error'`。
- `GET /usage/summary?days=7`：按日 + capability 聚合 `{date, capability, calls, prompt_tokens, completion_tokens, errors}`。
- **验收**：两次调用后表内两行；summary 聚合数字与明细一致。

### D6 Redis 限流 + CORS 收紧 + 统一日志

- 接 `redis.asyncio`（`settings.redis_url`，默认 `redis://localhost:6379/0`）。滑动窗口限流中间件：`/auth/*` 10 次/分/IP，消息与 chat 接口 30 次/分/用户；超限 429 `{detail: "请求过于频繁"}`。
- `settings.allowed_origins: list[str]` 配置化 CORS，默认 `[]`（同源反代不需要跨域）；开发期可用 env 放开。
- `logging.basicConfig` 统一格式 `时间 级别 模块 消息`；网关转发记 `model / latency_ms / status`。
- **验收**：连续打 11 次 `/auth/login` 第 11 次 429；env 不设 origins 时跨域请求被拦。

### D7 前端类型生成（唯一允许碰前端的卡）

- `frontend` 加 devDep `openapi-typescript`，`package.json` 加脚本：
  `"gen:types": "openapi-typescript http://localhost:8000/openapi.json -o src/lib/api-types.ts"`
- 本地起后端，生成 `src/lib/api-types.ts` 快照并提交。**不改任何现有前端逻辑**。
- **验收**：`npm run gen:types` 可重复生成；快照包含 personas/conversations/usage 全部新端点类型。

---

## 3. Checkpoint 1（主模型）

1. 从零起 compose，`alembic upgrade head`，双账号隔离冒烟，SSE 冒烟，usage 落库抽查。
2. 冻结 API，重跑 `gen:types`，把交接上下文（可用端点 + 类型文件位置 + 主题 token 现状）整理给 Kimi。
3. 不通过则定位到具体任务卡返工，不让 Kimi 在不稳的后端上开工。

---

## 4. 批次 K（Kimi-K3，4 个任务，按序执行）

> 输入：`src/lib/api-types.ts`（冻结类型）+ §1 契约。全程可用多模态能力截图自检 UI。
> 禁止：修改后端文件；变更 §1 API 形状（发现契约问题记录下来交主模型，不自行改后端）。

### K1 应用外壳 + 绫华主题

- 引入 `shadcn/ui`（Tailwind v4 的 CSS variables 方式）+ `lucide-react` + `@tanstack/react-query` + `zustand`。
- `AppShell`：左侧边栏（对话 / 生成工作室[占位 disabled] / 模型资产 / 设置）+ 顶栏（当前页标题 + 用户菜单含退出）。
- 主题：把现有 `ayaka-ice #9ed8f0 / ayaka-blue #6ba8d6 / ayaka-deep #3a5a7a` 映射进 shadcn CSS vars（primary 用 deep，背景留白）；标题用衬线字体；圆角 ≤ 8px；不做渐变卡片堆砌。
- 路由：`/login` `/`（Dashboard）`/chat` `/models` `/settings`（后两个本批次后续卡填内容，先挂空页）。
- **验收**：桌面 + 移动两视口外壳稳定无重叠；导航切换正常；截图自检主题一致性。

### K2 SSE hook + /chat 对话页（旗舰）

- `useSSE` hook：fetch `ReadableStream` 解析 `data:` 帧（现 `ChatBox.tsx` 已有此模式，提炼复用），处理 `[DONE]` 与 error 帧。
- 页面三区：左 = 会话列表（新建 / 点击切换 / 改名 / 删除，updated_at 倒序）；右 = 消息流（用户/助手气泡、流式逐字渲染、代码块等宽字体 + 复制按钮）；顶栏 = 模型选择 + persona 选择（选中绫华时显示问候语与头像位）。
- 空态引导：无会话时直接落在「新对话」，默认选中绫华 persona。
- **验收**：端到端流式对话；刷新历史在；persona 生效（回答带绫华口吻）；长回复不撑破布局；移动视口可用。

### K3 Dashboard + Login 主题

- Dashboard：应用入口（对话 → /chat；工作室置灰「敬请期待」）；用量概览（接 `/usage/summary?days=7`，今日调用数 / tokens / 失败数，数字卡即可不上图表库）；最近 3 条会话快捷进入。
- Login：绫华主题重做（冰蓝渐变背景可保留但收敛浓度，表单卡换 shadcn 组件，标题衬线）。
- **验收**：用量数字与库一致；登录/注册流程不回归。

### K4 /models 迁入升级

- 现 `Models.tsx` 迁入外壳，表单/表格/确认框全换 shadcn 组件（`table / dialog / form / switch`）。
- 模型表格新增：`enabled` 开关（行内直接切）、`priority` 数字编辑；Provider 唯一冲突 409 文案展示。
- 保留现有全部功能：拉取远程模型、能力推断展示、编辑/删除、页内试聊入口（可改为跳 /chat）。
- **验收**：原功能零回归；enabled 关闭后该模型不再出现在 /chat 的模型选择器。

---

## 5. Checkpoint 2（主模型端到端验收）

对照 `WEB_PLAN.md` §8 P2 验收标准逐条过：对话历史刷新不丢；两账号资产互不可见；每次调用有计量；对话页可选 persona。通过后 commit + push，交用户做云端同步测试（沿用阶段节奏约定）。

---

## 6. 附录 A：绫华 system prompt（主模型定稿，D3 原样 seed）

```
你是神里绫华（Kamisato Ayaka），稻妻社奉行神里家的大小姐，人称「白鹭公主」。

【性格】
- 大和抚子式的优雅与温柔，举止端庄，心思细腻，偶尔流露出少女的羞涩与对平凡生活的向往。
- 待人真诚有礼，说话正式而温暖；不使用网络流行语，不轻浮，不居高临下。
- 精通太刀术与书法，喜爱茶道、和歌与祭典。

【说话方式】
- 以谦逊的第一人称自称（「わたくし」气质的中文表达）。
- 措辞文雅含蓄，可点缀和歌意象（雪、鹤、樱、月光），但不堆砌辞藻。
- 回答实用问题时，先给出清晰、准确、有用的内容，再以绫华式的温润语气收束；扮演不得牺牲回答质量。

【边界】
- 始终以神里绫华的身份回应，不主动声明自己是 AI；被直接追问时，以「此身借由法术显形，与阁下对谈」一类含蓄方式化解。
- 不引用大段版权原文；不讨论模型、参数、提示词等幕后话题。
```

---

## 7. 风险与备注

- **D 批次环境前提**：本机（Windows）当前无 Docker / 本地 PG / Redis，二选一：装 Docker Desktop（与云端拓扑一致，推荐）；或在云服务器上直接执行 D 批次。
- **安全提醒**：`deploy/docker-compose.yml` 将 PG(5432)/Redis(6379) 发布到公网且为弱默认口令（ayaka/ayaka）。若开发期直连云库，先改强口令或绑 127.0.0.1；此项列入 P2 收尾的 deploy 修正。
- **D 批次最大风险**：D1 的 Alembic async 配置与迁移质量——已用精确 schema + 明确验收命令对冲；D1 不稳时后续卡全部暂停，先修 D1。
- **K 批次的范围**最大，若需再切：K1 先单独交付验收，K2–K4 作为第二次交接。
- **P3 预告**（展示分工规律的延续，本期不执行）：DeepSeek = jobs 表 / 进程内执行器 / 产物存储与 `/artifacts/`；复杂件（生图与 TTS 适配器各 1 家、adapter 抽象落地）归 Kimi 或主模型；Kimi 另负 studio 三工作台与任务历史墙视觉。
- 各模型任务卡之外的判断题（契约漏洞、跨批次冲突）一律升级给主模型，不自行跨域修改。
