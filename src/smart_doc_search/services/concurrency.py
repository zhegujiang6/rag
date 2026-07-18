"""进程内并发隔离，保护昂贵且有配额限制的外部模型调用。"""
from contextlib import contextmanager
from threading import BoundedSemaphore

from smart_doc_search.core.config import settings

class UpstreamBusyError(Exception):
    """上游模型并发槽位在规定等待时间内未释放。"""


class UpstreamLimiter:
    def __init__(self, limit: int, name: str):
        self._semaphore = BoundedSemaphore(limit)
        self._name = name

    @contextmanager
    def acquire(self):
        acquired = self._semaphore.acquire(timeout=settings.UPSTREAM_QUEUE_TIMEOUT_SECONDS)
        if not acquired:
            raise UpstreamBusyError(f"{self._name} 当前请求过多，请稍后重试")
        try:
            yield
        finally:
            self._semaphore.release()


llm_limiter = UpstreamLimiter(settings.LLM_MAX_CONCURRENCY, "LLM")
embedding_limiter = UpstreamLimiter(settings.EMBEDDING_MAX_CONCURRENCY, "Embedding")
