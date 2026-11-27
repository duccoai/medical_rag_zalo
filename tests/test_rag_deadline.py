import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import TransientServiceException
from app.schemas.medical import MedicalResponseSchema
from app.services import rag_engine


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.parsed = MedicalResponseSchema(
        answer="Nên nghỉ ngơi và uống đủ nước, hỏi ý kiến bác sĩ nếu triệu chứng kéo dài.",
        recommended_dosage=None,
        sources=[],
        urgency_flag=False,
    )
    return response


async def _hang(**_kwargs):
    # Mô phỏng model bị treo: không bao giờ trả về trong thời gian test
    await asyncio.sleep(10)


def _match(content: str = "nội dung") -> dict:
    return {"content": content, "similarity": 0.9, "metadata": {"source": "Dengue.pdf"}}


# --- generate_medical_answer: deadline tổng ---

def test_generate_skips_all_models_when_deadline_already_passed():
    mock_generate = AsyncMock(return_value=_ok_response())
    past_deadline = time.monotonic() - 1
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        with pytest.raises(TransientServiceException):
            asyncio.run(
                rag_engine.generate_medical_answer("đau đầu", ["ctx"], deadline=past_deadline)
            )

    assert mock_generate.call_count == 0


def test_generate_stops_fallback_when_total_deadline_runs_out():
    # Model đầu bị treo đến hết deadline thì không được gọi model dự phòng nữa
    mock_generate = AsyncMock(side_effect=_hang)
    started = time.monotonic()
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        with pytest.raises(TransientServiceException):
            asyncio.run(
                rag_engine.generate_medical_answer("đau đầu", ["ctx"], deadline=time.monotonic() + 0.2)
            )
    elapsed = time.monotonic() - started

    assert mock_generate.call_count == 1
    assert elapsed < 2


def test_generate_caps_each_model_by_remaining_budget(monkeypatch):
    # Timeout riêng của model (LLM_TIMEOUT_S) lớn hơn phần còn lại, nên phải bị giới hạn theo deadline
    monkeypatch.setattr(rag_engine, "LLM_TIMEOUT_S", 30.0)
    mock_generate = AsyncMock(side_effect=_hang)
    started = time.monotonic()
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        with pytest.raises(TransientServiceException):
            asyncio.run(
                rag_engine.generate_medical_answer("đau đầu", ["ctx"], deadline=time.monotonic() + 0.3)
            )
    elapsed = time.monotonic() - started

    assert elapsed < 2


def test_generate_falls_back_when_single_model_exceeds_its_own_timeout(monkeypatch):
    # Model đầu bị treo quá timeout riêng nhưng deadline tổng còn dư: vẫn fallback sang model 2
    monkeypatch.setattr(rag_engine, "LLM_TIMEOUT_S", 0.2)

    async def _first_hangs_then_ok(**kwargs):
        if kwargs["model"] == rag_engine.LLM_MODELS[0]:
            await asyncio.sleep(10)
        return _ok_response()

    mock_generate = AsyncMock(side_effect=_first_hangs_then_ok)
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        result = asyncio.run(
            rag_engine.generate_medical_answer("đau đầu", ["ctx"], deadline=time.monotonic() + 5)
        )

    assert result.answer.startswith("Nên nghỉ ngơi")
    models_called = [c.kwargs["model"] for c in mock_generate.call_args_list]
    assert models_called == [rag_engine.LLM_MODELS[0], rag_engine.LLM_MODELS[1]]


def test_generate_without_deadline_uses_settings_budget(monkeypatch):
    monkeypatch.setattr(rag_engine.settings, "ANSWER_TOTAL_TIMEOUT", 5.0)
    mock_generate = AsyncMock(return_value=_ok_response())
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        result = asyncio.run(rag_engine.generate_medical_answer("đau đầu", ["ctx"]))

    assert result.answer.startswith("Nên nghỉ ngơi")
    assert mock_generate.call_count == 1


# --- retrieve_medical_contexts: deadline tổng ---

def test_retrieve_fails_fast_when_deadline_already_passed():
    mock_embed = AsyncMock(return_value=[0.1])
    with patch.object(rag_engine, "embed_queries", mock_embed):
        with pytest.raises(TransientServiceException):
            asyncio.run(
                rag_engine.retrieve_medical_contexts("sốt", deadline=time.monotonic() - 1)
            )

    assert mock_embed.call_count == 0


def test_retrieve_timeout_capped_by_remaining_deadline():
    # retrieval_timeout mặc định 6s nhưng deadline chỉ còn 0.2s
    mock_embed = AsyncMock(side_effect=_hang)
    started = time.monotonic()
    with patch.object(rag_engine, "embed_queries", mock_embed):
        with pytest.raises(TransientServiceException):
            asyncio.run(
                rag_engine.retrieve_medical_contexts("sốt", deadline=time.monotonic() + 0.2)
            )
    elapsed = time.monotonic() - started

    assert elapsed < 2


def test_retrieve_without_deadline_keeps_original_behaviour():
    mock_embed = AsyncMock(return_value=[0.1])
    mock_search = AsyncMock(return_value=[_match()])
    with patch.object(rag_engine, "embed_queries", mock_embed), \
            patch.object(rag_engine, "search_similar_vectors", mock_search):
        result = asyncio.run(rag_engine.retrieve_medical_contexts("sốt"))

    assert result == [_match()]


# --- answer_medical_query: một deadline dùng xuyên suốt pipeline ---

def test_answer_medical_query_shares_one_deadline_across_steps(monkeypatch):
    monkeypatch.setattr(rag_engine.settings, "ANSWER_TOTAL_TIMEOUT", 10.0)
    mock_retrieve = AsyncMock(return_value=[_match()])
    mock_generate = AsyncMock(return_value=_ok_response())
    with patch.object(rag_engine, "retrieve_medical_contexts", mock_retrieve), \
            patch.object(rag_engine, "generate_medical_answer", mock_generate):
        asyncio.run(rag_engine.answer_medical_query("sốt xuất huyết"))

    retrieve_deadline = mock_retrieve.call_args.kwargs["deadline"]
    generate_deadline = mock_generate.call_args.kwargs["deadline"]
    assert retrieve_deadline == generate_deadline
    assert 9 < retrieve_deadline - time.monotonic() <= 10


def test_answer_medical_query_respects_total_budget_end_to_end(monkeypatch):
    # Truy xuất vượt budget tổng -> trả lỗi tạm thời ngay, không gọi LLM
    monkeypatch.setattr(rag_engine.settings, "ANSWER_TOTAL_TIMEOUT", 0.3)

    async def _slow_embed(_query):
        await asyncio.sleep(1.0)
        return [0.1]

    mock_generate = AsyncMock(return_value=_ok_response())
    with patch.object(rag_engine, "embed_queries", _slow_embed), \
            patch.object(rag_engine, "search_similar_vectors", AsyncMock(return_value=[_match()])), \
            patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        with pytest.raises(TransientServiceException):
            asyncio.run(rag_engine.answer_medical_query("sốt xuất huyết"))

    assert mock_generate.call_count == 0
