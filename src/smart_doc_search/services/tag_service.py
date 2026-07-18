"""文档标签服务 — 自动提取与基于标签的搜索增强.

功能:
  1. LLM 自动标签: 从文档内容提取关键词/分类
  2. 标签 CRUD: 为文档添加/删除/列出标签
  3. 标签筛选: 按标签过滤文档
  4. 标签增强: 对标签匹配的文档块提升检索分数
"""
from typing import List, Dict, Any, Optional, Set

from sqlalchemy import or_
from sqlalchemy.orm import Session
from loguru import logger as log

from smart_doc_search.data.database import Document, SessionLocal
from smart_doc_search.services.llm_client import llm_client
from smart_doc_search.core.config import settings


# ============================================================
# Prompt Templates
# ============================================================

TAG_EXTRACTION_PROMPT = """你是一个文档分类专家。请从以下文档内容中提取3-5个高质量标签关键词。

严格规则:
1. 只提取有区分度的专有名词、技术术语、特定概念——能让人一看到标签就知道这篇文档讲什么
2. 禁止这些泛词: "文档"、"报告"、"指南"、"教程"、"介绍"、"技术"、"计算机"、"软件"、"编程"、"开发"、"学习"、"资料"、"总结"、"笔记"、"整理"、"基础"、"入门"、"进阶"、"原理"、"方法"、"应用"、"实践"、"分析"、"研究"、"设计"、"实现"、"系统"、"框架"、"工具"、"平台"、"管理"、"项目"、"工程"
3. 宁可少也不要滥——如果内容涉及面窄，只输出1-2个精准标签即可
4. 每个标签2-12个字，使用中文
5. 输出格式: 逗号分隔，不要编号、不要解释

文档内容:
{content}

只输出标签（逗号分隔）:"""


# ============================================================
# Tag Service
# ============================================================

