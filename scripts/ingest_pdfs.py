import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.db.pgvector_store import (
    close_db_pool,
    init_vector_db,
)
from app.services.ingestion import extract_and_chunk_pdf
from app.services.rag_engine import (
    replace_document_source,
    retrieve_medical_contexts,
)

logger = logging.getLogger(__name__)

RAW_PDF_DIR = Path("data/raw_pdfs")

FileStatus = Literal["success", "failed", "skipped"]
STATUS_LABELS: dict[str, str] = {"success": "thành công", "failed": "thất bại", "skipped": "bỏ qua"}
STATUS_ICONS: dict[str, str] = {"success": "✅", "failed": "❌", "skipped": "⚠️"}


@dataclass
class FileIngestResult:
    """Kết quả nạp của một file PDF, dùng để báo cáo cuối lượt chạy"""
    name: str
    status: FileStatus
    chunks: int = 0
    inserted: int = 0
    deleted: int = 0
    elapsed: float = 0.0
    error: str | None = None


def normalize_vietnamese_pdf_artifacts(text: str) -> str:
    """Sửa lỗi ký tự ƣ/Ƣ (U+01A3/U+01A2) thường gặp ở tài liệu PDF y tế tiếng Việt cũ"""
    return text.replace("ƣ", "ư").replace("Ƣ", "Ư")


async def _ingest_one_file(pdf_path: Path, default_category: str) -> FileIngestResult:
    """Nạp một file PDF. Lỗi được ném ra ngoài để vòng lặp chính ghi nhận và chạy tiếp file kế tiếp."""
    file_start = time.perf_counter()
    print(f"📄 Đang đọc & phân tách cấu trúc: {pdf_path.name}")

    chunks = extract_and_chunk_pdf(pdf_path)
    if not chunks:
        print(f"   ⚠️ Không có chunk hợp lệ trong {pdf_path.name}, bỏ qua.\n")
        return FileIngestResult(name=pdf_path.name, status="skipped")

    # Chuẩn hóa lỗi font ƣ -> ư và gắn thêm category phục vụ lọc JSONB
    for item in chunks:
        item["content"] = normalize_vietnamese_pdf_artifacts(item["content"])
        item["metadata"]["category"] = default_category
        if "headers" in item["metadata"] and isinstance(item["metadata"]["headers"], dict):
            item["metadata"]["headers"] = {
                k: normalize_vietnamese_pdf_artifacts(v)
                for k, v in item["metadata"]["headers"].items()
            }

    print(f"   ⏳ Đang tạo Embedding 768d cho {len(chunks)} chunks...")
    # Embed trước, sau đó xóa bản cũ và ghi bản mới trong 1 transaction (lỗi giữa chừng thì giữ nguyên dữ liệu cũ)
    deleted, inserted = await replace_document_source(pdf_path.name, chunks)
    elapsed = round(time.perf_counter() - file_start, 2)

    if deleted > 0:
        print(f"   🧹 Đã thay thế {deleted} chunks cũ của file này.")
    print(f"   ✅ Hoàn tất nạp {inserted} vectors vào pgvector ({elapsed}s)\n")

    return FileIngestResult(
        name=pdf_path.name,
        status="success",
        chunks=len(chunks),
        inserted=inserted,
        deleted=deleted,
        elapsed=elapsed,
    )


def _print_report(results: list[FileIngestResult], total_time: float) -> None:
    """In báo cáo tổng hợp trạng thái từng file, số vector đã ghi và lý do các file thất bại"""
    success_count = sum(r.status == "success" for r in results)
    failed = [r for r in results if r.status == "failed"]
    skipped_count = sum(r.status == "skipped" for r in results)
    total_inserted = sum(r.inserted for r in results)

    print("=" * 65)
    print("📋 BÁO CÁO NẠP TÀI LIỆU")
    for r in results:
        print(
            f"   {STATUS_ICONS[r.status]} {r.name} | {STATUS_LABELS[r.status]} "
            f"| chunks: {r.chunks} | vectors ghi: {r.inserted} | thời gian: {r.elapsed}s"
        )
        if r.error:
            print(f"       Lý do: {r.error}")
    print("-" * 65)
    print(
        f"   Thành công: {success_count} | Thất bại: {len(failed)} | Bỏ qua: {skipped_count} "
        f"| Tổng vectors đã ghi: {total_inserted} | Tổng thời gian: {total_time}s"
    )
    if failed:
        print("   File cần nạp lại: " + ", ".join(r.name for r in failed))
        print("   Dữ liệu cũ của các file thất bại vẫn được giữ nguyên trong DB.")
    print("=" * 65)


async def run_ingestion_pipeline(default_category: str = "tu_van_nha_thuoc") -> list[FileIngestResult]:
    if not RAW_PDF_DIR.exists():
        print(f"❌ Không tìm thấy thư mục: {RAW_PDF_DIR.resolve()}")
        return []

    pdf_files = sorted(RAW_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"⚠️ Thư mục {RAW_PDF_DIR} đang trống.")
        return []

    print(f"🚀 Khởi tạo Vector DB & chuẩn bị xử lý {len(pdf_files)} file PDF...\n")
    await init_vector_db()

    results: list[FileIngestResult] = []
    pipeline_start = time.perf_counter()

    try:
        for pdf_path in pdf_files:
            # Lỗi của một file chỉ ghi nhận trạng thái thất bại, không dừng các file còn lại
            try:
                result = await _ingest_one_file(pdf_path, default_category)
            except Exception as exc:
                logger.exception("Nạp file %s thất bại", pdf_path.name)
                print(f"   ❌ Lỗi khi nạp {pdf_path.name}: {exc}. Chuyển sang file kế tiếp.\n")
                result = FileIngestResult(
                    name=pdf_path.name,
                    status="failed",
                    error=str(exc) or type(exc).__name__,
                )
            results.append(result)

        total_time = round(time.perf_counter() - pipeline_start, 2)
        _print_report(results, total_time)

        # Kiểm chứng ngay trên kho dữ liệu vừa nạp
        if any(r.inserted > 0 for r in results):
            sample_query = "Khi nào bệnh nhân chấn thương hoặc đau bụng cần đi cấp cứu ngay?"
            print(f"\n🔍 Test truy vấn thực tế: '{sample_query}'")
            matches = await retrieve_medical_contexts(
                query=sample_query,
                top_k=2,
                similarity_threshold=0.5,
            )
            for idx, m in enumerate(matches, start=1):
                headers = m["metadata"].get("headers", {})
                section = " > ".join(headers.values()) if headers else m["metadata"].get("source")
                print(f"   [{idx}] Similarity: {m['similarity']} | Mục: {section}")
                print(f"       Trích đoạn: {m['content'][:160].replace(chr(10), ' ')}...")

    finally:
        await close_db_pool()

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_results = asyncio.run(run_ingestion_pipeline())
    # Trả mã thoát khác 0 nếu có file thất bại để CI/cron phát hiện được
    if any(r.status == "failed" for r in run_results):
        sys.exit(1)
