from pydantic_settings import BaseSettings
from pathlib import Path

# Absolute path — works both locally (python main.py) and on Vercel serverless
_BACKEND_DIR = Path(__file__).parent
_DEFAULT_DATA_DIR = _BACKEND_DIR / "data"


class Settings(BaseSettings):
    openrouter_api_key: str
    llm_model: str = "anthropic/claude-3-haiku"
    max_tokens: int = 1024
    session_ttl_seconds: int = 1800
    data_dir: Path = _DEFAULT_DATA_DIR
    port: int = 8001

    class Config:
        env_file = str(_BACKEND_DIR / ".env")
        extra = "ignore"


settings = Settings()
