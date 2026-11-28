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
    EMBEDDING_BATCH_INTERVAL_SECONDS: float = 12.0  # Khoảng cách tối thiểu giữa 2 request nạp tài liệu (Free Tier nên 10-15s)
    EMBEDDING_BATCH_MAX_RETRIES: int = 5   # Số lần retry tối đa cho mỗi batch khi gặp 429/5xx
    EMBEDDING_QUERY_TIMEOUT: float = 5.0   # Timeout chặt cho luồng chat realtime Zalo
    EMBEDDING_BATCH_TIMEOUT: float = 20.0  # Timeout cho mỗi batch nạp tài liệu nền
    ANSWER_TOTAL_TIMEOUT: float = 30.0     # Deadline tổng cho một lần tư vấn (truy xuất + gọi LLM các model dự phòng)

    # Database Configuration fields read from .env
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = Field(..., description="PostgreSQL password (required)")
    POSTGRES_DB: str = "medical_db"



    # Redis Configuration
    REDIS_URL: str = 'redis://localhost:6379/0'
    REDIS_KEY_PREFIX: str = "medrag"           # Tiền tố mọi khóa, tránh đụng khóa của dự án khác
    REDIS_SOCKET_TIMEOUT: float = 2.0          # Timeout kết nối và thao tác Redis (giây)
    REDIS_MEMORY_MAX_TURNS: int = 5            # Số lượt hỏi-đáp giữ lại cho mỗi user
    REDIS_MEMORY_MAX_CHARS: int = 500          # Cắt mỗi nội dung lịch sử để không phình prompt
    REDIS_MEMORY_TTL_SECONDS: int = 86400      # Hội thoại hết hạn sau 24 giờ không hoạt động
    REDIS_CACHE_TTL_SECONDS: int = 3600        # Cache câu trả lời sống 1 giờ

    # Zalo OA
    ZALO_APP_ID: str | None = Field(default=None, description="App ID trên Zalo for Developers")
    ZALO_APP_SECRET: SecretStr | None = Field(default=None, description="App Secret, dùng để refresh token và xác minh chữ ký webhook [XÁC MINH]")
    ZALO_OA_SECRET_KEY: SecretStr | None = Field(default=None, description="Secret key của OA, dùng xác minh chữ ký webhook [XÁC MINH]")
    ZALO_OA_ACCESS_TOKEN: SecretStr | None = Field(default=None, description="Access token ban đầu của OA, chỉ dùng để bootstrap")
    ZALO_OA_REFRESH_TOKEN: SecretStr | None = Field(default=None, description="Refresh token ban đầu của OA, chỉ dùng để bootstrap")
    ZALO_API_BASE_URL: str = "https://openapi.zalo.me"      # [XÁC MINH] phiên bản API gửi tin
    ZALO_OAUTH_BASE_URL: str = "https://oauth.zaloapp.com"  # [XÁC MINH] endpoint refresh token
    ZALO_REQUEST_TIMEOUT: float = 5.0                       # Timeout mỗi lệnh gọi Zalo OpenAPI (giây)
    ZALO_REPLY_MAX_CHARS: int = 2000                        # Độ dài tối đa mỗi tin nhắn gửi đi [XÁC MINH]
    ZALO_EVENT_DEDUP_TTL_SECONDS: int = 3600                # Thời gian nhớ msg_id đã xử lý
    ZALO_TOKEN_REFRESH_LEEWAY_SECONDS: int = 300            # Làm mới trước khi token hết hạn 5 phút
    ZALO_WEBHOOK_SIGNATURE_MAX_AGE_SECONDS: int = 300       # Chống replay theo timestamp sự kiện [XÁC MINH]



    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """Computed async database URL for SQLAlchemy / asyncpg with safe fallback."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis Configuration
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

    