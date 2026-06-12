from pydantic_settings import BaseSettings
from pathlib import Path

# Absolute path — works both locally (python main.py) and on Vercel serverless
_BACKEND_DIR = Path(__file__).parent
_DEFAULT_DATA_DIR = _BACKEND_DIR / "data"


class Settings(BaseSettings):
    anthropic_api_key: str
    llm_model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 1024
    session_ttl_seconds: int = 1800
    data_dir: Path = _DEFAULT_DATA_DIR
    port: int = 8001

    class Config:
        env_file = str(_BACKEND_DIR / ".env")
        extra = "ignore"


settings = Settings()
