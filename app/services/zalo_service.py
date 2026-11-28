import logging

import httpx

from app.core.config import settings
from app.core.exceptions import AppBaseException, TransientServiceException
from app.db.redis_cache import get_redis

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=settings.ZALO_REQUEST_TIMEOUT)
    return _http_client


async def close_zalo_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def claim_event(msg_id: str) -> bool:
    """True nếu đây là lần đầu thấy msg_id. Redis lỗi thì trả True (fail-open) và log."""
    ...


async def send_text(user_id: str, text: str) -> None:
    """Gửi một tin văn bản tới người dùng qua OA customer-service message.

    Endpoint, header và body theo tài liệu Zalo [XÁC MINH]:
        POST {ZALO_API_BASE_URL}/v3.0/oa/message/cs
        header: access_token: <token>
        body:   {"recipient": {"user_id": "<user_id>"}, "message": {"text": "<text>"}}

    Nếu Zalo báo token hết hạn: refresh một lần rồi gửi lại. Lỗi khác: raise TransientServiceException hoặc AppBaseException.
    """
    ...
