from pydantic_settings import BaseSettings, SettingsConfigDict
class TestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file="/opt/aitbc/.env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")
    db_path: str = ""
print(TestSettings().db_path)
