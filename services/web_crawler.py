"""网页爬取核心 — 抓取 URL 并提取正文纯文本.

轻量数据中台 — 网页数据源接入的前置模块.

策略:
  主力: requests + readability-lxml (自动提取正文，去广告/导航/侧栏)
  降级: playwright 渲染后多策略提取

动态页面多策略提取:
  1. readability-lxml           — 博客/文章页
  2. 结构化卡片提取              — 列表/卡片式页面（职位、商品、新闻）
  3. 语义 HTML 区域              — <main>/<article>
  4. 可见文本 + 轻度清洗          — 兜底
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests
from loguru import logger as log


# ============================================================
# 爬虫异常
# ============================================================

class CrawlError(Exception):
    """网页爬取失败时抛出的异常."""
    pass


# ============================================================
# 爬取结果
# ============================================================

@dataclass
class CrawlResult:
    """单次网页爬取的结果."""
    url: str
    title: str
    content: str                         # 提取的正文纯文本
    content_length: int
    method: str                          # "static" | "dynamic"
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============================================================
# 网页爬虫
# ============================================================

class WebCrawler:
    """网页爬虫 — 抓取 URL 并提取可读的正文文本.

    Usage:
        crawler = WebCrawler()
        result = crawler.crawl("https://example.com/article")
    """

    # ── 配置 ────────────────────────────────────────────
    TIMEOUT = 15
    MIN_CONTENT_LENGTH = 100
    MAX_CONTENT_LENGTH = 100_000

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }

    # ── 公共入口 ────────────────────────────────────────

    def crawl(self, url: str) -> CrawlResult:
        """抓取指定 URL，返回提取的正文内容."""
        url = self._normalize_url(url)
        log.info(f"WebCrawler: 开始抓取 {url}")

        static_err = None
        try:
            return self._fetch_static(url)
        except CrawlError as e:
            static_err = e
            log.warning(f"WebCrawler: 静态抓取失败 ({e})，尝试动态降级...")

        try:
            return self._fetch_dynamic(url)
        except CrawlError as dynamic_err:
            log.error(f"WebCrawler: 动态抓取也失败 ({dynamic_err})")
            raise CrawlError(
                f"无法抓取该网页: {url}\n"
                f"  静态抓取: {static_err}\n"
                f"  动态抓取: {dynamic_err}"
            )

    # ── 静态抓取 ────────────────────────────────────────

    def _fetch_static(self, url: str) -> CrawlResult:
        """requests + readability-lxml 提取正文."""
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=self.TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            if resp.encoding and resp.encoding.lower() != "utf-8":
                resp.encoding = resp.apparent_encoding or "utf-8"
            html = resp.text
            text, title = self._html_to_text(html, url)
            if len(text) < self.MIN_CONTENT_LENGTH:
                raise CrawlError(f"提取到的正文字数过少 ({len(text)} 字符)，可能为 JS 动态渲染页面")
            log.info(f"WebCrawler: 静态抓取成功 | {len(text)} 字符 | 标题: {title[:50] if title else 'N/A'}")
            return CrawlResult(url=url, title=title, content=text, content_length=len(text), method="static")
        except requests.RequestException as e:
            raise CrawlError(f"HTTP 请求失败: {e}")
        except CrawlError:
            raise
        except Exception as e:
            raise CrawlError(f"静态抓取异常: {e}")

    # ── 动态抓取（playwright）───────────────────────────

    def _fetch_dynamic(self, url: str) -> CrawlResult:
        """playwright 渲染 → 多策略提取正文."""
        import time as _time
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise CrawlError("playwright 未安装，无法处理动态页面。请运行: pip install playwright && playwright install chromium")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=30_000)
                _time.sleep(2)
                self._scroll_to_load(page)
                html = page.content()
                page_title = page.title()

                # ── 策略 1: readability-lxml（文章/博客）──
                text, title = self._html_to_text(html, url)
                title = title or page_title

                # 如果 readability 已经拿到足够内容 → 直接用
                if len(text) >= 500:
                    browser.close()
                    log.info(f"WebCrawler: 动态抓取成功 (readability) | {len(text)} 字符 | 标题: {title[:50]}")
                    return CrawlResult(url=url, title=title, content=text, content_length=len(text), method="dynamic")

                # ── 策略 2: 结构化卡片（列表/卡片式页面）──
                log.info("WebCrawler: readability 不足，尝试结构化卡片提取")
                card_text = self._extract_cards(page, title)
                if card_text and len(card_text) > 200:
                    browser.close()
                    log.info(f"WebCrawler: 动态抓取成功 (cards) | {len(card_text)} 字符")
                    return CrawlResult(url=url, title=title, content=card_text, content_length=len(card_text), method="dynamic")

                # ── 策略 3: 语义区域 + 可见文本 ──
                semantic = self._extract_semantic_area(page)
                visible = ""
                try:
                    raw = page.evaluate("() => document.body.innerText")
                    if raw:
                        visible = self._clean_visible_text(raw)
                except Exception:
                    pass

                # 选最好的
                for candidate_text in [semantic, visible]:
                    if candidate_text and len(candidate_text) > len(text):
                        text = candidate_text

                browser.close()

                if not text.strip():
                    raise CrawlError("所有提取策略均未获得有效内容")
                if len(text) > self.MAX_CONTENT_LENGTH:
                    text = text[:self.MAX_CONTENT_LENGTH] + "\n\n...(内容已截断)"

                log.info(f"WebCrawler: 动态抓取成功 | {len(text)} 字符 | 标题: {title[:50]}")
                return CrawlResult(url=url, title=title, content=text, content_length=len(text), method="dynamic")

        except CrawlError:
            raise
        except Exception as e:
            raise CrawlError(f"动态抓取异常: {e}")

    # ── 策略 2: 结构化卡片提取 ───────────────────────

    def _extract_cards(self, page, fallback_title: str = "") -> str:
        """检测重复的卡片/列表项并结构化提取每个条目.

        对职位列表、商品列表、新闻列表等卡片式页面效果最好.
        工作原理:
        1. 找到页面中重复出现的容器（同类 class 的元素 >= 3 个）
        2. 提取每个容器内的标题和正文文本
        3. 按"卡片"格式输出
        """
        try:
            cards = page.evaluate("""
                () => {
                    // 找到所有可能是"卡片"的容器 —— 同 class 出现 >= 3 次的元素
                    const allElements = document.querySelectorAll('div, li, article, section');
                    const classCounts = {};
                    allElements.forEach(el => {
                        const cls = el.className && typeof el.className === 'string'
                            ? el.className.trim() : '';
                        if (cls && cls.length > 5 && !cls.includes('header') && !cls.includes('footer')
                            && !cls.includes('nav') && !cls.includes('menu') && !cls.includes('sidebar')) {
                            classCounts[cls] = (classCounts[cls] || 0) + 1;
                        }
                    });

                    // 找出现次数最多（>=3）且子元素丰富的类名
                    let bestCls = '';
                    let bestScore = 0;
                    for (const [cls, count] of Object.entries(classCounts)) {
                        if (count >= 3) {
                            const sample = document.querySelector('.' + cls.replace(/\\s+/g, '.'));
                            if (sample && sample.children.length >= 2) {
                                const textLen = (sample.innerText || '').length;
                                const score = count * 10 + Math.min(textLen, 500);
                                if (score > bestScore) {
                                    bestScore = score;
                                    bestCls = cls;
                                }
                            }
                        }
                    }

                    if (!bestCls) return [];

                    // 提取每个卡片
                    const selector = '.' + bestCls.split(/\\s+/).join('.');
                    const items = document.querySelectorAll(selector);
                    return Array.from(items).map(el => {
                        // 提取卡片内的标题（h1-h6 或带 title/name class 的元素）
                        const titleEl = el.querySelector('h1, h2, h3, h4, h5, h6, [class*="title"], [class*="name"], [class*="Title"], [class*="Name"], strong');
                        const title = titleEl ? titleEl.innerText.trim() : '';
                        const fullText = (el.innerText || '').trim();
                        return { title, text: fullText };
                    }).filter(c => c.text.length > 30);
                }
            """)

            if not cards or len(cards) < 2:
                return ""

            # 格式化输出
            parts = []
            for i, card in enumerate(cards):
                # 用卡片标题或第一行作为标题
                title_line = card.get("title", "")
                body = card.get("text", "")

                # 如果标题和正文开头重复，去掉正文开头的标题
                if title_line and body.startswith(title_line):
                    body = body[len(title_line):].strip()

                # 如果正文就是标题（无额外内容），只保留标题
                if not body or body == title_line:
                    parts.append(f"## {title_line}")
                else:
                    parts.append(f"## {title_line}\n{body}")

            result = "\n\n---\n\n".join(parts)
            return result

        except Exception as e:
            log.debug(f"WebCrawler: 卡片提取失败: {e}")
            return ""

    # ── 页面滚动 ─────────────────────────────────────

    @staticmethod
    def _scroll_to_load(page, max_scrolls: int = 5, delay: float = 0.8):
        """滚动页面触发懒加载."""
        try:
            prev_height = 0
            for i in range(max_scrolls):
                page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {(i+1)/max_scrolls})")
                time.sleep(delay)
                new_height = page.evaluate("() => document.body.scrollHeight")
                if new_height == prev_height:
                    break
                prev_height = new_height
        except Exception:
            pass

    # ── 语义区域 ─────────────────────────────────────

    def _extract_semantic_area(self, page) -> str:
        selectors = ["main", "[role='main']", "article", ".content", ".main-content", ".post-content", ".article-content", ".page-content"]
        parts = []
        for sel in selectors:
            try:
                elements = page.evaluate(f"""
                    () => {{
                        const els = document.querySelectorAll('{sel}');
                        return Array.from(els).map(el => el.innerText || '');
                    }}
                """)
                for text in elements:
                    if text and len(text) > 50:
                        parts.append(text)
                if parts:
                    break
            except Exception:
                continue
        return "\n\n".join(parts) if parts else ""

    # ── HTML → 纯文本 ───────────────────────────────────

    def _html_to_text(self, html: str, url: str) -> tuple:
        from readability import Document as ReadabilityDoc
        from lxml import etree
        try:
            doc = ReadabilityDoc(html, url=url)
            title = doc.title() or ""
            content_html = doc.summary()
            text = self._strip_html(content_html)
            if len(text) > self.MAX_CONTENT_LENGTH:
                text = text[:self.MAX_CONTENT_LENGTH] + "\n\n...(内容已截断)"
            return text.strip(), title.strip()
        except Exception as e:
            log.warning(f"readability 提取失败: {e}，降级为简单文本提取")
            try:
                tree = etree.HTML(html)
                title = ""
                title_el = tree.xpath("//title/text()")
                if title_el:
                    title = title_el[0]
                for bad in tree.xpath("//script|//style|//nav|//footer|//header"):
                    bad.getparent().remove(bad) if bad.getparent() is not None else None
                body = tree.xpath("//body")
                text = self._strip_html(etree.tostring(body[0], encoding="unicode", method="html")) if body else self._strip_html(html)
                return text.strip(), title.strip()
            except Exception:
                return "", ""

    @staticmethod
    def _strip_html(html: str) -> str:
        """HTML → 纯文本，保留段落和标题结构."""
        from lxml import etree
        try:
            tree = etree.HTML(html)
        except Exception:
            text = re.sub(r'<br\s*/?>', '\n', html)
            text = re.sub(r'</p>|</div>|</h\d>|</li>|</tr>', '\n', text)
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text

        for br in tree.xpath("//br"):
            br.tail = ("\n" + (br.tail or ""))
        for tag_name in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "section", "article"):
            for el in tree.xpath(f"//{tag_name}"):
                el.tail = ("\n" + (el.tail or ""))
        for i, tag in enumerate(("h1", "h2", "h3", "h4", "h5", "h6")):
            for el in tree.xpath(f"//{tag}"):
                el.text = (f"\n{'#' * (i + 1)} " + (el.text or ""))

        text = ""
        for el in tree.iter():
            if el.text:
                text += el.text
            if el.tail:
                text += el.tail

        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text

    # ── 可见文本清洗 ──────────────────────────────────

    @staticmethod
    def _clean_visible_text(text: str) -> str:
        """轻度清洗 — 去掉明显 UI 元素，保留有信息密度的内容."""
        noise_exact = {
            "首页", "登录", "注册", "反馈", "举报", "回到顶部", "返回顶部",
            "展开", "收起", "查看更多", "加载更多", "重置",
            "确定", "取消", "保存", "提交", "搜索", "清空",
            "分享", "收藏", "点赞", "评论", "发送",
        }
        noise_prefixes = ("Copyright", "©", "All Rights", "京ICP", "沪ICP", "粤ICP", "Powered by", "Created by")

        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append("")
                continue
            if stripped in noise_exact:
                continue
            if len(stripped) <= 1 or stripped.isdigit():
                continue
            if any(stripped.startswith(p) for p in noise_prefixes) and len(stripped) < 40:
                continue
            cleaned.append(stripped)

        text = "\n".join(cleaned)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        text = re.sub(r"^\n+", "", text)
        text = re.sub(r"\n+$", "", text)
        return text

    # ── URL 规范化 ──────────────────────────────────────

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url


# ============================================================
# 单例
# ============================================================

web_crawler = WebCrawler()
