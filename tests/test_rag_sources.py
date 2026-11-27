import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.medical import MedicalResponseSchema
from app.services import rag_engine


def _match(source: str, headers: dict | None = None, page: int | None = None, content: str = "nội dung") -> dict:
    meta: dict = {"source": source}
    if headers is not None:
        meta["headers"] = headers
    if page is not None:
        meta["page"] = page
    return {"content": content, "similarity": 0.9, "metadata": meta}


def _response_with_sources(sources: list[str]) -> MagicMock:
    response = MagicMock()
    response.parsed = MedicalResponseSchema(
        answer="Nên nghỉ ngơi và uống đủ nước, hỏi ý kiến bác sĩ nếu triệu chứng kéo dài.",
        recommended_dosage=None,
        sources=sources,
        urgency_flag=False,
    )
    return response


# --- _build_citation ---

def test_build_citation_uses_header_breadcrumb():
    meta = {"source": "Dengue.pdf", "headers": {"h1": "Chương 1", "h2": "Mục A"}}
    assert rag_engine._build_citation(meta) == "Dengue.pdf (Chương 1 > Mục A)"


def test_build_citation_falls_back_to_page_then_source():
    assert rag_engine._build_citation({"source": "Dengue.pdf", "page": 12}) == "Dengue.pdf (Trang 12)"
    assert rag_engine._build_citation({"source": "Dengue.pdf"}) == "Dengue.pdf"


def test_build_citation_defaults_source_when_missing():
    assert rag_engine._build_citation({}) == "Tài liệu y khoa"


# --- _build_source_index ---

def test_build_source_index_maps_full_citation_and_bare_source_name():
    matches = [_match("Dengue.pdf", headers={"h1": "Chương 1"})]
    index = rag_engine._build_source_index(matches)

    assert index[rag_engine._normalize_source_key("Dengue.pdf (Chương 1)")] == "Dengue.pdf (Chương 1)"
    assert index[rag_engine._normalize_source_key("Dengue.pdf")] == "Dengue.pdf (Chương 1)"


def test_build_source_index_keeps_first_citation_for_duplicate_keys():
    matches = [
        _match("Dengue.pdf", page=1),
        _match("Dengue.pdf", page=2),
    ]
    index = rag_engine._build_source_index(matches)

    assert index[rag_engine._normalize_source_key("Dengue.pdf")] == "Dengue.pdf (Trang 1)"


# --- _verify_sources ---

def test_verify_sources_drops_fabricated_names():
    index = rag_engine._build_source_index([_match("Dengue.pdf", page=12)])

    verified = rag_engine._verify_sources(
        ["Hướng dẫn Bệnh viện Bạch Mai 2030", "Dengue.pdf (Trang 12)"],
        index,
    )

    assert verified == ["Dengue.pdf (Trang 12)"]


def test_verify_sources_matches_case_and_whitespace_insensitively():
    index = rag_engine._build_source_index([_match("Dengue Guide.pdf", page=3)])

    verified = rag_engine._verify_sources(["  dengue   guide.PDF (trang 3) "], index)

    assert verified == ["Dengue Guide.pdf (Trang 3)"]


def test_verify_sources_maps_bare_source_name_to_canonical_citation():
    index = rag_engine._build_source_index([_match("Dengue.pdf", page=12)])

    assert rag_engine._verify_sources(["Dengue.pdf"], index) == ["Dengue.pdf (Trang 12)"]


def test_verify_sources_deduplicates_and_keeps_order():
    index = rag_engine._build_source_index([
        _match("A.pdf", page=1),
        _match("B.pdf", page=2),
    ])

    verified = rag_engine._verify_sources(
        ["B.pdf", "A.pdf", "b.pdf", "A.pdf (Trang 1)"],
        index,
    )

    assert verified == ["B.pdf (Trang 2)", "A.pdf (Trang 1)"]


def test_verify_sources_returns_empty_when_nothing_matches():
    index = rag_engine._build_source_index([_match("Dengue.pdf", page=12)])

    assert rag_engine._verify_sources(["Tài liệu không tồn tại"], index) == []


def test_verify_sources_returns_empty_without_index():
    assert rag_engine._verify_sources(["Dengue.pdf"], {}) == []


# --- generate_medical_answer ---

def test_generate_medical_answer_filters_llm_sources_with_index():
    index = rag_engine._build_source_index([_match("Dengue.pdf", page=12)])
    mock_generate = AsyncMock(
        return_value=_response_with_sources(["Dengue.pdf", "Sách giả tạo"])
    )
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        result = asyncio.run(
            rag_engine.generate_medical_answer("sốt xuất huyết", ["ctx"], source_index=index)
        )

    assert result.sources == ["Dengue.pdf (Trang 12)"]


def test_generate_medical_answer_returns_no_sources_without_index():
    mock_generate = AsyncMock(return_value=_response_with_sources(["Dengue.pdf"]))
    with patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        result = asyncio.run(rag_engine.generate_medical_answer("sốt", ["ctx"]))

    assert result.sources == []


# --- answer_medical_query (end-to-end with mocked retrieval and LLM) ---

def test_answer_medical_query_only_returns_retrieved_sources():
    matches = [_match("Dengue.pdf", headers={"h1": "Chương 2"})]
    mock_generate = AsyncMock(
        return_value=_response_with_sources(["Dengue.pdf (Chương 2)", "Nguồn bịa đặt"])
    )
    with patch.object(rag_engine, "retrieve_medical_contexts", AsyncMock(return_value=matches)), \
            patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        result = asyncio.run(rag_engine.answer_medical_query("sốt xuất huyết"))

    assert result.sources == ["Dengue.pdf (Chương 2)"]


def test_answer_medical_query_sends_citations_in_context():
    matches = [_match("Dengue.pdf", page=12, content="Paracetamol 10-15 mg/kg")]
    mock_generate = AsyncMock(return_value=_response_with_sources([]))
    with patch.object(rag_engine, "retrieve_medical_contexts", AsyncMock(return_value=matches)), \
            patch.object(rag_engine.client.aio.models, "generate_content", mock_generate):
        asyncio.run(rag_engine.answer_medical_query("sốt xuất huyết"))

    prompt = mock_generate.call_args.kwargs["contents"]
    assert "Nguồn: Dengue.pdf (Trang 12)" in prompt


def test_system_instruction_requires_citing_only_context_sources():
    assert "Trường sources" in rag_engine.SYSTEM_INSTRUCTION
    assert "Tuyệt đối không tự đặt" in rag_engine.SYSTEM_INSTRUCTION
