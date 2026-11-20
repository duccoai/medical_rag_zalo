from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from google.genai import errors as genai_errors
from app.core.config import settings
from app.db.pgvector_store import close_db_pool, get_db_pool, init_vector_db
from app.services.embedding import embed_documents, set_genai_client
from app.services.rag_engine import (
    ingest_document_chunks,
    retrieve_medical_contexts,
)


@pytest.mark.asyncio
async def test_embedding_batching_and_retry_unit():
    """Unit Test: Kiểm tra chia batch 64, chạy song song và tự động retry khi gặp lỗi 429"""
    call_counter = 0

    async def fake_embed_content(model, contents, config):
        nonlocal call_counter
        call_counter += 1
        # Giả lập lần gọi đầu tiên bị Rate Limit 429
        if call_counter == 1:
            raise genai_errors.APIError(
                code=429, response_json={"error": {"message": "Rate limit exceeded"}}
            )
        items = [contents] if isinstance(contents, str) else contents
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[0.1] * settings.EMBEDDING_DIMENSIONS)
                for _ in items
            ]
        )

    mock_client = MagicMock()
    mock_client.aio.models.embed_content = AsyncMock(side_effect=fake_embed_content)
    set_genai_client(mock_client)

    try:
        # 130 đoạn văn bản với batch_size=64 -> phải chia thành 3 batch (64 + 64 + 2)
        texts = [f"Đoạn tài liệu y khoa số {i}" for i in range(130)]
        vectors = await embed_documents(texts)

        assert len(vectors) == 130
        assert len(vectors[0]) == settings.EMBEDDING_DIMENSIONS
        # 3 batch + 1 lần retry do lỗi 429 ở batch đầu = 4 lần gọi API
        assert call_counter == 4
    finally:
        # Reset lại client thật cho các bài test tiếp theo
        set_genai_client(None)


@pytest.mark.asyncio
async def test_rag_ingest_and_retrieve_integration():
    """Integration Test: Kiểm tra luồng điều phối rag_engine -> embedding -> pgvector"""
    set_genai_client(None)  # Đảm bảo dùng Gemini Client thật
    try:
        await init_vector_db()

        # Dọn dữ liệu mẫu cũ để test chạy lại nhiều lần không trùng lặp
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM medical_documents WHERE metadata->>'source' IN ('duoc_thu_2026.pdf', 'huong_dan_dieu_tri.pdf');"
            )

        sample_chunks = [
            {
                "content": "Paracetamol (Acetaminophen) là thuốc hạ sốt, giảm đau phổ biến. Liều dùng trẻ em 10-15mg/kg mỗi 4-6 giờ.",
                "metadata": {"category": "dược lý", "source": "duoc_thu_2026.pdf"},
            },
            {
                "content": "Triệu chứng cúm A bao gồm sốt cao đột ngột, ho khô, đau họng, đau cơ và mệt mỏi kéo dài.",
                "metadata": {"category": "bệnh học", "source": "huong_dan_dieu_tri.pdf"},
            },
        ]

        # 1. Nạp dữ liệu thông qua tầng điều phối rag_engine
        inserted = await ingest_document_chunks(sample_chunks)
        assert inserted == 2

        # 2. Truy xuất dữ liệu thông qua tầng điều phối rag_engine kèm bộ lọc category
        results = await retrieve_medical_contexts(
            query="Liều dùng paracetamol cho trẻ em bị sốt",
            top_k=1,
            category_filter="dược lý",
        )
        assert len(results) == 1
        assert "Paracetamol" in results[0]["content"]
        assert results[0]["similarity"] > 0.60

        print(f"\n✅ Phase 5 Senior Architecture Test Passed! Similarity: {results[0]['similarity']}")
    finally:
        await close_db_pool()