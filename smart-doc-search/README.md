# 智能文档检索助手 — Java 微服务后端

基于 Spring Boot 3.2 + Spring Cloud 2023 + Redis + ChromaDB 的智能文档检索问答系统。

## 项目结构

```
smart-doc-search/
├── common/                    # 公共模块 (DTO/异常/工具类)
├── gateway/                   # API 网关 (Spring Cloud Gateway)
├── user-service/              # 用户服务 (认证/授权/会话)
├── rag-service/               # RAG 检索与对话服务
├── document-service/          # 文档与知识库服务
├── evaluation-service/        # RAGAS 评测服务
├── chromadb-sidecar/          # ChromaDB Python Sidecar (FastAPI)
├── streamlit-frontend/        # Streamlit 前端
├── k8s/                       # Kubernetes 部署配置
├── scripts/                   # 初始化 & 迁移脚本
└── docker-compose.yml         # 本地开发环境
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | Spring Boot 3.2 + Spring Cloud 2023 |
| JDK | JDK 17+ (Virtual Threads) |
| 注册中心 | Nacos |
| 网关 | Spring Cloud Gateway |
| 缓存 | Redis 7 + Spring Cache |
| 数据库 | MySQL 8.0 + HikariCP |
| 向量库 | ChromaDB (Sidecar) / Milvus |
| 消息队列 | RocketMQ |
| 对象存储 | MinIO |
| 鉴权 | Spring Security + JWT |
| 熔断降级 | Resilience4j |
| 监控 | Micrometer + Prometheus + Grafana |
| 文档 | SpringDoc OpenAPI + Knife4j |

## 快速开始

```bash
# 1. 启动基础设施
docker-compose up -d mysql redis nacos minio chromadb

# 2. 编译项目
mvn clean package -DskipTests

# 3. 启动各服务
mvn spring-boot:run -pl gateway
mvn spring-boot:run -pl user-service
mvn spring-boot:run -pl rag-service
mvn spring-boot:run -pl document-service
mvn spring-boot:run -pl evaluation-service
```

## 相关文档

- [后端升级方案](./docs/项目后端Java升级方案.docx)
