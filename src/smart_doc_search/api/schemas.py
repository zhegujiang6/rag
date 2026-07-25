"""Pydantic 请求/响应模型."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# ════════════════════════════════════════════════════════════════
# 请求模型
# ════════════════════════════════════════════════════════════════

class SearchRequest(BaseModel):
    """语义检索请求"""
    query: str = Field(..., description="查询文本", min_length=1, max_length=2000)
    knowledge_base_id: int = Field(..., description="知识库 ID", ge=1)
    user_id: int = Field(..., description="用户 ID（用于权限校验）", ge=1)
    top_k: int = Field(default=5, description="返回结果数量", ge=1, le=50)
    similarity_threshold: float = Field(default=0.5, description="相似度阈值", ge=0.0, le=1.0)


class ChatRequest(BaseModel):
    """RAG 对话请求"""
    query: str = Field(..., description="用户问题", min_length=1, max_length=5000)
    knowledge_base_id: int = Field(..., description="知识库 ID", ge=1)
    user_id: int = Field(..., description="用户 ID（用于权限校验）", ge=1)
    top_k: int = Field(default=5, description="检索结果数量", ge=1, le=20)
    conversation_history: List[Dict[str, str]] = Field(
        default_factory=list,
        description="历史对话 [{'role':'user'|'assistant','content':'...'}]"
    )
    stream: bool = Field(default=True, description="是否流式返回")


class EmbeddingRequest(BaseModel):
    """文本向量化请求"""
    texts: List[str] = Field(..., description="待向量化的文本列表", min_length=1, max_length=100)
    model: Optional[str] = Field(default=None, description="模型名称，为空则使用默认配置")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    chroma_status: str
    llm_status: str
    embedding_status: str
    detail: str


# ════════════════════════════════════════════════════════════════
# 响应模型
# ════════════════════════════════════════════════════════════════

class SearchResultItem(BaseModel):
    """单条检索结果"""
    id: str = ""
    content: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    rerank_score: Optional[float] = None


class SearchResponse(BaseModel):
    """检索响应"""
    results: List[SearchResultItem]
    total: int
    query: str
    knowledge_base_id: int
    retrieval_details: Dict[str, Any] = Field(default_factory=dict)


class SourceInfo(BaseModel):
    """来源信息"""
    document_id: Any = None
    filename: Optional[str] = None
    page: Any = None
    score: Optional[float] = None
    tags: Optional[List[str]] = None


class ChatResponse(BaseModel):
    """同步对话响应"""
    answer: str
    sources: List[SourceInfo] = Field(default_factory=list)
    retrieval_details: Dict[str, Any] = Field(default_factory=dict)
    query: str
    knowledge_base_id: int


class EmbeddingResponse(BaseModel):
    """向量化响应"""
    embeddings: List[List[float]]
    model: str
    dimension: int


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None
