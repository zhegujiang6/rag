"""检索相关路由."""
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from loguru import logger as log

from services.rag_engine import rag_engine, RetrievalError
from services.embedding_service import embedding_service, LLMError
from rag_server.schemas import (
    SearchRequest, SearchResponse, SearchResultItem,
    ErrorResponse,
)
from rag_server.dependencies import get_db, verify_api_key, verify_kb_ownership

router = APIRouter(tags=["检索"])


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="增强语义检索",
    description="""
执行增强语义检索：查询改写 → 混合搜索 → 重排序 → 父块扩展.

支持所有 RAG 优化特性（按 .env 配置开关控制）.

**安全**: 校验 knowledge_base_id 归属于请求的 user_id，防止跨用户数据泄露.
    """,
    dependencies=[Depends(verify_api_key)],
)
def search(req: SearchRequest, db: Session = Depends(get_db)):
    """增强语义检索 — 返回匹配的子块及其父块上下文."""
    # ── 权限校验 ──────────────────────────────────────────
    verify_kb_ownership(req.knowledge_base_id, req.user_id, db)

    try:
        result = rag_engine.retrieve_enhanced(
            query=req.query,
            knowledge_base_id=req.knowledge_base_id,
            top_k=req.top_k,
            similarity_threshold=req.similarity_threshold,
        )

        items = []
        for r in result.get("results", []):
            items.append(SearchResultItem(
                id=r.get("id", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                metadata=r.get("metadata", {}),
                rerank_score=r.get("rerank_score"),
            ))

        return SearchResponse(
            results=items,
            total=len(items),
            query=req.query,
            knowledge_base_id=req.knowledge_base_id,
            retrieval_details=result.get("debug", {}),
        )

    except LLMError as e:
        log.error(f"检索失败 (LLM): {e}")
        raise HTTPException(status_code=502, detail=f"LLM 服务异常: {str(e)}")
    except RetrievalError as e:
        log.error(f"检索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        log.error(f"检索失败 (未知): {e}")
        raise HTTPException(status_code=500, detail=f"检索服务异常: {str(e)}")


@router.post(
    "/search/with-parents",
    summary="完整检索（含父块上下文 + 来源）",
    description="增强检索 + 父块扩展 + 来源信息，返回可用于 LLM 上下文的完整结果.",
    dependencies=[Depends(verify_api_key)],
)
def search_with_parents(req: SearchRequest, db: Session = Depends(get_db)):
    """完整检索 — 返回父块内容、来源信息、检索调试信息."""
    # ── 权限校验 ──────────────────────────────────────────
    verify_kb_ownership(req.knowledge_base_id, req.user_id, db)

    try:
        result = rag_engine.retrieve_with_parents(
            query=req.query,
            knowledge_base_id=req.knowledge_base_id,
            db=db,
            top_k=req.top_k,
        )

        return {
            "parent_contents": result.get("parent_contents", []),
            "sources": result.get("sources", []),
            "sub_results": result.get("sub_results", []),
            "retrieval_details": result.get("retrieval_details", {}),
        }

    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 服务异常: {str(e)}")
    except RetrievalError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        log.error(f"完整检索失败: {e}")
        raise HTTPException(status_code=500, detail=f"检索服务异常: {str(e)}")
