from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = 'Medical RAG Bot'
    VERSION: str = '1.0.0'
    ENVIRONMENT: str = 'development'
    
    # API Keys
    OPENAI_API_KEY: SecretStr = Field(..., description="API Key cho LLM")
    ZALO_APP_SECRET: SecretStr
    ZALO_OA_ACCESS_TOKEN: SecretStr

    # Database Configuration fields read from .env
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "medicaloai11911"
    POSTGRES_DB: str = "medical_db"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """Computed async database URL for SQLAlchemy / asyncpg with safe fallback."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis Configuration
    REDIS_URL: str = 'redis://localhost:6379/0'

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()