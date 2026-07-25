"""RAG 微服务 — FastAPI 应用入口.

启动方式:
    # 开发模式
    python -m smart_doc_search.api.main

    # 生产模式
    uvicorn smart_doc_search.api.main:app --host 0.0.0.0 --port 8100 --workers 1

    # Docker
    docker build -t rag-server . && docker run -p 8100:8100 rag-server
"""
import os

from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from smart_doc_search.core.config import settings
from smart_doc_search.data.database import init_db
from smart_doc_search.services.vector_store import vector_store
from smart_doc_search.api.routers import routers
from smart_doc_search.api.concurrency import RequestConcurrencyMiddleware
from loguru import logger as log


# ════════════════════════════════════════════════════════════════
# 应用生命周期
# ════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的初始化与清理."""
    # ── 启动 ──────────────────────────────────────────────
    log.info("=" * 60)
    log.info(f"RAG Server 启动中... v{settings.APP_VERSION}")
    log.info(f"LLM Model: {settings.LLM_MODEL}")
    log.info(f"Embedding: {settings.EMBEDDING_MODEL}")
    log.info(f"ChromaDB:  {settings.CHROMA_PERSIST_DIR}")

    try:
        log.info("正在初始化数据库...")
        init_db()
        log.info("数据库初始化完成")
    except Exception as e:
        log.error(f"数据库初始化失败: {e}")
        # 不阻止启动 — 检索和嵌入功能仍可工作

    try:
        log.info("正在初始化 ChromaDB...")
        _ = vector_store.client
        log.info("ChromaDB 初始化完成")
    except Exception as e:
        log.error(f"ChromaDB 初始化失败: {e}")

    log.info("=" * 60)

    yield  # 应用在此运行

    # ── 关闭 ──────────────────────────────────────────────
    log.info("RAG Server 正在关闭...")


# ════════════════════════════════════════════════════════════════
# FastAPI 应用实例
# ════════════════════════════════════════════════════════════════

app = FastAPI(
    title="RAG 智能文档检索服务",
    description="""
## 概述

为智能文档检索助手提供核心 RAG 能力的微服务。

### 核心能力
- **语义检索**: 向量检索 + 混合搜索 (BM25) + 重排序
- **RAG 对话**: 基于知识库文档的流式 (SSE) / 同步问答
- **查询优化**: 查询改写、HyDE 假设文档生成
- **上下文压缩**: 句子级相关性过滤

### 设计原则
- 纯 RAG 引擎，不含文档接入/用户管理（由 Java 后端负责）
- SSE 流式输出，Java 后端通过 `SseClient` 消费
- 可选 API Key 认证（`X-API-Key` 头）
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    RequestConcurrencyMiddleware,
    max_concurrency=settings.RAG_MAX_CONCURRENT_REQUESTS,
    queue_timeout_seconds=settings.RAG_CONCURRENCY_QUEUE_TIMEOUT_SECONDS,
)


# ════════════════════════════════════════════════════════════════
# CORS 中间件
# ════════════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 生产环境应限制为 Java 后端地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


# ════════════════════════════════════════════════════════════════
# 全局异常处理
# ════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """捕获所有未处理的异常，返回统一格式."""
    log.error(f"未处理异常 [{request.method} {request.url.path}]: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "内部服务错误", "detail": str(exc)},
    )


# ════════════════════════════════════════════════════════════════
# 健康检查
# ════════════════════════════════════════════════════════════════

@app.get(
    "/health",
    tags=["系统"],
    summary="健康检查",
    description="检查各依赖服务的连接状态.",
)
def health_check() -> Dict[str, Any]:
    """检查 MySQL、ChromaDB、LLM API 的连通性."""
    status = {"status": "healthy", "version": settings.APP_VERSION}

    # 1. ChromaDB 检查
    try:
        _ = vector_store.client
        status["chroma_status"] = "ok"
    except Exception as e:
        status["chroma_status"] = f"error: {e}"
        status["status"] = "degraded"

    # 2. LLM API 检查（轻量级 — 仅验证配置是否存在）
    if settings.LLM_API_KEY:
        status["llm_status"] = "configured"
    else:
        status["llm_status"] = "no_api_key"
        status["status"] = "degraded"

    # 3. Embedding API 检查
    if settings.EMBEDDING_API_KEY or settings.LLM_API_KEY:
        status["embedding_status"] = "configured"
    else:
        status["embedding_status"] = "no_api_key"
        status["status"] = "degraded"

    # 详细状态
    parts = []
    for k in ("chroma_status", "llm_status", "embedding_status"):
        parts.append(f"{k}={status[k]}")
    status["detail"] = "; ".join(parts)

    return status


# ════════════════════════════════════════════════════════════════
# 注册路由
# ════════════════════════════════════════════════════════════════

for router in routers:
    app.include_router(router, prefix="/api/rag")


# ════════════════════════════════════════════════════════════════
# 直接运行入口
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("RAG_SERVER_PORT", "8100"))
    host = os.getenv("RAG_SERVER_HOST", "0.0.0.0")
    reload = os.getenv("RAG_SERVER_RELOAD", "false").lower() == "true"

    log.info(f"启动 RAG Server → http://{host}:{port}")
    log.info(f"API 文档 → http://{host}:{port}/docs")

    uvicorn.run(
        "smart_doc_search.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
