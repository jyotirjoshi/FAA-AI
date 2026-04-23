from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    top_k: int = 10
    min_relevance: float = 0.12

    max_pages_per_source: int = 1200
    request_timeout_seconds: int = 20

    project_root: Path = Path(__file__).resolve().parents[1]
    raw_dir: Path = project_root / "data" / "raw"
    processed_dir: Path = project_root / "data" / "processed"
    index_dir: Path = project_root / "data" / "index"


settings = Settings()
