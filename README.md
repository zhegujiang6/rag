# 智能文档检索助手

基于 RAG + LLM 的智能文档检索与问答系统。支持多格式文档上传、知识库管理、语义检索和流式对话。

## 功能特性

- 📁 **多格式文档支持**: PDF / Word / TXT / Markdown
- 📚 **多知识库管理**: 独立知识库，文档关联
- 🔍 **语义检索**: 基于向量相似度的智能搜索（父子块策略）
- 💬 **流式对话**: SSE 打字机效果，Markdown 渲染
- 🧠 **双模式**: RAG 知识库问答 + 普通 LLM 对话
- 🐳 **Docker 部署**: 一键启动所有服务

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy 2.0 + ChromaDB |
| 前端 | Vue 3 + Vite + TailwindCSS |
| LLM | OpenAI API 兼容接口 |
| 数据库 | MySQL 8.0 |
| 部署 | Docker + Docker Compose |

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM API Key
```

### 2. Docker Compose 启动

```bash
docker-compose up -d
```

### 3. 访问

- 前端: http://localhost
- 后端 API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

### 4. 使用

1. 上传文档（PDF/Word/TXT/Markdown）
2. 创建知识库并关联文档
3. 选择知识库，开始 RAG 智能问答
4. 不选知识库即为普通对话模式

## 本地开发

### 后端

```bash
cd backend
pip install -r requirements.txt

# 启动 MySQL (Docker)
docker run -d --name mysql-dev \
  -e MYSQL_ROOT_PASSWORD=password \
  -e MYSQL_DATABASE=doc_search \
  -p 3306:3306 mysql:8.0

# 启动后端
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/documents/upload` | 上传文档 |
| GET | `/api/v1/documents` | 文档列表 |
| DELETE | `/api/v1/documents/{id}` | 删除文档 |
| POST | `/api/v1/knowledge-bases` | 创建知识库 |
| GET | `/api/v1/knowledge-bases` | 知识库列表 |
| POST | `/api/v1/chat` | 普通对话 (SSE) |
| POST | `/api/v1/chat/rag` | RAG 问答 (SSE) |
| GET | `/api/v1/conversations` | 对话历史 |

完整 API 文档见: http://localhost:8000/docs

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置管理
│   │   ├── api/                 # API 路由
│   │   ├── core/                # 核心引擎
│   │   │   ├── document_parser.py
│   │   │   ├── document_splitter.py
│   │   │   ├── embedding_service.py
│   │   │   ├── vector_store.py
│   │   │   ├── llm_client.py
│   │   │   └── rag_engine.py
│   │   ├── models/              # ORM 模型
│   │   ├── middleware/          # 中间件
│   │   └── utils/               # 工具
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── views/Home.vue
│   │   ├── components/          # Vue 组件
│   │   ├── stores/              # Pinia 状态管理
│   │   └── api/                 # API 封装
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```
