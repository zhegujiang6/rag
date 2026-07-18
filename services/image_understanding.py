"""图片理解服务：把文档图片转写为可检索的文字。"""
from typing import List

from config import settings
from services.embedding_service import embedding_service, LLMError
from services.llm_client import LLMClient
from loguru import logger as log


class ImageUnderstandingService:
    """通过视觉模型识别图片中的文字、表格、图表和关键信息。"""

    PROMPT = """请解析这张文档图片，使其可用于知识库检索。
1. 完整转写清晰可见的文字、代码、数字和标题；
2. 表格按“列名 | 列名”及“值 | 值”的 Markdown 文本形式输出；
3. 图表说明坐标、图例、关键趋势和数值；
4. 不要添加图片中不存在的内容。只输出解析结果，不要寒暄。"""

    def describe_image(self, image_path: str) -> str:
        if not settings.VISION_PARSING_ENABLED:
            return ""

        client = LLMClient(
            api_key=settings.VISION_API_KEY or settings.LLM_API_KEY,
            api_base=settings.VISION_API_BASE or settings.LLM_API_BASE,
            model=settings.VISION_MODEL,
        )
        message: List[dict] = [{
            "role": "user",
            "content": [
                {"type": "text", "text": self.PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": embedding_service.image_as_data_uri(image_path)},
                },
            ],
        }]
        text = client.chat_sync(message, temperature=0, max_tokens=settings.VISION_MAX_TOKENS)
        text = (text or "").strip()
        if text:
            log.info(f"图片内容识别完成: {image_path} | {len(text)} 字符")
        return text


image_understanding_service = ImageUnderstandingService()
