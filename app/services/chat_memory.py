import json
import logging

from app.core.config import settings
from app.db.redis_cache import get_redis

logger = logging.getLogger(__name__)


def _memory_key(user_id: str) -> str:
    return f"{settings.REDIS_KEY_PREFIX}:memory:{user_id}"


def _clip(text: str) -> str:
    limit = settings.REDIS_MEMORY_MAX_CHARS
    return text if len(text) <= limit else text[:limit] + "..."


async def load_history(user_id: str) -> list[dict[str, str]]:
    """Trả về lịch sử theo thứ tự cũ -> mới. Lỗi Redis trả về danh sách rỗng."""
    try:
        raw_items = await get_redis().lrange(_memory_key(user_id), 0, -1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không đọc được memory (user_id=%s): %s", user_id, exc)
        return []
    return [json.loads(item) for item in raw_items]


async def append_turn(user_id: str, question: str, answer: str) -> None:
    """Ghi một lượt hỏi-đáp, giữ tối đa REDIS_MEMORY_MAX_TURNS lượt, làm mới TTL."""
    key = _memory_key(user_id)
    max_items = settings.REDIS_MEMORY_MAX_TURNS * 2  # mỗi lượt là 2 phần tử
    turns = [
        json.dumps({"role": "user", "content": _clip(question)}, ensure_ascii=False),
        json.dumps({"role": "assistant", "content": _clip(answer)}, ensure_ascii=False),
    ]
    try:
        async with get_redis().pipeline(transaction=True) as pipe:
            pipe.rpush(key, *turns)
            pipe.ltrim(key, -max_items, -1)
            pipe.expire(key, settings.REDIS_MEMORY_TTL_SECONDS)
            await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không ghi được memory (user_id=%s): %s", user_id, exc)


async def clear_history(user_id: str) -> None:
    """Xóa hội thoại của một user (dùng cho endpoint reset ở bước 7)."""
    await get_redis().delete(_memory_key(user_id))
