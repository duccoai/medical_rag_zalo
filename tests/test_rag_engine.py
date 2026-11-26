import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import httpx2
import pytest
from google.genai import errors

from app.core.exceptions import AppBaseException, TransientServiceException
from app.schemas.medical import MedicalResponseSchema
from app.services import embedding, rag_engine


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


@pytest.mark.parametrize(
    "transport_error",
    [httpx.ConnectTimeout, httpx2.ConnectTimeout],
)
def test_falls_back_to_next_model_on_transport_error(transport_error):
    mock_generate = AsyncMock(
        side_effect=[transport_error("connection timed out"), _ok_response()]
    )
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        result = asyncio.run(rag_engine.generate_medical_answer("đau đầu", ["ctx"]))

    assert result.answer.startswith("Nên nghỉ ngơi")
    models_called = [c.kwargs["model"] for c in mock_generate.call_args_list]
    assert models_called == [rag_engine.LLM_MODELS[0], rag_engine.LLM_MODELS[1]]


def test_raises_retryable_error_when_all_models_time_out():
    mock_generate = AsyncMock(
        side_effect=[httpx2.ConnectTimeout("connection timed out")] * len(
            rag_engine.LLM_MODELS
        )
    )
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        with pytest.raises(TransientServiceException):
            asyncio.run(rag_engine.generate_medical_answer("đau đầu", ["ctx"]))

    assert mock_generate.call_count == len(rag_engine.LLM_MODELS)


def test_gemini_config_uses_low_thinking_level():
    mock_generate = AsyncMock(return_value=_ok_response())
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        asyncio.run(rag_engine._call_gemini("gemini-3.8-flash", "context"))

    config = mock_generate.call_args.kwargs["config"]
    assert config.thinking_config.thinking_level.value == "LOW"
    assert config.thinking_config.thinking_budget is None
    assert config.temperature is None


def test_generate_client_disables_sdk_retries_for_fallback_control():
    http_options = rag_engine.client._api_client._http_options

    assert http_options.timeout == rag_engine.LLM_TIMEOUT_MS
    assert http_options.retry_options.attempts == 1


def test_embedding_recognizes_httpx2_transport_error_as_transient():
    assert embedding._is_transient_error(
        httpx2.ConnectTimeout("connection timed out")
    )


def test_embedding_client_timeout_matches_longest_request_deadline(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(embedding, "_client", None)
    with patch.object(embedding.genai, "Client", return_value=mock_client) as factory:
        embedding.get_genai_client()

    http_options = factory.call_args.kwargs["http_options"]
    timeout = http_options.timeout
    expected_timeout = int(
        max(
            embedding.settings.EMBEDDING_QUERY_TIMEOUT,
            embedding.settings.EMBEDDING_BATCH_TIMEOUT,
        )
        * 1000
    )
    assert timeout == expected_timeout
    assert http_options.retry_options.attempts == 1
