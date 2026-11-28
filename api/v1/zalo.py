import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import AppBaseException
from app.core.security import ZALO_SIGNATURE_HEADER, verify_zalo_signature
from app.schemas.zalo import ZaloWebhookEvent
from app.services.zalo_webhook_handler import handle_user_text_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/zalo", tags=["Zalo"])
SUPPORTED_EVENT = "user_send_text"  # [XÁC MINH] tên sự kiện


@router.post("/webhook", summary="Nhận sự kiện webhook từ Zalo OA")
async def zalo_webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()

    try:
        event = ZaloWebhookEvent.model_validate(json.loads(raw_body))
    except (ValueError, ValidationError) as exc:
        raise AppBaseException("Payload webhook không hợp lệ.", status_code=400) from exc

    if settings.ZALO_OA_SECRET_KEY is None:  # hoặc ZALO_APP_SECRET, theo kết quả xác minh
        raise AppBaseException("Webhook Zalo chưa được cấu hình.", status_code=503)

    verified = verify_zalo_signature(
        raw_body=raw_body,
        signature_header=request.headers.get(ZALO_SIGNATURE_HEADER),
        app_id=event.app_id or "",
        timestamp=event.timestamp or "",
        oa_secret_key=settings.ZALO_OA_SECRET_KEY.get_secret_value(),
        max_age_seconds=settings.ZALO_WEBHOOK_SIGNATURE_MAX_AGE_SECONDS,
    )
    if not verified:
        logger.warning("Webhook Zalo sai chữ ký, app_id=%s", event.app_id)
        raise AppBaseException("Chữ ký webhook không hợp lệ.", status_code=401)

    if (
        event.event_name != SUPPORTED_EVENT
        or event.sender is None
        or event.message is None
        or not event.message.msg_id
    ):
        return {"success": True, "ignored": True}

    background_tasks.add_task(handle_user_text_event, event)
    return {"success": True, "ignored": False}
