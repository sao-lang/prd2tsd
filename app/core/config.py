"""应用配置 — 基于 pydantic-settings 的三级优先级配置。"""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。

    配置优先级（高→低）：
    1. 环境变量（运行时注入）
    2. .env 文件
    3. 代码默认值
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Application ──
    APP_NAME: str = "prd2tsd"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-to-a-random-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── PostgreSQL ──
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/prd2tsd"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 10

    # ── MinIO ──
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "prd2tsd"
    MINIO_SECURE: bool = False

    # ── Neo4j ──
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4jpassword"
    NEO4J_DATABASE: str = "neo4j"

    # ── Model Config — LLM ──
    MODEL_CONFIG__LLM__DEEPSEEK__API_KEY: str = ""
    MODEL_CONFIG__LLM__DEEPSEEK__BASE_URL: str = "https://api.deepseek.com/v1"
    MODEL_CONFIG__LLM__DEEPSEEK__DEFAULT_MODEL: str = "deepseek-chat"

    MODEL_CONFIG__LLM__OPENAI__API_KEY: str = ""
    MODEL_CONFIG__LLM__OPENAI__BASE_URL: str = "https://api.openai.com/v1"
    MODEL_CONFIG__LLM__OPENAI__DEFAULT_MODEL: str = "gpt-4o-mini"

    # ── Model Config — Embedding ──
    MODEL_CONFIG__EMBEDDING__OPENAI__API_KEY: str = ""
    MODEL_CONFIG__EMBEDDING__OPENAI__BASE_URL: str = "https://api.openai.com/v1"
    MODEL_CONFIG__EMBEDDING__OPENAI__DEFAULT_MODEL: str = "text-embedding-3-small"

    # ── Model Config — Rerank ──
    MODEL_CONFIG__RERANK__COHERE__API_KEY: str = ""
    MODEL_CONFIG__RERANK__COHERE__BASE_URL: str = "https://api.cohere.com/v1"
    MODEL_CONFIG__RERANK__COHERE__DEFAULT_MODEL: str = "rerank-english-v3.0"

    # ── Model Config — Judge ──
    MODEL_CONFIG__JUDGE__OPENAI__API_KEY: str = ""
    MODEL_CONFIG__JUDGE__OPENAI__BASE_URL: str = "https://api.openai.com/v1"
    MODEL_CONFIG__JUDGE__OPENAI__DEFAULT_MODEL: str = "gpt-4o-mini"

    # ── Model Config — Vision ──
    MODEL_CONFIG__VISION__OPENAI__API_KEY: str = ""
    MODEL_CONFIG__VISION__OPENAI__BASE_URL: str = "https://api.openai.com/v1"
    MODEL_CONFIG__VISION__OPENAI__DEFAULT_MODEL: str = "gpt-4o"

    # ── Observability (Block E) ──
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "prd2tsd"
    PROMETHEUS_PORT: int = 9090

    # ── Budget (Block E) ──
    BUDGET_DEFAULT_MONTHLY_USD: float = 100.0
    BUDGET_DEFAULT_ALERT_THRESHOLD: float = 0.9
    BUDGET_DEFAULT_AUTO_DOWNGRADE: bool = True

    # ── Rate Limiter (Block E) ──
    RATE_LIMIT_DEFAULT_RPM: int = 60       # 每分钟请求数
    RATE_LIMIT_DEFAULT_TPM: int = 100000   # 每分钟 Token 数

    # ── Gateway Capability Modes ──
    EMBEDDING_MODE: str = "auto"        # auto / api / local
    RERANK_MODE: str = "auto"           # auto / api / local
    IMAGE_ENCODE_MODE: str = "local"    # auto / api / local（当前无 API，默认 local）
    CLIP_MODEL_NAME: str = "openai/clip-vit-base-patch32"

    # ── Model Routing Rules ──
    MODEL_ROUTING__ANALYSIS_REQUIREMENT__TYPE: str = "llm"
    MODEL_ROUTING__ANALYSIS_REQUIREMENT__PROVIDER: str = "deepseek"
    MODEL_ROUTING__ANALYSIS_REQUIREMENT__MODEL: str = "deepseek-chat"

    MODEL_ROUTING__PLANNING_ARCHITECTURE__TYPE: str = "llm"
    MODEL_ROUTING__PLANNING_ARCHITECTURE__PROVIDER: str = "deepseek"
    MODEL_ROUTING__PLANNING_ARCHITECTURE__MODEL: str = "deepseek-chat"

    MODEL_ROUTING__EVALUATION_SCORING__TYPE: str = "judge"
    MODEL_ROUTING__EVALUATION_SCORING__PROVIDER: str = "openai"
    MODEL_ROUTING__EVALUATION_SCORING__MODEL: str = "gpt-4o-mini"

    MODEL_ROUTING__GENERATION__TYPE: str = "llm"
    MODEL_ROUTING__GENERATION__PROVIDER: str = "deepseek"
    MODEL_ROUTING__GENERATION__MODEL: str = "deepseek-chat"

    MODEL_ROUTING__EMBEDDING__TYPE: str = "embedding"
    MODEL_ROUTING__EMBEDDING__PROVIDER: str = "openai"
    MODEL_ROUTING__EMBEDDING__MODEL: str = "text-embedding-3-small"

    MODEL_ROUTING__RERANK__TYPE: str = "rerank"
    MODEL_ROUTING__RERANK__PROVIDER: str = "cohere"
    MODEL_ROUTING__RERANK__MODEL: str = "rerank-english-v3.0"

    def get_model_config_env(self, model_type: str, provider: str) -> dict[str, Any]:
        """从环境变量中获取某模型类型的配置。

        Args:
            model_type: 模型类型（llm / embedding / rerank / judge / vision）。
            provider: 供应商名称（deepseek / openai / cohere）。

        Returns:
            包含 api_key, base_url, default_model 的字典。
        """
        prefix = f"MODEL_CONFIG__{model_type.upper()}__{provider.upper()}__"
        return {
            "api_key": getattr(self, f"{prefix}API_KEY", ""),
            "base_url": getattr(self, f"{prefix}BASE_URL", ""),
            "default_model": getattr(self, f"{prefix}DEFAULT_MODEL", ""),
        }

    def get_routing_env(self) -> dict[str, dict[str, str]]:
        """从环境变量中提取所有路由规则。

        扫描所有 MODEL_ROUTING__* 环境变量，按 task_type 分组。

        Returns:
            {task_type: {field: value}} 格式的路由规则字典。
        """
        rules: dict[str, dict[str, str]] = {}
        for key in dir(self):
            if not key.startswith("MODEL_ROUTING__"):
                continue
            parts = key.split("__")
            # MODEL_ROUTING__{TASK_TYPE}__{FIELD}
            if len(parts) < 4:
                continue
            task_type = parts[2].lower()
            field = parts[3].lower()
            value = getattr(self, key)
            if task_type not in rules:
                rules[task_type] = {}
            rules[task_type][field] = str(value)
        return rules


settings = Settings()
