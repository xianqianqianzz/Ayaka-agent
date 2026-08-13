# 神里绫华 桌面AI桌宠 Agent — 项目初步规划

## Context

本项目旨在开发一个以《原神》角色**神里绫华（Kamisato Ayaka）**为形象的对话式桌面AI伴侣应用。项目参考了开源项目 **Cyrene-Agent**（https://github.com/Playa-0v0/Cyrene-Agent）的架构设计，该项目的角色是《崩坏：星穹铁道》中的昔涟。

神里绫华的核心人设：
- 稻妻神里家大小姐、「白鹭公主」
- 大和抚子性格：优雅、温柔、略带羞涩
- 擅长剑术（太刀术）与书法
- 冰元素神之眼持有者
- 第一人称使用「私（watakushi）」，说话正式而温暖

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 桌面外壳 | Electron 35+ | 提供多窗口、置顶、透明叠加能力 |
| 语言 | TypeScript 5.8+ | 全栈类型安全 |
| 构建工具 | Vite 6 + electron-vite | 统一主进程/预加载/渲染进程构建 |
| 渲染引擎 | PixiJS v7 | Live2D渲染层（pixi-live2d-display兼容版本） |
| Live2D桥接 | pixi-live2d-display ^0.5.x | 加载和显示Cubism模型 |
| Live2D运行时 | Cubism Core 4.x | 需本地化引入，不可用CDN |
| 前端框架 | React 19 | 聊天窗口和设置面板UI |
| CSS | Tailwind CSS 4 | 工具类优先样式 |
| 状态管理 | Zustand 5 | 渲染进程轻量状态管理 |
| AI协议 | AG-UI事件流 | 标准化流式聊天+工具调用协议 |
| LLM后端 | OpenAI兼容API | 支持任意兼容 `/v1/chat/completions` 的服务 |
| 测试 | Vitest 3 | 单元测试 |
| 打包 | electron-builder 25 | NSIS Windows安装包 |

---

## 项目目录结构

```
ayaka-agent/
├── package.json
├── tsconfig.json
├── electron-builder.yml
├── electron.vite.config.ts
├── .env / .env.example
│
├── resources/                        # 静态资源
│   ├── live2d/                       # Cubism Core运行时（本地化）
│   │   └── live2dcubismcore.min.js
│   ├── models/                       # Live2D模型文件
│   │   └── ayaka/                    # 绫华模型（初始用占位模型）
│   │       ├── *.model3.json
│   │       ├── *.moc3
│   │       ├── textures/
│   │       ├── motions/
│   │       └── expressions/
│   └── icons/                        # 应用图标
│
├── src/
│   ├── main/                         # Electron 主进程
│   │   ├── index.ts                  # 应用入口：窗口创建、生命周期
│   │   ├── windows/                  # 窗口管理
│   │   │   ├── pet-window.ts         # 桌宠窗口（置顶、透明、无边框）
│   │   │   ├── chat-window.ts        # 聊天窗口
│   │   │   └── settings-window.ts    # 设置窗口
│   │   ├── ipc/                      # IPC处理注册
│   │   │   ├── index.ts              # 中央IPC注册
│   │   │   ├── chat-ipc.ts           # 聊天通道
│   │   │   ├── pet-ipc.ts            # 桌宠通道
│   │   │   └── config-ipc.ts         # 配置通道
│   │   ├── agent/                    # AI Agent核心
│   │   │   ├── orchestrator.ts       # Agent主循环（AG-UI事件流）
│   │   │   ├── llm-client.ts         # LLM API客户端
│   │   │   ├── personality.ts        # 绫华人设/系统提示词
│   │   │   └── types.ts              # Agent类型定义
│   │   ├── config/                   # 配置管理
│   │   │   ├── store.ts              # 配置持久化
│   │   │   └── defaults.ts           # 默认配置
│   │   └── utils/                    # 工具函数
│   │       └── logger.ts
│   │
│   ├── preload/                      # Preload桥接脚本
│   │   ├── pet.preload.ts
│   │   ├── chat.preload.ts
│   │   └── settings.preload.ts
│   │
│   ├── renderer/                     # Vite渲染进程
│   │   ├── pet/                      # 桌宠渲染器
│   │   │   ├── index.html
│   │   │   ├── main.ts               # PIXI应用启动
│   │   │   ├── live2d/               # Live2D模块
│   │   │   │   ├── model-manager.ts  # 模型加载和生命周期
│   │   │   │   ├── motion-controller.ts  # 动作控制
│   │   │   │   ├── expression-controller.ts  # 表情管理
│   │   │   │   └── interaction.ts    # 点击/悬停交互
│   │   │   └── ui/                   # 桌宠UI叠加
│   │   │       └── bubble.ts         # 对话气泡
│   │   ├── chat/                     # 聊天窗口
│   │   │   ├── index.html
│   │   │   ├── main.tsx
│   │   │   ├── app.tsx
│   │   │   ├── components/
│   │   │   │   ├── message-list.tsx
│   │   │   │   ├── message-bubble.tsx
│   │   │   │   ├── input-box.tsx
│   │   │   │   └── streaming-text.tsx
│   │   │   └── store.ts              # 聊天状态(Zustand)
│   │   └── settings/                 # 设置窗口
│   │       ├── index.html
│   │       ├── main.tsx
│   │       └── components/
│   │           ├── api-config.tsx
│   │           ├── pet-config.tsx
│   │           └── about.tsx
│   │
│   └── shared/                       # 主进程与渲染进程共享
│       ├── ipc-channels.ts           # IPC通道常量+类型映射
│       ├── types.ts                  # 共享领域类型
│       ├── ag-ui-events.ts           # AG-UI事件类型
│       └── character-profile.ts      # 绫华角色资料
│
└── tests/
    ├── unit/
    └── e2e/
```

