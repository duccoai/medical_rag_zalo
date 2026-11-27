import logging
from redis.asyncio import Redis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Một client dùng chung cho toàn app, giống cách pgvector_store giữ _pool
_client: Redis | None = None


def get_redis() -> Redis:
    """Tạo hoặc tái sử dụng client Redis bất đồng bộ."""
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
    return _client


async def init_redis() -> None:
    """Ping khi khởi động. Redis chưa sẵn sàng chỉ cảnh báo, không chặn server."""
    try:
        await get_redis().ping()
    except Exception as exc:  # noqa: BLE001 - Redis là tầng tùy chọn
        logger.warning("Redis chưa sẵn sàng khi khởi động, memory và cache tạm tắt: %s", exc)


async def close_redis() -> None:
    """Đóng client khi server tắt."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
