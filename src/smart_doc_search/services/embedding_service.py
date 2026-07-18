"""嵌入服务 — 调用 OpenAI 兼容的 Embedding API 生成文本向量"""
import base64
import mimetypes
import time
from pathlib import Path
from typing import Dict, List
import httpx
from smart_doc_search.core.config import settings
from smart_doc_search.services.concurrency import embedding_limiter, UpstreamBusyError
from loguru import logger as log


# ============================================================
# 自定义异常类
# ============================================================
class LLMError(Exception):
    """LLM/嵌入服务调用失败时抛出的异常，用于统一处理 API 调用错误"""
    pass


# ============================================================
# 嵌入服务核心类
# ============================================================
class EmbeddingService:
    """嵌入服务核心类，调用 OpenAI 兼容的 Embedding API 生成文本向量"""

    def __init__(self, api_key: str = None, api_base: str = None, model: str = None):
        """初始化嵌入服务，参数优先使用传入值，否则从配置文件读取"""
        # API 密钥：优先使用传入值，其次使用嵌入专用密钥，最后使用通用 LLM 密钥
        self.api_key = api_key or settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        # API 基础地址：去除末尾斜杠
        self.api_base = (api_base or settings.EMBEDDING_API_BASE).rstrip("/")
        # 模型名称
        self.model = model or settings.EMBEDDING_MODEL
        # 向量维度
        self.dimension = settings.EMBEDDING_DIMENSION

    def _get_client(self) -> httpx.Client:
        """创建 HTTP 客户端，配置超时时间和认证头"""
        return httpx.Client(
            timeout=httpx.Timeout(60.0),  # 60秒超时
            headers={
                "Authorization": f"Bearer {self.api_key}",  # Bearer 认证
                "Content-Type": "application/json",         # JSON 格式请求
            },
        )

    # ============================================================
# 单文本嵌入
# ============================================================
    def embed_single(self, text: str) -> List[float]:
        """为单个文本生成嵌入向量，内部调用批量接口"""
        result = self.embed_batch([text])
        return result[0] if result else []

    def embed_multimodal(self, contents: List[Dict[str, str]], max_retries: int = 3) -> List[float]:
        """调用 DashScope qwen3-vl-embedding 生成融合多模态向量。"""
        if not settings.MULTIMODAL_EMBEDDING_ENABLED:
            raise LLMError("多模态向量未启用")
        api_key = settings.MULTIMODAL_EMBEDDING_API_KEY or self.api_key
        if not api_key:
            raise LLMError("MULTIMODAL_EMBEDDING_API_KEY 未配置")
        payload = {"model": settings.MULTIMODAL_EMBEDDING_MODEL, "input": {"contents": contents}, "parameters": {"dimension": settings.MULTIMODAL_EMBEDDING_DIMENSION, "enable_fusion": True}}
        url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"
        for attempt in range(max_retries):
            try:
                with embedding_limiter.acquire(), httpx.Client(timeout=httpx.Timeout(90.0), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}) as client:
                    response = client.post(url, json=payload)
                if response.status_code == 200:
                    vector = response.json().get("output", {}).get("embeddings", [{}])[0].get("embedding", [])
                    if len(vector) != settings.MULTIMODAL_EMBEDDING_DIMENSION:
                        raise LLMError(f"多模态向量维度异常: {len(vector)}")
                    return vector
                if response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise LLMError(f"多模态 Embedding 请求失败: {response.status_code}")
            except UpstreamBusyError as error:
                raise LLMError(str(error))
            except httpx.TimeoutException:
                if attempt == max_retries - 1:
                    raise LLMError("多模态 Embedding 请求超时")
                time.sleep(2 ** attempt)
        raise LLMError("多模态 Embedding 不可用")

    @staticmethod
    def image_as_data_uri(image_path: str) -> str:
        path = Path(image_path)
        mime, _ = mimetypes.guess_type(path.name)
        if mime not in {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}:
            raise LLMError(f"不支持的图片类型: {path.suffix}")
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    # ============================================================
    # 批量文本嵌入（自动分片）
    # ============================================================
    # DashScope 限制每批最多 10 条，OpenAI 兼容 API 一般也是 ≤ 2048 tokens 总量
    MAX_BATCH_SIZE = 10

    def embed_batch(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        """批量生成嵌入向量，自动按 MAX_BATCH_SIZE 拆分为小批以避免 API 限制"""
        if not texts:
            return []

        # 自动拆分为小批处理，合并所有结果
        all_embeddings = []
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i:i + self.MAX_BATCH_SIZE]
            all_embeddings.extend(self._embed_batch_single(batch, max_retries))
        return all_embeddings

    # ============================================================
# 单次批量请求（带重试机制）
# ============================================================
    def _embed_batch_single(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        """发送单次批量请求到嵌入 API，带指数退避重试机制（处理限流、超时、服务端错误）"""
        url = f"{self.api_base}/embeddings"  # 构建完整的 API 地址

        # 循环重试，最多 max_retries 次
        for attempt in range(max_retries):
            try:
                with embedding_limiter.acquire(), self._get_client() as client:
                    # 发送 POST 请求，包含模型名称和输入文本列表
                    response = client.post(url, json={"model": self.model, "input": texts})

                    # 成功响应（HTTP 200）
                    if response.status_code == 200:
                        data = response.json()
                        # 按 index 排序，确保结果顺序与输入文本顺序一致
                        embeddings = sorted(data["data"], key=lambda x: x["index"])
                        # 提取每个文本的嵌入向量
                        return [item["embedding"] for item in embeddings]

                    # 限流错误（HTTP 429）：指数退避重试（等待时间翻倍）
                    elif response.status_code == 429:
                        wait = 2 ** attempt
                        log.warning(f"嵌入 API 限流，{wait}秒后重试 ({attempt + 1}/{max_retries})")
                        time.sleep(wait)

                    # 服务端错误（HTTP 5xx）：指数退避重试
                    elif response.status_code >= 500:
                        wait = 2 ** attempt
                        log.warning(f"嵌入 API 服务端错误 {response.status_code}，{wait}秒后重试")
                        time.sleep(wait)

                    # 其他错误（如认证失败等）：直接抛出异常
                    else:
                        log.error(f"嵌入 API 错误: {response.status_code} - {response.text}")
                        raise LLMError(f"嵌入服务请求失败: {response.status_code}")

            except httpx.TimeoutException:
                # 请求超时：重试（最后一次不重试）
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    log.warning(f"嵌入 API 请求超时，{wait}秒后重试")
                    time.sleep(wait)
                else:
                    raise LLMError("嵌入服务请求超时")

            except LLMError:
                # 自定义异常直接抛出
                raise
            except Exception as e:
                # 其他未知异常：重试（最后一次不重试）
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    log.warning(f"嵌入 API 异常: {e}，{wait}秒后重试")
                    time.sleep(wait)
                else:
                    raise LLMError(f"嵌入服务调用失败: {str(e)}")

        # 所有重试都失败
        raise LLMError("嵌入服务不可用：已达到最大重试次数")


# ============================================================
# 单例实例
# ============================================================
# 创建全局单例，其他模块直接导入使用，避免重复创建客户端
embedding_service = EmbeddingService()
