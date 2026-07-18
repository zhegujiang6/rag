"""
Streamlit 前端配置 — 仅含前端需要的配置项。
业务配置从 Java 后端获取。
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "智能文档检索助手"
    APP_VERSION: str = "2.0.0"

    # Java 后端 API 网关地址
    API_GATEWAY_URL: str = "http://localhost:8080"
    API_TIMEOUT: int = 120

    # LLM 显示信息 (从后端获取，仅用于侧边栏展示)
    LLM_MODEL: str = "qwen-plus"


settings = Settings()
