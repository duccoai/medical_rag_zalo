from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = 'Medical RAG Bot'
    VERSION: str = '1.0.0'
    ENVIRONMENT: str = 'development'
    
    # API Keys
    GEMINI_API_KEY: SecretStr = Field(..., description="API Key Google AI Studio cho Gemini (định dạng AQ.)")
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSIONS: int = 768        # Chuẩn Matryoshka tối ưu HNSW (< 2000d)
    EMBEDDING_BATCH_SIZE: int = 64         # Số chunks tối đa mỗi request API (50-100 để tránh 429)
    EMBEDDING_MAX_CONCURRENCY: int = 1     # Số batch chạy song song (1 = tuần tự, tránh dồn request)
    EMBEDDING_BATCH_INTERVAL_SECONDS: float = 4.0  # Thời gian nghỉ sau mỗi batch nạp tài liệu
    EMBEDDING_BATCH_MAX_RETRIES: int = 5   # Số lần retry tối đa cho mỗi batch khi gặp 429/5xx
    EMBEDDING_QUERY_TIMEOUT: float = 5.0   # Timeout chặt cho luồng chat realtime Zalo
    EMBEDDING_BATCH_TIMEOUT: float = 20.0  # Timeout cho mỗi batch nạp tài liệu nền

    # Database Configuration fields read from .env
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "medicaloai11911"
    POSTGRES_DB: str = "medical_db"

    # Zalo OA
    ZALO_APP_SECRET: SecretStr
    ZALO_OA_ACCESS_TOKEN: SecretStr

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """Computed async database URL for SQLAlchemy / asyncpg with safe fallback."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis Configuration
    REDIS_URL: str = 'redis://localhost:6379/0'

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()