---

## 核心架构

### 进程模型

```
┌─────────────────────────────────────────────────┐
│                ELECTRON MAIN PROCESS             │
│                                                  │
│  ┌─────────────┐  ┌──────────┐  ┌────────────┐ │
│  │Window Manager│  │IPC Router│  │Agent Engine │ │
│  │pet/chat/     │  │          │  │┌──────────┐│ │
│  │settings      │  │          │  ││Orchestrator│ │
│  └─────────────┘  └──────────┘  ││(AG-UI)    ││ │
│                                  │├──────────┤│ │
│  ┌─────────────┐  ┌──────────┐  ││LLM Client ││ │
│  │Config Store │  │SysTray   │  │├──────────┤│ │
│  └─────────────┘  └──────────┘  ││Personality││ │
│                                  │└──────────┘│ │
│                                  └────────────┘ │
└────┬──────────────────┬──────────────────┬─────┘
     │ IPC              │ IPC              │ IPC
     ▼                  ▼                  ▼
┌──────────┐  ┌──────────────┐  ┌──────────────┐
│PET WINDOW│  │ CHAT WINDOW  │  │SETTINGS WIN  │
│PixiJS    │  │ React        │  │ React        │
│+ Live2D  │  │              │  │              │
└──────────┘  └──────────────┘  └──────────────┘
```

### 聊天数据流

```
用户输入文字 → Chat Window
    │ IPC: chat:send-message
    ▼
Agent Orchestrator
    │ 组装请求：系统提示词 + 对话历史 + 用户消息
    ▼
LLM Client (SSE流式)
    │ 逐token返回
    ▼
AG-UI事件分发
    ├── TEXT_MESSAGE → Chat Window（显示文字）
    └── 表情/动作信号 → Pet Window（表情+动作同步）
```

### 点击交互数据流

```
用户点击桌宠
    │ Live2D hitTest
    ▼
Interaction Handler
    │ 根据点击区域选择响应
    ▼
选项A（MVP）：从本地回复池播放预设响应+动作
选项B（Phase 3）：触发LLM环境评论
```

---

## MVP功能范围（Phase 1）

### 目标：可对话的桌面桌宠

1. **Live2D桌宠窗口**
   - 始终置顶、透明背景、无边框
   - 拖动移动
   - 空闲动画循环
   - 点击交互（预定义回复+动作）

2. **AI对话**
   - 独立的聊天窗口
   - 流式文字回复（逐token显示）
   - 多轮对话历史（滑动上下文窗口）
   - 绫华人设系统提示词

3. **表情与动作系统**
   - 根据对话触发表情切换（高兴/悲伤/惊讶/害羞/默认）
   - 对话时嘴唇开合同步
   - 点击触发特定动作

