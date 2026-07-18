"""用户认证服务 — 注册、登录、登出，使用 bcrypt 加密密码."""
import bcrypt
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from database import SessionLocal, User
from loguru import logger as log


class AuthService:
    """本地用户认证服务。

    密码使用 bcrypt 加密存储。
    登录后用户信息存入 st.session_state。
    """

    @staticmethod
    def register(username: str, password: str, db: Session) -> Optional[User]:
        """注册新用户。

        Returns:
            User 对象，如果用户名已存在则返回 None。
        """
        username = username.strip()
        if len(username) < 3 or len(password) < 6:
            return None

        # 检查用户名是否已存在
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return None

        # bcrypt 加密
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        user = User(
            username=username,
            password_hash=password_hash,
            created_at=datetime.now(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        log.info(f"新用户注册: id={user.id}, username={user.username}")
        return user

    @staticmethod
    def login(username: str, password: str, db: Session) -> Optional[User]:
        """用户登录。

        验证用户名和密码，成功返回 User 对象，失败返回 None。
        """
        username = username.strip()

        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None

        # bcrypt 验证
        if not bcrypt.checkpw(
            password.encode("utf-8"), user.password_hash.encode("utf-8")
        ):
            return None

        log.info(f"用户登录: id={user.id}, username={user.username}")
        return user

    @staticmethod
    def change_password(user_id: int, old_pw: str, new_pw: str, db: Session) -> bool:
        """修改密码。"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        if not bcrypt.checkpw(
            old_pw.encode("utf-8"), user.password_hash.encode("utf-8")
        ):
            return False

        user.password_hash = bcrypt.hashpw(
            new_pw.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        db.commit()
        return True


auth_service = AuthService()
