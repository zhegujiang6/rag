"""LLM 客户端 — 调用 OpenAI 兼容的 LLM API，支持同步和流式响应"""
import time
import json
from typing import Generator, List, Dict
import httpx
from config import settings
from loguru import logger as log
from services.embedding_service import LLMError
from services.concurrency import llm_limiter


# ============================================================
# LLM 客户端核心类
# ============================================================
class LLMClient:
    """LLM 客户端核心类，调用 OpenAI 兼容的 LLM API，支持同步和流式响应"""

    def __init__(self, api_key: str = None, api_base: str = None, model: str = None):
        """初始化 LLM 客户端，参数优先使用传入值，否则从配置文件读取"""
        self.api_key = api_key or settings.LLM_API_KEY           # API 密钥
        self.api_base = (api_base or settings.LLM_API_BASE).rstrip("/")  # API 基础地址（去除末尾斜杠）
        self.model = model or settings.LLM_MODEL                 # 模型名称

    def _get_client(self) -> httpx.Client:
        """创建 HTTP 客户端，配置较长的超时时间（LLM 请求可能耗时较长）"""
        return httpx.Client(
            timeout=httpx.Timeout(120.0, connect=10.0),  # 总超时 120 秒，连接超时 10 秒
            headers={
                "Authorization": f"Bearer {self.api_key}",  # Bearer 认证
                "Content-Type": "application/json",         # JSON 格式请求
            },
        )

    # ============================================================
# 同步聊天（用于需要完整响应的场景，如评测/重排序）
# ============================================================
    def chat_sync(
        self, messages: List[Dict[str, str]],
        temperature: float = None, max_tokens: int = None,
        max_retries: int = 3,
    ) -> str:
        """同步聊天补全，等待完整响应后返回。适用于不需要实时显示的场景（如评测、重排序）"""
        # 使用传入参数或配置默认值
        temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        url = f"{self.api_base}/chat/completions"  # 构建 API 地址

        # 循环重试，最多 max_retries 次
        for attempt in range(max_retries):
            try:
                with llm_limiter.acquire(), self._get_client() as client:
                    response = client.post(
                        url,
                        json={
                            "model": self.model,           # 模型名称
                            "messages": messages,          # 消息列表（包含历史对话）
                            "temperature": temperature,    # 温度参数（控制随机性）
                            "max_tokens": max_tokens,      # 最大 token 数
                            "stream": False,               # 非流式响应
                        },
                    )

                    # 成功响应（HTTP 200）
                    if response.status_code == 200:
                        return self._extract_text(response.content)

                    # 限流错误（HTTP 429）：指数退避重试
                    elif response.status_code == 429:
                        wait = 2 ** attempt
                        log.warning(f"LLM 同步 API 限流，{wait}秒后重试")
                        time.sleep(wait)
                    # 服务端错误（HTTP 5xx）：指数退避重试
                    elif response.status_code >= 500:
                        wait = 2 ** attempt
                        log.warning(f"LLM 同步 API 服务端错误 {response.status_code}，{wait}秒后重试")
                        time.sleep(wait)
                    # 其他错误：直接抛出异常
                    else:
                        log.error(f"LLM 同步 API 错误: {response.status_code}")
                        raise LLMError(f"LLM 同步调用失败: HTTP {response.status_code}")

            except httpx.TimeoutException:
                # 请求超时：重试（最后一次不重试）
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    log.warning(f"LLM 同步请求超时，{wait}秒后重试")
                    time.sleep(wait)
                else:
                    raise LLMError("LLM 同步调用超时")
            except LLMError:
                # 自定义异常直接抛出
                raise
            except Exception as e:
                # 其他未知异常：重试（最后一次不重试）
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    log.warning(f"LLM 同步异常: {e}，{wait}秒后重试")
                    time.sleep(wait)
                else:
                    raise LLMError(f"LLM 同步调用失败: {str(e)}")

        # 所有重试都失败
        raise LLMError("LLM 同步服务不可用：已达到最大重试次数")

    # ============================================================