4. **对话气泡**
   - 点击桌宠时显示文字气泡
   - 自动消失

5. **系统托盘**
   - 托盘图标 + 右键菜单
   - 显示/隐藏桌宠
   - 打开设置
   - 退出应用

6. **设置窗口**
   - LLM API配置（端点、密钥、模型名称）
   - 桌宠基本设置（大小、位置）
   - 人设参数（温度、最大token数）

### 实现步骤（4周）

| 周次 | 内容 |
|------|------|
| 第1周 | 项目脚手架：Electron + TypeScript + Vite搭建，多窗口架构，IPC桥接 |
| 第2周 | Live2D集成：Cubism Core本地化，模型加载，空闲动画，点击交互，气泡 |
| 第3周 | AI聊天：LLM客户端，绫华人设提示词，AG-UI事件流，聊天窗口UI |
| 第4周 | 整合打磨：对话驱动表情，系统托盘，设置窗口，测试修复 |

---

## Phase 2 — 语音和记忆（后续）

- TTS语音合成（Edge TTS免费方案 + GPT-SoVITS角色语音选项）
- 记忆系统（L0人设/L1近期对话/L2长期事实提取）
- 情绪感知（根据对话内容自动切换表情）

## Phase 3 — 高级功能（远期）

- 工具调用（联网搜索、文件操作、文档生成）
- RAG知识库（原神/稻妻/绫华相关知识）
- 语音输入（ASR语音识别 + VAD静默检测）
- 主动对话（定时问候、空闲提醒）

---

## 关键决策

### 1. Live2D模型策略
- **MVP阶段**：使用Booth等平台的免费Live2D占位模型进行开发
- 所有代码基于标准Cubism 4 moc3格式，更换模型只需替换文件
- **并行任务**：在B站、Booth、DeviantArt等平台寻找神里绫华粉丝自制Live2D模型
- **长期方案**：如找不到合适模型，可考虑委托画师+Live2D建模师制作，或从MMD模型转换

### 2. PixiJS版本选择
- 使用PixiJS v7（而非v8），因为pixi-live2d-display对v7支持最稳定
- Cyrene-Agent已验证此组合可用

### 3. 多窗口架构
- 桌宠窗口和聊天窗口分离
- 桌宠窗口：透明置顶，只渲染Live2D
- 聊天窗口：标准窗口，React渲染
- 好处：用户可自由安排窗口位置（聊天放副屏等）

### 4. AG-UI协议
- 采用AG-UI事件协议标准，解耦Agent后端与前端
- 事件类型：TEXT_MESSAGE_START/CONTENT/END、TOOL_CALL、RUN_STARTED/FINISHED
- 便于后续扩展工具调用和多模态

### 5. LLM后端灵活性
- 通过配置支持任意OpenAI兼容API
- 用户可自由选择：云端API（OpenAI/DeepSeek/通义千问等）或本地模型（Ollama/LM Studio）

---

## 与参考项目的主要差异

| 方面 | Cyrene-Agent | 本项目 |
|------|-------------|--------|
| 角色 | 昔涟（崩铁） | 神里绫华（原神） |
| 范围 | 全功能（7窗口、90+IPC通道） | 渐进式：MVP精简起步 |
| PixiJS | v7 | v7（已验证兼容） |
| UI框架 | 原生JS | React 19 + Tailwind |
| TTS默认 | GPT-SoVITS/MiniMax | Edge TTS（免费） |
| 记忆系统 | DMAE Worldbook引擎 | 简化为3层（可扩展） |
| 模型可用性 | 有定制模型 | 需占位→寻找/制作 |

---

## 验证方式

1. **开发阶段**：`npm run dev` 启动Electron应用，验证桌宠窗口显示、聊天功能、IPC通信
2. **单元测试**：`npm test` 运行Vitest测试，覆盖Agent核心逻辑、IPC通道、配置管理
3. **构建验证**：`npm run build && npm start` 确保打包后应用正常运行
4. **功能验证**：
   - 桌宠窗口：透明置顶、可拖动、点击响应、动画播放
   - 聊天窗口：消息发送、流式回复、历史滚动
   - 设置窗口：API配置保存、桌宠参数调整
   - 系统托盘：菜单交互
