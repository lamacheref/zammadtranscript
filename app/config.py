from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    zammad_url: str = "http://localhost:8080"
    zammad_token: str = ""
    webhook_secret: str = ""
    zammad_timeout: int = 30

    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_cpu_threads: int = 8
    whisper_language: str | None = None

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: int = 120

    host: str = "0.0.0.0"
    port: int = 8000

    log_level: str = "INFO"

    redis_url: str = "redis://localhost:6379"
    rq_queue_name: str = "transcription"


@lru_cache
def get_settings() -> Settings:
    return Settings()