# 流式聊天（Generator）
# ============================================================
    def chat_stream(
        self, messages: List[Dict[str, str]],
        temperature: float = None, max_tokens: int = None,
        max_retries: int = 3,
    ) -> Generator[str, None, None]:
        """流式聊天补全，逐个 token 输出（Generator）。适用于实时显示回答的场景（如聊天界面）"""
        # 使用传入参数或配置默认值
        temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        url = f"{self.api_base}/chat/completions"  # 构建 API 地址

        # 循环重试，最多 max_retries 次
        for attempt in range(max_retries):
            try:
                with llm_limiter.acquire(), self._get_client() as client:
                    # 使用流式请求模式（stream=True）
                    with client.stream(
                        "POST", url,
                        json={
                            "model": self.model,           # 模型名称
                            "messages": messages,          # 消息列表
                            "temperature": temperature,    # 温度参数
                            "max_tokens": max_tokens,      # 最大 token 数
                            "stream": True,                # 启用流式响应
                        },
                    ) as response:
                        if response.status_code == 200:
                            content_type = response.headers.get("content-type", "")

                            # 真正的 SSE 流式响应（text/event-stream）
                            if "text/event-stream" in content_type:
                                # 逐行读取响应
                                for line in response.iter_lines():
                                    if line.startswith("data: "):
                                        data = line[6:].strip()
                                        if data == "[DONE]":
                                            # 流式结束标记
                                            return
                                        try:
                                            chunk = json.loads(data)
                                            # OpenAI 格式：从 choices[0].delta.content 获取内容
                                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                                            content = delta.get("content", "")
                                            # DashScope 格式回退：从 output.text 或 text 获取内容
                                            if not content:
                                                content = chunk.get("output", {}).get("text", "") or chunk.get("text", "")
                                            if content:
                                                # 逐个 token 输出
                                                yield content
                                        except (json.JSONDecodeError, KeyError, IndexError):
                                            # 忽略格式错误的行
                                            continue
                                return
                            else:
                                # 非 SSE 响应（某些 API 返回完整 JSON）—— 模拟流式输出
                                full_body = response.read()
                                text = self._extract_text(full_body)
                                if text:
                                    # 按 8 字符为单位拆分，模拟流式输出
                                    chunk_size = 8
                                    for i in range(0, len(text), chunk_size):
                                        yield text[i:i + chunk_size]
                                        time.sleep(0.01)
                                return

                        # 限流错误（HTTP 429）：指数退避重试
                        elif response.status_code == 429:
                            wait = 2 ** attempt
                            log.warning(f"LLM API 限流，{wait}秒后重试")
                            time.sleep(wait)
                        # 服务端错误（HTTP 5xx）：指数退避重试
                        elif response.status_code >= 500:
                            wait = 2 ** attempt
                            log.warning(f"LLM API 服务端错误 {response.status_code}，{wait}秒后重试")
                            time.sleep(wait)
                        # 其他错误：直接抛出异常
                        else:
                            log.error(f"LLM API 错误: {response.status_code} - {response.text[:200]}")
                            raise LLMError(f"LLM 调用失败: HTTP {response.status_code}")

            except httpx.TimeoutException:
                # 请求超时：重试（最后一次不重试）
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    log.warning(f"LLM API 请求超时，{wait}秒后重试")
                    time.sleep(wait)
                else:
                    raise LLMError("LLM 调用超时")
            except LLMError:
                # 自定义异常直接抛出
                raise
            except Exception as e:
                # 其他未知异常：重试（最后一次不重试）
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    log.warning(f"LLM 流式异常: {e}，{wait}秒后重试")
                    time.sleep(wait)
                else:
                    raise LLMError(f"LLM 调用失败: {str(e)}")

        # 所有重试都失败
        raise LLMError("LLM 服务不可用：已达到最大重试次数")

    # ============================================================
# 文本提取（兼容多种 API 响应格式）
# ============================================================
    def _extract_text(self, raw_body: bytes) -> str:
        """从 API 响应中提取文本内容，兼容 OpenAI、DashScope 等多种格式"""
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            # JSON 解析失败，直接返回原始文本
            return raw_body.decode("utf-8", errors="replace")

        # OpenAI 格式：从 choices[0].message.content 提取
        if "choices" in data:
            choices = data["choices"]
            if choices:
                return (choices[0].get("message", {}).get("content", "") or
                        choices[0].get("delta", {}).get("content", "") or
                        choices[0].get("text", ""))

        # DashScope 格式：从 text 或 output.text 提取
        if "text" in data:
            return data["text"]
        if "output" in data:
            output = data["output"]
            if isinstance(output, dict):
                return output.get("text", "")
            return str(output)

        # 未知格式：记录警告并返回原始文本
        log.warning(f"未知的 LLM 响应格式: {list(data.keys())}")
        return raw_body.decode("utf-8", errors="replace")


# ============================================================
# 单例实例
# ============================================================
# 创建全局单例，其他模块直接导入使用，避免重复创建客户端
llm_client = LLMClient()
