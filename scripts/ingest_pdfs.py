import asyncio
import logging
import time
from pathlib import Path
from app.db.pgvector_store import (
    close_db_pool,
    init_vector_db,
)
from app.services.ingestion import extract_and_chunk_pdf
from app.services.rag_engine import (
    replace_document_source,
    retrieve_medical_contexts,
)

RAW_PDF_DIR = Path("data/raw_pdfs")


def normalize_vietnamese_pdf_artifacts(text: str) -> str:
    """Sửa lỗi ký tự ƣ/Ƣ (U+01A3/U+01A2) thường gặp ở tài liệu PDF y tế tiếng Việt cũ"""
    return text.replace("ƣ", "ư").replace("Ƣ", "Ư")




async def run_ingestion_pipeline(default_category: str = "tu_van_nha_thuoc") -> None:
    if not RAW_PDF_DIR.exists():
        print(f"❌ Không tìm thấy thư mục: {RAW_PDF_DIR.resolve()}")
        return

    pdf_files = sorted(RAW_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"⚠️ Thư mục {RAW_PDF_DIR} đang trống.")
        return

    print(f"🚀 Khởi tạo Vector DB & chuẩn bị xử lý {len(pdf_files)} file PDF...\n")
    await init_vector_db()

    total_inserted = 0
    pipeline_start = time.perf_counter()

    try:
        for pdf_path in pdf_files:
            file_start = time.perf_counter()
            print(f"📄 Đang đọc & phân tách cấu trúc: {pdf_path.name}")

            chunks = extract_and_chunk_pdf(pdf_path)
            if not chunks:
                print(f"   ⚠️ Không có chunk hợp lệ trong {pdf_path.name}, bỏ qua.\n")
                continue

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
            total_inserted += inserted

            if deleted > 0:
                print(f"   🧹 Đã thay thế {deleted} chunks cũ của file này.")
            print(f"   ✅ Hoàn tất nạp {inserted} vectors vào pgvector ({elapsed}s)\n")

        total_time = round(time.perf_counter() - pipeline_start, 2)
        print("=" * 65)
        print(f"🎉 TỔNG KẾT: Đã lưu {total_inserted} vectors vào PostgreSQL trong {total_time}s.")

        # Kiểm chứng ngay trên kho dữ liệu vừa nạp
        if total_inserted > 0:
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run_ingestion_pipeline())