# Java 微服务升级版

这是智能文档检索助手的独立 Java 微服务实现，基于 Spring Boot 3.2、Spring Cloud 2023、Redis、Nacos、MinIO、RocketMQ 和 ChromaDB Sidecar。

## 模块

```text
platform/java/
├─ common/                    # 公共 DTO、异常、上下文与工具
├─ gateway/                   # API 网关与鉴权过滤器
├─ user-service/              # 用户注册、登录与令牌管理
├─ document-service/          # 文档、知识库和处理流水线
├─ rag-service/               # 检索与对话
├─ evaluation-service/        # RAG 效果评测
├─ chromadb-sidecar/          # ChromaDB Python HTTP 适配层
├─ streamlit-frontend/        # Java 网关对应的轻量前端
├─ scripts/                   # 数据库初始化与迁移
├─ k8s/                       # Kubernetes 资源
└─ docker-compose.yml         # 本地完整环境
```

## 编译验证

需要 JDK 17+ 与 Maven 3.9+：

```powershell
mvn -DskipTests compile
```

## Docker 启动

复制模板并填写所需密钥：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

主要入口：

- Streamlit：<http://localhost:8501>
- API 网关：<http://localhost:8080>
- Nacos：<http://localhost:8848/nacos>
- MinIO 控制台：<http://localhost:9001>

也可以只启动基础设施：

```powershell
docker compose up -d mysql redis nacos minio rocketmq-namesrv rocketmq-broker chromadb-sidecar
```
