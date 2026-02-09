from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # API
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Paths
    data_path: Path = Path("../data/Inventory Management")
    model_path: Path = Path("./models")
    chroma_path: Path = Path("./chroma_db")
    trained_models_dir: Path = Path("./data/models")

    # Model settings
    default_llm: str = "anthropic/claude-3.5-sonnet"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Forecasting
    forecast_horizon_days: int = 7

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