class TagService:
    """文档标签管理与自动提取."""

    MAX_AUTO_TAGS = 5
    AUTO_TAG_CHUNK_SIZE = 1500  # 发送给 LLM 的每个样本字符数

    # ── 自动提取 ────────────────────────────────────────

    def auto_extract(self, content: str) -> List[str]:
        """使用 LLM 从文档内容中提取标签.

        从文档的多个位置采样以提高覆盖率:
        - 开头（前 ~1500 字符）
        - 中间（~1500 字符）
        - 后半段（~1000 字符，文档后三分之一）

        Args:
            content: 文档文本.

        Returns:
            经过验证的标签字符串列表.
        """
        if not content or len(content) < 50:
            return []

        # 多位置采样以提高文档覆盖率
        samples = [content[:self.AUTO_TAG_CHUNK_SIZE]]

        if len(content) > self.AUTO_TAG_CHUNK_SIZE * 2:
            mid = len(content) // 2
            samples.append(content[mid:mid + self.AUTO_TAG_CHUNK_SIZE])

        if len(content) > self.AUTO_TAG_CHUNK_SIZE * 4:
            third = len(content) * 2 // 3
            samples.append(content[third:third + 1000])

        content_sample = "\n\n---\n\n".join(samples)

        prompt = TAG_EXTRACTION_PROMPT.format(content=content_sample)
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = llm_client.chat_sync(messages, temperature=0.3, max_tokens=200)
            tags = self._parse_tag_list(raw)
            tags = self._filter_quality(tags)
            log.info(f"TagService: auto-extracted {len(tags)} tags: {tags}")
            return tags[:self.MAX_AUTO_TAGS]
        except Exception as e:
            log.warning(f"TagService: auto-extraction failed: {e}")
            return []

    def _parse_tag_list(self, raw: str) -> List[str]:
        """解析 LLM 输出中的逗号/换行分隔的标签列表."""
        import re
        tags = []
        # 按常见分隔符分割
        for part in re.split(r'[,，、\n]', raw):
            tag = re.sub(r'^[\d]+[\.\、\)\-]\s*', '', part.strip())
            tag = tag.strip().strip('"').strip("'").strip("。")
            if tag and 1 < len(tag) <= 20 and tag not in tags:
                tags.append(tag)
        return tags

    # ── 质量过滤: 去除无用的泛化标签 ─────────────
    # 禁用标签: 过于泛化，对检索/筛选没有帮助
    _BANNED_TAGS: Set[str] = {
        "文档", "报告", "指南", "教程", "介绍", "说明",
        "技术", "计算机", "软件", "编程", "开发", "学习", "资料",
        "总结", "笔记", "整理", "基础", "入门", "进阶",
        "原理", "方法", "应用", "实践", "分析", "研究",
        "设计", "实现", "系统", "框架", "工具", "平台",
        "管理", "项目", "工程", "解决方案", "概述",
        # English equivalents that LLM sometimes outputs
        "document", "report", "guide", "tutorial", "introduction",
        "technology", "software", "programming", "development",
    }

    def _filter_quality(self, tags: List[str]) -> List[str]:
        """移除禁用的泛化标签和重复项."""
        result = []
        for tag in tags:
            lower = tag.strip().lower()
            # 跳过禁用标签
            if lower in self._BANNED_TAGS:
                log.debug(f"TagService: filtered out generic tag '{tag}'")
                continue
            # 跳过单个字符或纯数字
            if len(tag) <= 1 or tag.isdigit():
                continue
            # 去重
            if tag not in result:
                result.append(tag)
        return result

    # ── 为文档自动打标签并持久化 ────────────────────────

    def auto_tag_document(
        self, doc_id: int, content: str, db: Session = None
    ) -> List[str]:
        """为文档提取标签并保存到数据库.

        将自动提取的标签与已有的手动标签合并.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return []

            auto_tags = self.auto_extract(content)

            # Merge with existing manual tags (preserve them)
            existing = list(doc.tags or [])
            manual_tags = [
                t for t in existing
                if isinstance(t, dict) and t.get("source") == "manual"
            ]

            # Build new tag list: manual (preserved) + auto (new)
            new_tags = manual_tags
            for tag in auto_tags:
                # Check if already present (as manual or auto)
                existing_names = {
                    t.get("name", t) if isinstance(t, dict) else t
                    for t in new_tags
                }
                if tag not in existing_names:
                    new_tags.append({"name": tag, "source": "auto"})

            doc.tags = new_tags
            db.commit()
            return auto_tags

        except Exception as e:
            log.error(f"TagService: auto_tag_document failed: {e}")
            if should_close:
                db.rollback()
            return []
        finally:
            if should_close:
                db.close()

    # ── 手动标签管理 ─────────────────────────────────

    def add_tag(
        self, doc_id: int, tag_name: str, db: Session = None
    ) -> bool:
        """为文档添加手动标签."""
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return False

            tags = list(doc.tags or [])
            tag_name = tag_name.strip()

            # Don't add duplicates
            for t in tags:
                name = t.get("name", t) if isinstance(t, dict) else t
                if name == tag_name:
                    return True

            tags.append({"name": tag_name, "source": "manual"})
            doc.tags = tags
            db.commit()
            return True

        except Exception as e:
            log.error(f"TagService: add_tag failed: {e}")
            return False
        finally:
            if should_close:
                db.close()

    def remove_tag(
        self, doc_id: int, tag_name: str, db: Session = None
    ) -> bool:
        """从文档中移除标签."""
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return False

            tags = list(doc.tags or [])
            new_tags = []
            removed = False
            for t in tags:
                name = t.get("name", t) if isinstance(t, dict) else t
                if name == tag_name:
                    removed = True
                else:
                    new_tags.append(t)

            if removed:
                doc.tags = new_tags if new_tags else None
                db.commit()
            return removed

        except Exception as e:
            log.error(f"TagService: remove_tag failed: {e}")
            return False
        finally:
            if should_close:
                db.close()

    # ── 批量操作 ──────────────────────────────────────

    def get_all_tags(
        self, user_id: int = None, db: Session = None
    ) -> List[Dict[str, Any]]:
        """获取所有文档中的唯一标签及其使用次数.

        Returns:
            {name, count, sources} 字典列表.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            query = db.query(Document)
            if user_id:
                query = query.filter(Document.user_id == user_id)

            docs = query.filter(Document.tags.isnot(None)).all()

            tag_counts: Dict[str, Dict] = {}
            for doc in docs:
                for t in (doc.tags or []):
                    name = t.get("name", t) if isinstance(t, dict) else t
                    source = t.get("source", "manual") if isinstance(t, dict) else "manual"
                    if name not in tag_counts:
                        tag_counts[name] = {"name": name, "count": 0, "sources": set()}
                    tag_counts[name]["count"] += 1
                    tag_counts[name]["sources"].add(source)

            # Convert sets to lists for JSON serialization
            result = [
                {"name": v["name"], "count": v["count"], "sources": list(v["sources"])}
                for v in tag_counts.values()
            ]
            result.sort(key=lambda x: x["count"], reverse=True)
            return result

        finally:
            if should_close:
                db.close()

    def filter_by_tags(
        self, tags: List[str], user_id: int = None, db: Session = None
    ) -> List[int]:
        """查找包含所有指定标签的文档 ID.

        Returns:
            文档 ID 列表.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            query = db.query(Document)
            if user_id:
                query = query.filter(Document.user_id == user_id)

            docs = query.filter(Document.tags.isnot(None)).all()

            doc_ids = []
            for doc in docs:
                doc_tag_names = {
                    t.get("name", t) if isinstance(t, dict) else t
                    for t in (doc.tags or [])
                }
                if all(t in doc_tag_names for t in tags):
                    doc_ids.append(doc.id)

            return doc_ids

        finally:
            if should_close:
                db.close()

    # ── 检索时的标签增强 ────────────────────────────

    def compute_tag_boost(
        self, query: str, doc_id: int, base_score: float, db: Session = None
    ) -> float:
        """基于标签与查询的重叠度提升检索分数.

        如果文档的标签出现在查询文本中，则提升分数.
        增强因子: 1.0 + 0.15 * (匹配标签数)，上限为 1.3.

        Args:
            query: 用户查询字符串.
            doc_id: 文档 ID.
            base_score: 原始检索分数.
            db: 数据库会话.

        Returns:
            增强后的分数.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc or not doc.tags:
                return base_score

            matching = 0
            for t in doc.tags:
                name = t.get("name", t) if isinstance(t, dict) else t
                if name in query:
                    matching += 1

            if matching == 0:
                return base_score

            boost = min(1.0 + 0.15 * matching, 1.3)
            boosted = base_score * boost
            log.debug(
                f"Tag boost: doc#{doc_id} {matching} tags matched, "
                f"{base_score:.3f} → {boosted:.3f}"
            )
            return boosted

        finally:
            if should_close:
                db.close()


# ============================================================
# Singleton
# ============================================================

tag_service = TagService()
