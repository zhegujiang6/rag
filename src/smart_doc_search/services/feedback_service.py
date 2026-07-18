"""用户反馈收集服务.

记录对生成答案的显式反馈（点赞/点踩）和隐式反馈（重新生成、复制）.
这些数据用于 RAG 质量监控的持续改进循环.

反馈存储在 `feedback` 表中（见 database.py）.
"""
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger as log

from smart_doc_search.data.database import Feedback, SessionLocal


# ============================================================
# Feedback Service
# ============================================================

class FeedbackService:
    """收集和聚合用户对 RAG 答案的反馈."""

    # ── 记录反馈 ───────────────────────────────────────────────

    def record(
        self,
        message_id: int,
        rating: int,
        feedback_type: str = "",
        user_id: int = 1,
        comment: str = None,
        db: Session = None,
    ) -> Optional[int]:
        """记录反馈事件.

        Args:
            message_id: 被评分的消息 ID.
            rating: -1（负面）, 0（中性）, 1（正面）.
            feedback_type: 'thumbs_up', 'thumbs_down', 'regenerate', 'copy'.
            user_id: 提供反馈的用户（默认=1）.
            comment: 可选的文本评论.
            db: 数据库会话（未提供则自动创建）.

        Returns:
            成功时返回反馈 ID，失败返回 None.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            # 检查该用户是否已对这条消息提供过反馈
            existing = db.query(Feedback).filter(
                Feedback.message_id == message_id,
                Feedback.user_id == user_id,
            ).first()

            if existing:
                # 更新已存在的反馈
                existing.rating = rating
                existing.feedback_type = feedback_type
                if comment:
                    existing.comment = comment
                db.commit()
                log.info(
                    f"Feedback updated: msg={message_id}, "
                    f"rating={rating}, type={feedback_type}"
                )
                return existing.id
            else:
                # 创建新反馈
                fb = Feedback(
                    message_id=message_id,
                    user_id=user_id,
                    rating=rating,
                    feedback_type=feedback_type,
                    comment=comment,
                )
                db.add(fb)
                db.commit()
                log.info(
                    f"Feedback recorded: msg={message_id}, "
                    f"rating={rating}, type={feedback_type}"
                )
                return fb.id

        except Exception as e:
            log.error(f"Failed to record feedback: {e}")
            if should_close:
                db.rollback()
            return None
        finally:
            if should_close:
                db.close()

    # ── 聚合统计 ─────────────────────────────────────────────

    def get_stats(
        self, knowledge_base_id: int = None, db: Session = None, days: int = 30
    ) -> dict:
        """获取聚合的反馈统计数据.

        Args:
            knowledge_base_id: 按知识库筛选（可选）.
            db: 数据库会话.
            days: 回溯天数窗口.

        Returns:
            包含 total, positive, negative, neutral 计数和 avg_rating 的字典.
        """
        should_close = db is None
        if db is None:
            db = SessionLocal()

        try:
            from datetime import datetime, timedelta
            cutoff = datetime.utcnow() - timedelta(days=days)

            query = db.query(Feedback).filter(
                Feedback.created_at >= cutoff
            )

            # If filtering by KB, join through Message → Conversation
            if knowledge_base_id:
                from smart_doc_search.data.database import Message, Conversation
                query = query.join(
                    Message, Feedback.message_id == Message.id
                ).join(
                    Conversation, Message.conversation_id == Conversation.id
                ).filter(
                    Conversation.knowledge_base_id == knowledge_base_id
                )

            all_feedback = query.all()
            total = len(all_feedback)
            positive = sum(1 for f in all_feedback if f.rating > 0)
            negative = sum(1 for f in all_feedback if f.rating < 0)
            neutral = sum(1 for f in all_feedback if f.rating == 0)
            avg_rating = (
                sum(f.rating for f in all_feedback) / total if total > 0 else 0.0
            )

            # Count by type
            type_counts = {}
            for f in all_feedback:
                t = f.feedback_type or "unknown"
                type_counts[t] = type_counts.get(t, 0) + 1

            return {
                "total": total,
                "positive": positive,
                "negative": negative,
                "neutral": neutral,
                "avg_rating": round(avg_rating, 3),
                "positive_rate": round(positive / total, 3) if total > 0 else 0.0,
                "by_type": type_counts,
                "days": days,
            }

        except Exception as e:
            log.error(f"Failed to get feedback stats: {e}")
            return {
                "total": 0, "positive": 0, "negative": 0, "neutral": 0,
                "avg_rating": 0.0, "positive_rate": 0.0, "by_type": {}, "days": days,
            }
        finally:
            if should_close:
                db.close()


# ============================================================
# Singleton
# ============================================================

feedback_service = FeedbackService()
