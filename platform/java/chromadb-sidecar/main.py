"""
ChromaDB Python Sidecar — 为 Java 后端提供向量数据库操作接口。

将此服务部署在 Java 微服务旁边，Java 通过 HTTP/gRPC 调用，
解决 ChromaDB 没有成熟 Java SDK 的问题。

启动: uvicorn main:app --host 0.0.0.0 --port 8001
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
import os

app = FastAPI(
    title="ChromaDB Sidecar",
    description="为 Java 后端提供 ChromaDB 向量数据库操作的 HTTP API",
    version="1.0.0",
)

# ── 全局客户端 ────────────────────────────────────────────────
_chroma_client: Optional[chromadb.PersistentClient] = None


def get_client() -> chromadb.PersistentClient:
    """懒加载 ChromaDB 客户端."""
    global _chroma_client
    if _chroma_client is None:
        persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "/app/chroma_data")
        _chroma_client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


# ── 请求/响应模型 ─────────────────────────────────────────────

class SearchRequest(BaseModel):
    query_embedding: List[float]
    top_k: int = 5
    similarity_threshold: float = 0.5
    where_filter: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    chroma_id: str
    document_id: int
    parent_chunk_id: int
    chunk_index: int
    content: str
    metadata: Dict[str, Any]
    score: float


class AddChunkRequest(BaseModel):
    collection_name: str
    chunks: List[Dict[str, Any]]
    embeddings: List[List[float]]


class DeleteRequest(BaseModel):
    collection_name: str
    document_id: Optional[int] = None
    chunk_ids: Optional[List[str]] = None


# ── API 端点 ─────────────────────────────────────────────────

@app.get("/health")
def health():
    """健康检查."""
    return {"status": "ok", "service": "chromadb-sidecar"}


@app.post("/api/v1/collections/{collection_name}/search")
def search(collection_name: str, request: SearchRequest) -> List[SearchResult]:
    """语义检索 — 按向量相似度搜索子块。

    对应 Java: ChromaDbClient.search()
    """
    # TODO: 实现 ChromaDB 查询逻辑
    # 1. get_or_create_collection(collection_name)
    # 2. collection.query(query_embeddings=[...], n_results=top_k, where=...)
    # 3. 转换为 SearchResult 列表返回
    collection = get_client().get_or_create_collection(collection_name)
    if collection.count() == 0:
        return []
    result = collection.query(query_embeddings=[request.query_embedding], n_results=min(request.top_k, collection.count()), where=request.where_filter, include=["documents", "metadatas", "distances"])
    rows = []
    for chunk_id, content, metadata, distance in zip(result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]):
        score = max(0.0, 1.0 - float(distance))
        if score >= request.similarity_threshold:
            metadata = metadata or {}
            rows.append(SearchResult(chroma_id=chunk_id, document_id=int(metadata["document_id"]), parent_chunk_id=int(metadata["parent_chunk_id"]), chunk_index=int(metadata.get("chunk_index", 0)), content=content or "", metadata=metadata, score=score))
    return rows


@app.post("/api/v1/collections/{collection_name}/add")
def add_embeddings(collection_name: str, request: AddChunkRequest):
    """批量写入向量 — 文档处理管道完成后调用。

    对应 Java: DocumentService.addDocToKb() → ChromaDbClient.addEmbeddings()
    """
    # TODO: 实现 ChromaDB 批量写入
    # 1. get_or_create_collection(collection_name)
    # 2. collection.add(ids=[...], embeddings=[...], documents=[...], metadatas=[...])
    if len(request.chunks) != len(request.embeddings):
        raise HTTPException(status_code=400, detail="chunks and embeddings must have equal length")
    if not request.chunks:
        return {"status": "ok", "count": 0}
    collection = get_client().get_or_create_collection(collection_name)
    collection.upsert(ids=[str(c["chroma_id"]) for c in request.chunks], embeddings=request.embeddings, documents=[str(c["content"]) for c in request.chunks], metadatas=[c.get("metadata", {}) for c in request.chunks])
    return {"status": "ok", "count": len(request.chunks)}


@app.delete("/api/v1/collections/{collection_name}/documents/{document_id}")
def delete_by_document(collection_name: str, document_id: int):
    """按文档 ID 删除向量 — 删除文档时清理 ChromaDB。

    对应 Java: DocumentService.deleteDocument()
    """
    # TODO: 实现按 document_id 删除
    # collection.delete(where={"document_id": document_id})
    get_client().get_or_create_collection(collection_name).delete(where={"document_id": document_id})
    return {"status": "ok"}


@app.delete("/api/v1/collections/{collection_name}")
def delete_collection(collection_name: str):
    """删除整个集合 — 删除知识库时清理。

    对应 Java: KnowledgeBaseService.deleteKb()
    """
    # TODO: 实现删除集合
    # client.delete_collection(collection_name)
    try:
        get_client().delete_collection(collection_name)
    except ValueError:
        pass
    return {"status": "ok"}


@app.get("/api/v1/collections/{collection_name}/count")
def get_count(collection_name: str):
    """获取集合中的向量数量。

    对应 Java: KnowledgeBaseService.getChunkCount()
    """
    # TODO: 返回 collection.count()
    return {"count": get_client().get_or_create_collection(collection_name).count()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
