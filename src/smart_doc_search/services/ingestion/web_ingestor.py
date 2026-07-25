"""网页接入器 — 将网页 URL 转换为 RawDocument.

轻量数据中台 — 第二个适配器实现.
将 WebCrawler 封装为 BaseIngestor 接口，让网页内容与文件内容走相同的 Pipeline.
"""

from smart_doc_search.services.ingestion.base import BaseIngestor, RawDocument, IngestionError
from smart_doc_search.services.web_crawler import web_crawler, CrawlError
from loguru import logger as log


class WebIngestor(BaseIngestor):
    """网页数据源适配器.

    负责：
    1. 调用 WebCrawler 抓取网页内容
    2. 返回统一的 RawDocument 格式
    """

    source_type = "web"

    def ingest(self, source: str) -> RawDocument:
        """从网页 URL 提取正文内容.

        Args:
            source: 网页 URL 字符串（需含协议头）.

        Returns:
            RawDocument: 包含网页正文和元数据.

        Raises:
            IngestionError: 抓取失败时抛出.
        """
        url = source

        log.info(f"WebIngestor: 开始接入网页 '{url}'")

        # ── 调用爬虫抓取 ──
        try:
            result = web_crawler.crawl(url)
        except CrawlError as e:
            raise IngestionError(str(e))

        # ── 构建统一 RawDocument ──
        raw_doc = RawDocument(
            content=result.content,
            source_type=self.source_type,
            source_identifier=url,
            metadata={
                "title": result.title,
                "url": url,
                "fetch_method": result.method,
                "fetched_at": result.fetched_at,
                "content_length": result.content_length,
            },
        )

        log.info(
            f"WebIngestor: 接入完成 | URL: {url} | "
            f"标题: {result.title[:50] if result.title else 'N/A'} | "
            f"字符数: {len(raw_doc.content)} | 方法: {result.method}"
        )
        return raw_doc
