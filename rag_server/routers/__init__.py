"""RAG 服务路由."""
from rag_server.routers.retrieval import router as retrieval_router
from rag_server.routers.chat import router as chat_router

# 所有路由的列表，供 main.py 注册
routers = [retrieval_router, chat_router]
