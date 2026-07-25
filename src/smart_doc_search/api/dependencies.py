"""依赖注入 — 数据库会话、认证、权限校验."""
import os
from typing import Generator

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session
from loguru import logger as log

from smart_doc_search.data.database import SessionLocal, KnowledgeBase


# ════════════════════════════════════════════════════════════════
# 数据库会话
# ════════════════════════════════════════════════════════════════

def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖: 为每个请求提供一个数据库会话，请求结束时自动关闭."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════
# API Key 认证（内部服务间调用）
# ════════════════════════════════════════════════════════════════

# 从环境变量读取，未设置时默认允许所有请求
_API_KEY = os.getenv("RAG_API_KEY", "")


async def verify_api_key(request: Request, x_api_key: str = Header(default="", alias="X-API-Key")):
    """验证 API Key（如果配置了的话）.

    未配置 RAG_API_KEY 环境变量时，跳过验证（开发模式）.
    配置后，请求必须携带匹配的 X-API-Key 头.
    """
    if not _API_KEY:
        # 未配置密钥 = 开发模式，允许所有请求
        return True

    if not x_api_key:
        raise HTTPException(status_code=401, detail="缺少 X-API-Key 请求头")

    # 常量时间比较（防止时序攻击）
    import hmac
    if not hmac.compare_digest(x_api_key, _API_KEY):
        raise HTTPException(status_code=403, detail="API Key 无效")

    return True


# ════════════════════════════════════════════════════════════════
# 知识库所有权校验
# ════════════════════════════════════════════════════════════════

def verify_kb_ownership(
    knowledge_base_id: int, user_id: int, db: Session
) -> KnowledgeBase:
    """校验知识库归属于指定用户，不通过则抛 403.

    这是数据隔离的核心防线：
    - 用户 A 无法通过猜测 knowledge_base_id 访问用户 B 的知识库
    - ChromaDB 按 kb_{id} 分区，但 MySQL 存储了 kb.user_id 归属
    - 每次检索/对话前校验，防止跨用户数据泄露

    Returns:
        知识库对象（调用方可复用，避免重复查询）
    """
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == knowledge_base_id
    ).first()

    if kb is None:
        log.warning(f"权限校验: 知识库 kb_id={knowledge_base_id} 不存在")
        raise HTTPException(
            status_code=404,
            detail=f"知识库 {knowledge_base_id} 不存在",
        )

    if kb.user_id != user_id:
        log.warning(
            f"权限拒绝: user_id={user_id} 尝试访问 kb_id={knowledge_base_id} "
            f"(实际归属 user_id={kb.user_id})"
        )
        raise HTTPException(
            status_code=403,
            detail="无权访问该知识库",
        )

    log.debug(f"权限通过: user_id={user_id} → kb_id={knowledge_base_id}")
    return kb
