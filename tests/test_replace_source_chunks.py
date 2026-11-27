from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppBaseException
from app.db import pgvector_store
from app.services import rag_engine


def _chunks(source: str, count: int) -> list[dict]:
    return [
        {
            "content": f"Nội dung đoạn {i}",
            "metadata": {"source": source, "chunk_index": i, "category": "test"},
        }
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_embedding_failure_does_not_touch_database(monkeypatch):
    """Nếu embedding lỗi, không được gọi bước xóa/ghi DB nên dữ liệu cũ của file được giữ nguyên"""
    monkeypatch.setattr(
        rag_engine,
        "embed_documents",
        AsyncMock(side_effect=RuntimeError("embedding failed")),
    )
    replace_mock = AsyncMock(return_value=(0, 0))
    monkeypatch.setattr(rag_engine, "replace_source_chunks", replace_mock)

    with pytest.raises(RuntimeError):
        await rag_engine.replace_document_source("a.pdf", _chunks("a.pdf", 3))

    replace_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_document_source_embeds_all_chunks_before_replacing(monkeypatch):
    """Embed đủ toàn bộ chunk rồi mới chuyển vectors xuống tầng replace"""
    chunks = _chunks("a.pdf", 2)
    vectors = [[0.1, 0.2], [0.3, 0.4]]
    embed_mock = AsyncMock(return_value=vectors)
    replace_mock = AsyncMock(return_value=(5, 2))
    monkeypatch.setattr(rag_engine, "embed_documents", embed_mock)
    monkeypatch.setattr(rag_engine, "replace_source_chunks", replace_mock)

    result = await rag_engine.replace_document_source("a.pdf", chunks)

    embed_mock.assert_awaited_once_with([c["content"] for c in chunks])
    replace_mock.assert_awaited_once_with(source="a.pdf", chunks=chunks, embeddings=vectors)
    assert result == (5, 2)


@pytest.mark.asyncio
async def test_replace_rejects_chunks_from_other_source(monkeypatch):
    """Chunk không thuộc nguồn đang xử lý phải bị từ chối trước khi chạm DB"""
    fake_pool = AsyncMock()
    get_pool_mock = AsyncMock(return_value=fake_pool)
    monkeypatch.setattr(pgvector_store, "get_db_pool", get_pool_mock)

    with pytest.raises(AppBaseException):
        await pgvector_store.replace_source_chunks(
            source="a.pdf",
            chunks=_chunks("b.pdf", 1),
            embeddings=[[0.1, 0.2]],
        )

    get_pool_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_with_no_chunks_keeps_existing_data(monkeypatch):
    """Không có chunk hợp lệ thì trả về (0, 0) và không xóa dữ liệu cũ"""
    get_pool_mock = AsyncMock()
    monkeypatch.setattr(pgvector_store, "get_db_pool", get_pool_mock)

    result = await pgvector_store.replace_source_chunks(source="a.pdf", chunks=[], embeddings=[])

    assert result == (0, 0)
    get_pool_mock.assert_not_awaited()
