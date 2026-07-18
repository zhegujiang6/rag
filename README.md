# 智能文档检索助手

基于 RAG 与大语言模型的文档检索、知识库问答和效果评测系统。当前仓库包含一套可直接运行的 Python 应用，以及一套独立的 Java 微服务升级版。

## 快速启动（推荐）

1. 复制环境变量模板并填写至少一个可用的 LLM/Embedding API Key：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 构建并启动 Python 主应用、RAG API、MySQL 和 ChromaDB：

   ```powershell
   docker compose up -d --build
   ```

3. 访问服务：

   - Streamlit 应用：<http://localhost:8501>
   - RAG API 文档：<http://localhost:8100/docs>
   - RAG API 健康检查：<http://localhost:8100/health>

查看状态和日志：

```powershell
docker compose ps
docker compose logs -f app rag-server
```

## 本地开发

需要 Python 3.11+。先安装当前项目及两类应用依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[streamlit,api,dev]"
```

只使用 Docker 启动基础设施：

```powershell
docker compose up -d mysql chroma
```

分别启动两个 Python 入口：

```powershell
streamlit run apps/streamlit/app.py
python -m smart_doc_search.api.main
```

## 目录结构

```text
├─ apps/
│  └─ streamlit/             # Streamlit 入口、公共 UI 和功能页面
├─ src/smart_doc_search/
│  ├─ api/                   # FastAPI RAG 接口与路由
│  ├─ core/                  # 配置等核心基础设施
│  ├─ data/                  # SQLAlchemy 连接和数据模型
│  └─ services/              # 解析、切分、检索、问答、评测等业务能力
├─ deployment/docker/        # Python 应用的镜像定义
├─ data/
│  ├─ chroma/                # 本地向量库数据
│  ├─ uploads/               # 上传的原始文档
│  ├─ extracted_images/      # 文档解析产生的图片
│  └─ evaluations/           # 评测数据集
├─ platform/java/            # 独立的 Java 微服务升级版
├─ tools/resume/             # 与主应用无关的简历文档工具
├─ docker-compose.yml        # Python 主应用的一键编排
└─ pyproject.toml            # Python 包与依赖声明
```

`data/` 中已有的上传文件和 ChromaDB 数据在整理时被完整保留。`.env` 只用于本机配置，不应提交到版本库。

## Java 微服务版

Java 版位于 [`platform/java`](platform/java/README.md)，采用 Spring Boot、Spring Cloud、Redis、Nacos、MinIO、RocketMQ 和 ChromaDB Sidecar。它与根目录 Python 主应用相互独立：

```powershell
Set-Location platform/java
mvn -DskipTests compile
docker compose up -d --build
```

## 验证

```powershell
python -m pytest
docker compose config -q
mvn -q -f platform/java/pom.xml -DskipTests compile
```
