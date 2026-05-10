from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Claude API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-latest"

    # AI プロバイダー選択: "auto" | "api" | "claude_code"
    # auto: ANTHROPIC_API_KEY があれば API 優先、なければ Claude Code CLI
    ai_provider_type: str = "auto"

    # DB
    db_dir: Path = BASE_DIR / "data"

    # App
    app_title: str = "PatentBase"
    app_version: str = "0.1.0"
    debug: bool = False

    @property
    def db_url(self) -> str:
        self.db_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_dir / 'patents.db'}"


settings = Settings()
