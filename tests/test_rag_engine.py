import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors

from app.core.exceptions import AppBaseException
from app.schemas.medical import MedicalResponseSchema
from app.services import rag_engine


def _api_error(code: int) -> errors.APIError:
    return errors.APIError(
        code,
        {"error": {"code": code, "message": "mock error", "status": "UNAVAILABLE"}},
    )


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.parsed = MedicalResponseSchema(
        answer="Nên nghỉ ngơi và uống đủ nước, hỏi ý kiến bác sĩ nếu triệu chứng kéo dài.",
        recommended_dosage=None,
        sources=["tài liệu test"],
        urgency_flag=False,
    )
    return response


@pytest.mark.parametrize("code", [503, 504])
def test_falls_back_to_next_model_on_overload(code):
    mock_generate = AsyncMock(side_effect=[_api_error(code), _ok_response()])
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        result = asyncio.run(rag_engine.generate_medical_answer("đau đầu", ["ctx"]))

    assert result.answer.startswith("Nên nghỉ ngơi")
    models_called = [c.kwargs["model"] for c in mock_generate.call_args_list]
    assert models_called == [rag_engine.LLM_MODELS[0], rag_engine.LLM_MODELS[1]]


def test_raises_when_all_models_overloaded():
    mock_generate = AsyncMock(side_effect=[_api_error(503)] * len(rag_engine.LLM_MODELS))
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        with pytest.raises(AppBaseException):
            asyncio.run(rag_engine.generate_medical_answer("đau đầu", ["ctx"]))

    assert mock_generate.call_count == len(rag_engine.LLM_MODELS)


def test_does_not_fallback_on_other_api_errors():
    mock_generate = AsyncMock(side_effect=[_api_error(400), _ok_response()])
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        with pytest.raises(AppBaseException):
            asyncio.run(rag_engine.generate_medical_answer("đau đầu", ["ctx"]))

    assert mock_generate.call_count == 1
