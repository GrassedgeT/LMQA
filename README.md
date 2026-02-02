# LMQA - AI Chat with Long-term Memory

LMQA 是一个集成了长期记忆功能的 AI 聊天应用演示项目。它结合了 React 前端和 Flask 后端，利用 Mem0 记忆层、Qdrant 向量数据库和 Neo4j 图数据库，实现了一个能够“记住”用户交互和上下文的智能对话系统。


## 🛠️ 技术栈

### Backend (后端)
*   **Core**: Python 3.12+, Flask
*   **Memory Layer**: Mem0 (集成 Graph & Vector Memory)
*   **Database**:
    *   **Vector DB**: Qdrant (用于语义搜索)
    *   **Graph DB**: Neo4j (用于关系图谱)
    *   **Relational DB**: SQLite (用于存储用户、对话历史和系统配置)
*   **Package Manager**: uv (高性能 Python 包管理器)

### Frontend (前端)
*   **Core**: React 19, TypeScript
*   **Build Tool**: Vite
*   **Routing**: React Router
*   **Styling**: CSS Modules

---

## 🚀 快速开始

### 1. 前置要求
*   **Docker & Docker Compose** (用于运行数据库)
*   **Node.js & npm** (用于前端)
*   **Python 3.12+** (建议安装 `uv` 包管理器)

### 2. 启动数据库服务
请确保 Docker Desktop 或 Docker Engine 正在运行，然后在项目根目录 (`LMQA/`) 或 `backend/` 目录下运行：

```bash
docker-compose up -d
```
*   **Qdrant**: 端口 6333 (GRPC) / 6334 (HTTP)
*   **Neo4j**: 端口 7474 (HTTP) / 7687 (Bolt)
*   **注意**: 首次启动可能需要几分钟拉取镜像。

### 3. 后端设置 (Backend)

进入后端目录：
```bash
cd backend
```

**安装依赖:**
```bash
uv sync
```

**配置环境变量:**
复制示例文件并重命名为 `.env`：
```bash
cp .env-example .env
```
编辑 `.env` 文件，填入必要的配置：
*   **数据库配置**: Qdrant 和 Neo4j 的地址/账号密码 (默认为 Docker Compose 预设值)。
*   **LLM API Key**: 填入你的 LLM 提供商 Key (如 `GOOGLE_API_KEY`, `OPENAI_API_KEY` 等)。
*   **Secret Key**: 设置 `SECRET_KEY`。

**运行服务器:**
```bash
uv run main.py
```
后端服务将在 `http://localhost:5000` 启动。

### 4. 前端设置 (Frontend)

进入前端目录：
```bash
cd frontend
```

**安装依赖:**
```bash
npm install
```

**运行开发服务器:**
```bash
npm run dev
```
前端服务将在 `http://localhost:3000` (或 5173，视 Vite 配置而定) 启动。

---

## 📂 项目结构

```
.
├── backend/                  # Flask 后端应用
│   ├── app/
│   │   ├── api/              # API 路由 (Auth, Chat, Memories)
│   │   ├── core/             # 核心配置与工具
│   │   └── services/         # 业务逻辑服务
│   ├── memory/               # Mem0 记忆模块集成
│   ├── docker-compose.yml    # 数据库容器配置
│   ├── main.py               # 程序入口
│   └── pyproject.toml        # Python 依赖配置
├── frontend/                 # React 前端应用
│   ├── src/
│   │   ├── components/       # UI 组件
│   │   ├── contexts/         # React Context (Theme等)
│   │   ├── pages/            # 页面 (Chat, Login, Memory等)
│   │   └── api.ts            # API 调用封装
│   └── vite.config.ts        # Vite 配置
└── evaluation/               # 模型评估脚本
```

## ⚠️ 开发注意事项 

**如果你使用 AI 辅助写代码，请严格遵守以下规则：**

1.  **文件完整性**：不要让 AI 随意破坏他人编写的文件结构。
2.  **依赖管理**：**禁止 AI 自动运行安装命令**。所有依赖必须根据文档手动管理。
    *   Python: 使用 `uv add <package>`
    *   Frontend: 使用 `npm install <package>`
3.  **Commit 规范**：Commit message 必须遵守 [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)。
4.  **安全**：**严禁将 API KEY 硬编码到代码中**。必须使用 `.env` 文件获取，且 `.env` 禁止提交到远程仓库。
5.  **简易Git 流程**：
    *   开发新功能前，从 `main` 分支切出自己的新分支。
    *   Push 前必须先拉取远端最新代码并使用 `rebase`：
        ```bash
        git fetch origin
        git rebase origin/main
        git push -u origin feature/your-feature-name
        ```
    *   合并代码必须通过 GitHub Pull Request (PR) 进行。

---