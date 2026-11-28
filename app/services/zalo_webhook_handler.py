import logging

from app.core.config import settings
from app.schemas.zalo import ZaloWebhookEvent
from app.services.chat_memory_service import answer_with_memory
from app.services.zalo_message import FALLBACK_TEXT, HINT_TEXT, format_zalo_reply
from app.services.zalo_service import claim_event, send_text

logger = logging.getLogger(__name__)

TEXT_MIN_CHARS = 2
TEXT_MAX_CHARS = 1000


async def handle_user_text_event(event: ZaloWebhookEvent) -> None:
    """Chạy trong BackgroundTasks. Không được ném lỗi ra ngoài."""
    user_id = event.sender.id
    text = (event.message.text or "").strip()
    msg_id = event.message.msg_id

    if not await claim_event(msg_id):
        logger.info("Bỏ qua sự kiện trùng msg_id=%s", msg_id)
        return

    if not (TEXT_MIN_CHARS <= len(text) <= TEXT_MAX_CHARS):
        await _safe_send(user_id, HINT_TEXT)
        return

    try:
        result = await answer_with_memory(user_id=user_id, message=text)
        chunks = format_zalo_reply(result, limit=settings.ZALO_REPLY_MAX_CHARS)
    except Exception:  # noqa: BLE001 - nền không được làm rơi lỗi
        logger.exception("Lỗi xử lý RAG cho user_id=%s", user_id)
        chunks = [FALLBACK_TEXT]

    for chunk in chunks:
        await _safe_send(user_id, chunk)


async def _safe_send(user_id: str, text: str) -> None:
    try:
        await send_text(user_id, text)
    except Exception:  # noqa: BLE001
        logger.exception("Không gửi được tin Zalo cho user_id=%s", user_id)
