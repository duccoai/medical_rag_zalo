import hashlib
import logging

from app.core.config import settings
from app.db.redis_cache import get_redis
from app.schemas.medical import MedicalResponseSchema
from app.services.chat_memory import append_turn, load_history
from app.services.rag_engine import answer_medical_query, check_input_guardrail

logger = logging.getLogger(__name__)


def _cache_key(query: str, category: str | None, top_k: int) -> str:
    normalized = " ".join(query.casefold().split())
    digest = hashlib.sha256(f"{normalized}|{category or ''}|{top_k}".encode("utf-8")).hexdigest()
    return f"{settings.REDIS_KEY_PREFIX}:cache:answer:{digest}"


async def _get_cached(key: str) -> MedicalResponseSchema | None:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không đọc được cache: %s", exc)
        return None
    return MedicalResponseSchema.model_validate_json(raw) if raw else None


async def _set_cached(key: str, result: MedicalResponseSchema) -> None:
    try:
        await get_redis().set(key, result.model_dump_json(), ex=settings.REDIS_CACHE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không ghi được cache: %s", exc)


async def answer_with_memory(
    user_id: str,
    message: str,
    category: str | None = None,
    top_k: int = 3,
    similarity_threshold: float = 0.5,
) -> MedicalResponseSchema:
    """Điều phối: guardrail -> memory -> cache -> RAG -> ghi cache -> ghi memory."""
    emergency = check_input_guardrail(message)
    if emergency:
        return emergency

    history = await load_history(user_id)
    cache_key = _cache_key(message, category, top_k)

    if not history:
        cached = await _get_cached(cache_key)
        if cached is not None:
            return cached

    result = await answer_medical_query(
        query=message,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        category_filter=category,
        history=history,
    )

    if not history and not result.urgency_flag:
        await _set_cached(cache_key, result)
    await append_turn(user_id, question=message, answer=result.answer)
    return result
