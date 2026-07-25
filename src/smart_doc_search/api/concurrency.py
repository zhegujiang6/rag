"""FastAPI 层的请求并发上限，SSE 连接会一直占用槽位直到流结束。"""
import asyncio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RequestConcurrencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_concurrency: int, queue_timeout_seconds: float):
        super().__init__(app)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.queue_timeout_seconds = queue_timeout_seconds

    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/api/rag/"):
            return await call_next(request)
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=self.queue_timeout_seconds)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=429, content={"error": "RAG 服务繁忙，请稍后重试"}, headers={"Retry-After": "2"})

        released = False
        try:
            response = await call_next(request)
            original_iterator = response.body_iterator

            async def release_after_stream():
                nonlocal released
                try:
                    async for chunk in original_iterator:
                        yield chunk
                finally:
                    if not released:
                        released = True
                        self.semaphore.release()

            response.body_iterator = release_after_stream()
            return response
        except Exception:
            if not released:
                released = True
                self.semaphore.release()
            raise
