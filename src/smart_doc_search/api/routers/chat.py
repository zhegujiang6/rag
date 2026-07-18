"""对话相关路由 — RAG 流式生成 + 同步生成."""
import json
import time
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from loguru import logger as log

from smart_doc_search.services.rag_engine import rag_engine, RetrievalError
from smart_doc_search.services.embedding_service import LLMError
from smart_doc_search.api.schemas import ChatRequest, ChatResponse, SourceInfo
from smart_doc_search.api.dependencies import get_db, verify_api_key, verify_kb_ownership

router = APIRouter(tags=["对话"])


# ════════════════════════════════════════════════════════════════
# SSE 流式对话
# ════════════════════════════════════════════════════════════════

@router.post(
    "/chat/stream",
    summary="RAG 流式对话 (SSE)",
    description="""
基于知识库文档的流式对话，使用 Server-Sent Events 推送响应.

事件类型:
- `status`: 状态更新（检索中、生成中...）
- `token`: LLM 生成的文本 token
- `sources`: 最终返回的来源文档信息
- `retrieval_details`: 检索过程调试信息
- `error`: 错误信息
- `done`: 流结束标记

**安全**: 校验 knowledge_base_id 归属于请求的 user_id，防止跨用户数据泄露.
    """,
    dependencies=[Depends(verify_api_key)],
)
def chat_stream(req: ChatRequest, db: Session = Depends(get_db)):
    """SSE 流式 RAG 对话."""
    # ── 权限校验 ──────────────────────────────────────────
    verify_kb_ownership(req.knowledge_base_id, req.user_id, db)

    def generate_events():
        """SSE 事件生成器，将 RAG 引擎输出转换为 SSE 格式."""
        try:
            generator = rag_engine.generate_rag_stream(
                query=req.query,
                knowledge_base_id=req.knowledge_base_id,
                db=db,
                conversation_history=req.conversation_history,
                top_k=req.top_k,
            )

            for chunk in generator:
                event_type = chunk.get("type", "unknown")

                if event_type == "token":
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk['content']}, ensure_ascii=False)}\n\n"

                elif event_type == "status":
                    yield f"data: {json.dumps({'type': 'status', 'content': chunk['content']}, ensure_ascii=False)}\n\n"

                elif event_type == "sources":
                    yield f"data: {json.dumps({'type': 'sources', 'data': chunk['data']}, ensure_ascii=False)}\n\n"

                elif event_type == "contexts":
                    pass  # 不推送给客户端

                elif event_type == "retrieval_details":
                    yield f"data: {json.dumps({'type': 'retrieval_details', 'data': chunk['data']}, ensure_ascii=False)}\n\n"

                elif event_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': chunk['content']}, ensure_ascii=False)}\n\n"
                    return

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except RetrievalError as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'检索失败: {str(e)}'}, ensure_ascii=False)}\n\n"
        except LLMError as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'LLM 服务异常: {str(e)}'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            log.error(f"流式生成失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': f'生成失败: {str(e)}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ════════════════════════════════════════════════════════════════
# 同步对话（非流式）
# ════════════════════════════════════════════════════════════════

@router.post(
    "/chat/sync",
    response_model=ChatResponse,
    summary="RAG 同步对话",
    description="非流式的 RAG 对话，等待完整回答后一次性返回.",
    dependencies=[Depends(verify_api_key)],
)
def chat_sync(req: ChatRequest, db: Session = Depends(get_db)):
    """同步 RAG 对话 — 收集所有 token 后一次性返回."""
    # ── 权限校验 ──────────────────────────────────────────
    verify_kb_ownership(req.knowledge_base_id, req.user_id, db)

    t_start = time.time()

    try:
        generator = rag_engine.generate_rag_stream(
            query=req.query,
            knowledge_base_id=req.knowledge_base_id,
            db=db,
            conversation_history=req.conversation_history,
            top_k=req.top_k,
        )

        answer_parts: List[str] = []
        sources: List[Dict[str, Any]] = []
        retrieval_details: Dict[str, Any] = {}

        for chunk in generator:
            event_type = chunk.get("type", "unknown")

            if event_type == "token":
                answer_parts.append(chunk["content"])
            elif event_type == "sources":
                sources = chunk.get("data", [])
            elif event_type == "retrieval_details":
                retrieval_details = chunk.get("data", {})
            elif event_type == "error":
                raise HTTPException(status_code=500, detail=chunk["content"])

        answer = "".join(answer_parts)
        elapsed = round(time.time() - t_start, 2)
        retrieval_details["timing_total"] = elapsed

        log.info(f"同步对话完成: {len(answer)} chars, {elapsed}s")

        source_items = [
            SourceInfo(
                document_id=s.get("document_id"),
                filename=s.get("filename"),
                page=s.get("page"),
                score=s.get("score"),
                tags=s.get("tags"),
            )
            for s in sources
        ]

        return ChatResponse(
            answer=answer,
            sources=source_items,
            retrieval_details=retrieval_details,
            query=req.query,
            knowledge_base_id=req.knowledge_base_id,
        )

    except HTTPException:
        raise
    except RetrievalError as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {str(e)}")
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 服务异常: {str(e)}")
    except Exception as e:
        log.error(f"同步对话失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")
