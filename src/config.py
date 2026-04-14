from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gamma-4"

    ai_gamma4_base_url: str = ""
    ai_gamma4_key: str = ""
    ai_gamma4_model: str = ""

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    top_k: int = 8
    min_relevance: float = 0.35

    max_pages_per_source: int = 1200
    request_timeout_seconds: int = 20

    project_root: Path = Path(__file__).resolve().parents[1]
    raw_dir: Path = project_root / "data" / "raw"
    processed_dir: Path = project_root / "data" / "processed"
    index_dir: Path = project_root / "data" / "index"


settings = Settings()
