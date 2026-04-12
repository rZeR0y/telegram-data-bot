from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    DATABASE_URL: str
    ALLOWED_CHAT_IDS: str = ""
    REPORT_CHAT_ID: str = ""
    GLM_API_KEY: str = ""

    @property
    def allowed_chat_ids(self) -> List[int]:
        if not self.ALLOWED_CHAT_IDS:
            return []
        return [int(x.strip()) for x in self.ALLOWED_CHAT_IDS.split(",") if x.strip()]

    @property
    def report_chat_id(self) -> int | None:
        return int(self.REPORT_CHAT_ID) if self.REPORT_CHAT_ID else None

    class Config:
        env_file = ".env"


settings = Settings()
