from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gamma-4"

    nvapi_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvapi_key: str = ""
    nvapi_model: str = "meta/llama-4-maverick-17b-128e-instruct"

    litai_base_url: str = ""
    litai_api_key: str = ""
    litai_model: str = ""

    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"

    hf_api_base_url: str = "https://router.huggingface.co/v1"
    hf_api_token: str = ""
    hf_model: str = ""

    ai_gamma4_base_url: str = ""
    ai_gamma4_key: str = ""
    ai_gamma4_model: str = ""

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
