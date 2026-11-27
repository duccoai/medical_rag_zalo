import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.db import redis_cache
from app.db.redis_cache import close_redis, get_redis
from app.schemas.medical import MedicalResponseSchema
from app.services import chat_memory, chat_memory_service, rag_engine
from app.services.chat_memory import append_turn, clear_history, load_history
from app.services.chat_memory_service import answer_with_memory

# Test dùng Redis thật (docker-compose: redis) nhưng với prefix riêng để không đụng dữ liệu thật
TEST_PREFIX = "medrag_test"
USER = "pytest-user"
QUESTION = "Sốt xuất huyết dùng thuốc gì để hạ sốt?"


def _run(coro):
    """Mỗi lần chạy có event loop mới; đóng client Redis sau mỗi lần để không dùng lại client của loop cũ."""
    async def _wrapper():
        try:
            return await coro
        finally:
            await close_redis()

    return asyncio.run(_wrapper())


async def _purge_test_keys() -> None:
    redis = get_redis()
    keys = [key async for key in redis.scan_iter(match=f"{TEST_PREFIX}:*")]
    if keys:
        await redis.delete(*keys)


async def _keys(pattern: str) -> list[str]:
    return [key async for key in get_redis().scan_iter(match=f"{TEST_PREFIX}:{pattern}")]


def _answer(sources: list[str] | None = None, urgency: bool = False, text: str = "Nghỉ ngơi và uống đủ nước.") -> MedicalResponseSchema:
    return MedicalResponseSchema(
        answer=text,
        recommended_dosage=None,
        sources=sources or [],
        urgency_flag=urgency,
    )


@pytest.fixture(autouse=True)
def _isolated_redis(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_KEY_PREFIX", TEST_PREFIX)
    _run(_purge_test_keys())
    yield
    _run(_purge_test_keys())


# Ca 1: append_turn rồi load_history giữ đúng thứ tự cũ -> mới, đủ cặp user/assistant
def test_append_then_load_keeps_order():
    async def scenario():
        await append_turn(USER, question="q1", answer="a1")
        await append_turn(USER, question="q2", answer="a2")
        return await load_history(USER)

    history = _run(scenario())

    assert history == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]


# Ca 2: ghi nhiều hơn REDIS_MEMORY_MAX_TURNS lượt thì chỉ giữ lượt mới nhất
def test_keeps_only_latest_turns(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_MEMORY_MAX_TURNS", 2)

    async def scenario():
        for i in range(1, 4):
            await append_turn(USER, question=f"q{i}", answer=f"a{i}")
        return await load_history(USER)

    history = _run(scenario())

    assert len(history) == 4
    assert [turn["content"] for turn in history] == ["q2", "a2", "q3", "a3"]


# Ca 3: sau append_turn, TTL của khóa > 0 và <= REDIS_MEMORY_TTL_SECONDS
def test_memory_key_has_ttl_within_limit():
    async def scenario():
        await append_turn(USER, question="q", answer="a")
        key = chat_memory._memory_key(USER)
        return await get_redis().ttl(key)

    ttl = _run(scenario())

    assert 0 < ttl <= settings.REDIS_MEMORY_TTL_SECONDS


# Ca 4: nội dung dài hơn REDIS_MEMORY_MAX_CHARS bị cắt và có "..."
def test_long_content_is_clipped(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_MEMORY_MAX_CHARS", 10)

    async def scenario():
        await append_turn(USER, question="x" * 50, answer="y" * 5)
        return await load_history(USER)

    history = _run(scenario())

    assert history[0]["content"] == "x" * 10 + "..."
    assert history[1]["content"] == "y" * 5


# Ca 5: Redis lỗi thì answer_with_memory vẫn trả kết quả RAG, không ném lỗi
def test_redis_failure_still_returns_answer(monkeypatch):
    def _broken_redis():
        raise ConnectionError("redis down")

    monkeypatch.setattr(chat_memory, "get_redis", _broken_redis)
    monkeypatch.setattr(chat_memory_service, "get_redis", _broken_redis)
    rag_mock = AsyncMock(return_value=_answer(text="Kết quả RAG"))
    monkeypatch.setattr(chat_memory_service, "answer_medical_query", rag_mock)

    result = _run(answer_with_memory(USER, QUESTION))

    assert result.answer == "Kết quả RAG"
    assert rag_mock.await_count == 1


# Ca 6: hai câu hỏi giống nhau, không có history -> lần 2 lấy từ cache, không gọi RAG
def test_identical_question_without_history_hits_cache(monkeypatch):
    rag_mock = AsyncMock(return_value=_answer(text="Đáp án cache"))
    monkeypatch.setattr(chat_memory_service, "answer_medical_query", rag_mock)

    async def scenario():
        first = await answer_with_memory(USER, QUESTION)
        # Lần đầu đã ghi memory, xóa để lần 2 thực sự không có history
        await clear_history(USER)
        second = await answer_with_memory(USER, QUESTION)
        return first, second

    first, second = _run(scenario())

    assert rag_mock.await_count == 1
    assert second.answer == first.answer == "Đáp án cache"


# Ca 7: câu hỏi cấp cứu trả cảnh báo, không gọi RAG, không tạo khóa cache hay memory
def test_emergency_returns_warning_without_caching_or_memory(monkeypatch):
    rag_mock = AsyncMock(return_value=_answer())
    monkeypatch.setattr(chat_memory_service, "answer_medical_query", rag_mock)

    result = _run(answer_with_memory(USER, "Bệnh nhân đang bị co giật"))

    assert result.urgency_flag is True
    assert rag_mock.await_count == 0

    async def keys_created():
        return await _keys("*")

    assert _run(keys_created()) == []


# Ca 8: có history thì không đọc và không ghi cache
def test_history_present_skips_cache_read_and_write(monkeypatch):
    rag_mock = AsyncMock(return_value=_answer(text="Trả lời có ngữ cảnh"))
    monkeypatch.setattr(chat_memory_service, "answer_medical_query", rag_mock)
    sentinel = _answer(text="Câu trả lời cũ lấy từ cache, không được dùng khi có ngữ cảnh hội thoại.").model_dump_json()
    cache_key = chat_memory_service._cache_key(QUESTION, None, 3)

    async def scenario():
        await append_turn(USER, question="Câu trước", answer="Trả lời trước")
        await get_redis().set(cache_key, sentinel, ex=60)
        result = await answer_with_memory(USER, QUESTION)
        stored = await get_redis().get(cache_key)
        return result, stored

    result, stored = _run(scenario())

    # Đã gọi RAG với history (không đọc cache), và cache không bị ghi đè
    assert rag_mock.await_count == 1
    assert rag_mock.call_args.kwargs["history"] != []
    assert result.answer == "Trả lời có ngữ cảnh"
    assert stored == sentinel


# Ca 9: sources trả về chỉ nằm trong tập tài liệu đã truy xuất
def test_returned_sources_are_limited_to_retrieved_documents(monkeypatch):
    matches = [
        {"content": "Nội dung tài liệu A", "similarity": 0.9, "metadata": {"source": "Doc A"}},
    ]
    monkeypatch.setattr(rag_engine, "retrieve_medical_contexts", AsyncMock(return_value=matches))
    monkeypatch.setattr(
        rag_engine,
        "_call_gemini",
        AsyncMock(return_value=_answer(sources=["Doc A", "Tài liệu bịa đặt"])),
    )

    result = _run(answer_with_memory(USER, "đau đầu"))

    assert result.sources == ["Doc A"]
