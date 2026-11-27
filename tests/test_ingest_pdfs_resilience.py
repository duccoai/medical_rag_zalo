from unittest.mock import AsyncMock

import pytest

from scripts import ingest_pdfs


def _fake_chunks(path):
    return [
        {
            "content": f"Nội dung của {path.name}",
            "metadata": {"source": path.name, "chunk_index": 0},
        }
    ]


@pytest.mark.asyncio
async def test_failed_file_does_not_stop_remaining_files(tmp_path, monkeypatch):
    """Một file lỗi giữa chừng được ghi nhận thất bại, các file còn lại vẫn được nạp"""
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (tmp_path / name).write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(ingest_pdfs, "RAW_PDF_DIR", tmp_path)
    monkeypatch.setattr(ingest_pdfs, "init_vector_db", AsyncMock())
    monkeypatch.setattr(ingest_pdfs, "close_db_pool", AsyncMock())
    monkeypatch.setattr(ingest_pdfs, "extract_and_chunk_pdf", _fake_chunks)

    async def fake_replace(source, chunks):
        if source == "b.pdf":
            raise RuntimeError("embedding timeout")
        return 0, len(chunks)

    replace_mock = AsyncMock(side_effect=fake_replace)
    monkeypatch.setattr(ingest_pdfs, "replace_document_source", replace_mock)
    monkeypatch.setattr(ingest_pdfs, "retrieve_medical_contexts", AsyncMock(return_value=[]))

    results = await ingest_pdfs.run_ingestion_pipeline()

    assert [r.name for r in results] == ["a.pdf", "b.pdf", "c.pdf"]
    assert [r.status for r in results] == ["success", "failed", "success"]
    assert results[1].error == "embedding timeout"
    assert results[0].inserted == 1 and results[2].inserted == 1
    assert replace_mock.await_count == 3


@pytest.mark.asyncio
async def test_file_without_chunks_is_skipped(tmp_path, monkeypatch):
    """File không có chunk hợp lệ được đánh dấu bỏ qua và không gọi bước ghi DB"""
    (tmp_path / "empty.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(ingest_pdfs, "RAW_PDF_DIR", tmp_path)
    monkeypatch.setattr(ingest_pdfs, "init_vector_db", AsyncMock())
    monkeypatch.setattr(ingest_pdfs, "close_db_pool", AsyncMock())
    monkeypatch.setattr(ingest_pdfs, "extract_and_chunk_pdf", lambda path: [])
    replace_mock = AsyncMock()
    monkeypatch.setattr(ingest_pdfs, "replace_document_source", replace_mock)

    results = await ingest_pdfs.run_ingestion_pipeline()

    assert [r.status for r in results] == ["skipped"]
    replace_mock.assert_not_awaited()
