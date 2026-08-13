# Web 方案设计（下游优先 · 模型资产管理为骨架）

## 1. 背景与目标

- 核心目标是**跑通 AI 上下游**，而非「做桌宠」。桌宠只是后期软件形态里的一个小功能。
- 首选形态：**Web 网站（多用户）**，云服务器部署（Ubuntu 24.04），静态前端 + 后台 API。
- 中游 harness 以**模型资产管理（模型网关）**为骨架，工作流编排后续加入。
- 全程保持「神里绫华（Kamisato Ayaka）」美术主题。

---

## 2. 总体架构

```
用户浏览器
   │ HTTPS
   ▼
Nginx（静态前端 + TLS 终止 + 反向代理）
   ├── /          → 静态前端（Vite 构建产物）
   └── /api/*     → 后端 API
                      │
                      ├── PostgreSQL  用户 / 模型注册表 / 会话 / 任务
                      ├── Redis       会话 / 限流 / 异步任务队列
                      └── 对象存储    生成的图片 / 视频 / 语音 / 模型产物
```

**核心闭环（一句话）**：下游应用不直接对接各家模型，而是统一通过「模型网关」调用；上游训练出的模型，注册进网关后，就能被下游应用像调用云 API 一样调用。网关就是「跑通上下游」的枢纽。

---

## 3. 核心技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 前端框架 | Vite + React 19 + TypeScript | 已有基础 |
| UI | Tailwind CSS + shadcn/ui | 便于定制绫华主题 |
| 状态 | TanStack Query + Zustand | 服务端状态 + 客户端状态 |
| 后端 | **Python FastAPI**（已定） | 异步、自动 OpenAPI、流式友好 |
| 数据库 | PostgreSQL | JSONB，后续可加 pgvector |
| 缓存 / 队列 | Redis | 会话、限流、异步任务 |
| 对象存储 | 本地磁盘 → MinIO | 生成物与模型产物 |
| 部署 | Docker Compose + Nginx + certbot | 单机起步 |

---

## 4. 核心抽象：模型网关（Model Gateway）

中游 harness 的种子，也是下游的地基。三个实体：

- **Provider（供应商 / 来源）**：模型来源，类型如 `openai / deepseek / ollama / custom / self-hosted`。含 base_url、鉴权方式、支持的能力。
- **Model（模型）**：注册在某个 Provider 下的具体模型，带 `capability` 分类：`text-chat / embedding / tts / text-to-image / text-to-video / asr`。
- **统一推理入口**：下游应用按「能力」发起调用，网关路由到具体模型，并负责流式转发、计量、失败降级。

**关键设计：能力路由（capability routing）**。下游不写死模型名，而是声明「我要做 tts」，网关挑一个可用的 tts 模型。带来的好处：

- 支持两种接入模式：用户**自带 Key**（BYOK）或**用平台额度**。
- 上游训练的模型 = 注册一个 `self-hosted` Provider + Model，即可被下游无差别调用。

---

## 5. 后端设计

### 模块划分（单体起步，后续再拆）

1. `auth` — 最简注册 / 登录 / JWT（短期单用户，预留扩展，不做完整用户体系）
2. `users` — 资料、额度 / 计费（后续）
3. `gateway` — Provider / Model CRUD、能力路由、统一推理、流式代理、计量
4. `chat` — 会话 / 消息（对话应用）
5. `generation` — TTS / 生图 / 生视频（异步任务）
6. `agent` — Vibe Coding 运行时（后续）
7. `workflow` — 工作流编排（中游，后续）
8. `training` — 训练任务管理（上游，后续）

### 主要 API（前缀 `/api/v1`）

- 认证：`POST /auth/register`、`/auth/login`、`/auth/refresh`
- 网关：`GET /models?capability=tts`、`POST /providers`（管理端）
- 统一推理：`POST /chat/completions`（OpenAI 兼容 + SSE 流式）
- 对话：`/conversations`、`/conversations/{id}/messages`
- 生成：`POST /generate/{tts|image|video}` → 返回 job；`GET /jobs/{id}`
- 后续：`/workflows`（中游）、`/trainings`（上游）

### 关键数据表

- `providers`、`models`、`api_keys`（用户自带 Key）
- `users`、`conversations`、`messages`
- `jobs`（异步任务：类型 / 模型 / 入参 / 状态 / 产物 URL）
- `workflows`、`workflow_runs`（后续）

---

## 6. 前端设计

- **类型安全**：后端 FastAPI 自动生成 OpenAPI → 生成 TS 类型，前后端契约不脱节。
- **页面结构**：
  1. 落地 / 登录注册
  2. 控制台 Dashboard（应用入口 + 用量）
  3. **对话**（旗舰应用，流式 UI）
  4. **生成工作室**（TTS / 生图 / 生视频，任务化）
  5. Vibe Coding 工作台（后续）
  6. 管理端（网关：Provider / Model / 额度；训练任务；工作流，后续）
- **主题**：绫华美术风格（冰蓝、和风）贯穿所有页面。

---

## 7. 三层落地映射

- **下游** = 控制台里的各个「应用」（对话 / TTS / 生图 / 生视频 / Vibe Coding），全部经网关调用。
- **中游** = 网关（已做）+ 工作流（后续）。
- **上游** = 训练模块（后续）：提交训练任务 → 产出模型 → 注册进网关 → 被下游调用。

---

## 8. 分期规划

| 阶段 | 内容 | 意义 |
|---|---|---|
| P0 | 脚手架 + 部署骨架（Docker / Nginx / PG / Redis） | 地基 |
| P1 | 认证 + 模型网关（Provider / Model + 统一流式推理） | harness 种子 |
| P2 | 对话应用端到端（首个下游应用，验证整条链路） | 里程碑 |
| P3 | TTS + 生图 + 生视频（异步任务） | 扩充下游 |
| P4 | Vibe Coding agent | 下游重头 |
| P5 | 工作流编排 | 中游补全 |
| P6 | 训练模块 + 注册进网关 | 上游闭环 |

---

## 9. 已确定的技术决策

1. **后端语言**：Python FastAPI（一以贯之，训练 / 推理都是 Python 生态）
2. **前端形态**：纯 SPA（Vite + React + TS），不用 Next.js
3. **用户体系**：短期仅自己使用，只做最简注册 / 登录并预留扩展；不做计费 / 完整多用户体系，接入模式先做 **BYOK**（用户自带 Key）
4. **部署**：Docker Compose 单机起步（Ubuntu 24.04）
