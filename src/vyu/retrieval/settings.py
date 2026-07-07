from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrievalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VYU_RETRIEVAL_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    git_sha: str = "unknown"
    embedding_provider: str = "deterministic"
    embedding_model: str = "vyu-deterministic-v1"
    embed_batch_size: int = 32
    embed_max_attempts: int = 3
    lexical_pool_size: int = 50
    vector_pool_size: int = 50
    final_top_k: int = 20
    rrf_rank_constant: int = 60
    evaluation_suite: str = "retrieval_synthetic_v1"
    idempotency_ttl_hours: int = 24
