from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import json
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MISTRAL_API_KEY: str
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str
    TELEGRAM_ADMIN_CHAT_ID: str = ""
    BASE_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "sqlite:///./data/orders.db"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def load_menu() -> dict:
    menu_path = Path(__file__).parent.parent / "menu.json"
    with open(menu_path, encoding="utf-8") as f:
        return json.load(f)
