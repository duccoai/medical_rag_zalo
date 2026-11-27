Dưới đây là bản phân tích chi tiết về **tầng Service và Business Logic** của project **medical_rag_zalo** dựa trên việc đọc trực tiếp source code (`app/services/`, `app/db/pgvector_store.py`, và các thành phần liên quan), tuân thủ đúng yêu cầu không thực thi hay sửa đổi code.

---

### I. Tổng quan các Service và Trách nhiệm

Tầng service được đặt tại thư mục `app/services/` và bao gồm 3 module chính cùng 1 module lưu trữ vector liên quan trực tiếp:

1. **`app/services/embedding.py` (Embedding & Gemini Client Service)**
   - **Trách nhiệm:** Quản lý vòng đời kết nối Gemini AI Client, điều phối và thực thi việc tạo vector embedding từ văn bản (cho cả luồng realtime Zalo query lẫn luồng batch PDF background), tích hợp cơ chế retry thông minh (`tenacity`), quản lý tốc độ request (`rate limit` / RPM pacing) và kiểm soát lỗi tạm thời.

2. **`app/services/ingestion.py` (PDF Processing & Two-Tier Chunking Service)**
   - **Trách nhiệm:** Tiền xử lý tài liệu y khoa định dạng PDF (chuyển đổi Markdown, làm sạch header/footer rặp lại/số trang), băm tài liệu theo cấu trúc 2 tầng (tầng 1 theo tiêu đề Markdown `h1`, `h2`, `h3`, tầng 2 đệ quy theo độ dài ký tự), gắn `breadcrumb` ngữ cảnh phân cấp vào từng chunk để tối ưu chất lượng retrieval.

3. **`app/services/rag_engine.py` (RAG Pipeline & LLM Answer Generation Service)**
   - **Trách nhiệm:** Điều phối toàn bộ vòng đời hỏi đáp y tế (RAG Pipeline), bảo vệ đầu vào bằng Safety Guardrail (chặn từ khóa cấp cứu), kết nối với `pgvector` để tìm kiếm ngữ cảnh, định dạng tài liệu trích dẫn, và gọi Gemini LLM sinh câu trả lời có cấu trúc JSON (`MedicalResponseSchema`) kèm cơ chế **Model Fallback** tự động khi model chính quá tải (`503`/`504`/`429`).

4. **`app/db/pgvector_store.py` (Vector Database & Storage Service - *Thành phần liên quan trực tiếp*)**
   - **Trách nhiệm:** Quản lý Connection Pool (`asyncpg`), khởi tạo extension `vector`, cấu trúc bảng `medical_documents`, thiết lập Index HNSW (`vector_cosine_ops`), thực hiện Upsert hàng loạt (chống trùng lặp qua `chunk_key`) và thực hiện truy vấn tương đồng cosine (`<=>`).

---

### II. Phân tích các Function & Method quan trọng theo từng Module

#### 1. Module `app/services/embedding.py`
- **`get_genai_client() -> genai.Client`**: Lazy-init client Gemini, tự động tính toán timeout dựa trên config (`EMBEDDING_QUERY_TIMEOUT`, `EMBEDDING_BATCH_TIMEOUT`), hỗ trợ inject mock client qua `set_genai_client()` phục vụ Unit Test.
- **`_embed_core(texts: str | list[str], task_type: EmbeddingTaskType)`**: Hàm điều phối cốt lõi phân chia 2 nhánh:
  - *Nhánh 1 (Str):* Dành cho query realtime (Zalo chat), timeout ngắn (`EMBEDDING_QUERY_TIMEOUT`), retry nhanh qua `_QUERY_WAIT`, trả về `list[float]` 1D.
  - *Nhánh 2 (List[str]):* Dành cho nạp PDF nền, chia thành các lô (`batch_size`), dùng `asyncio.Semaphore` giới hạn đồng thời kết hợp `_wait_for_request_slot()` để giãn cách nhịp request tránh chạm ngưỡng RPM của Gemini Free Tier.
- **`_embed_single_payload_with_retry(...)`**: Bọc gọi API `client.aio.models.embed_content` với `model=settings.EMBEDDING_MODEL` và `output_dimensionality=settings.EMBEDDING_DIMENSIONS`, tích hợp `AsyncRetrying` của thư viện `tenacity`, bắt lỗi tạm thời (`_is_transient_error`) và trích xuất `retryDelay` (`_batch_wait`) khi gặp mã lỗi `429`.
- **`embed_documents(...)` / `embed_queries(...)`**: Overload wrapper gán sẵn `task_type` tương ứng là `"RETRIEVAL_DOCUMENT"` và `"RETRIEVAL_QUERY"`.

#### 2. Module `app/services/ingestion.py`
- **`pdf_to_markdown(pdf_path: Path) -> str`**: Sử dụng `pymupdf4llm.to_markdown()` để chuyển đổi toàn bộ PDF thành Markdown liền mạch (nếu lỗi ném `AppBaseException` mã `422`).
- **`clean_markdown_text(markdown: str) -> str`**: Xử lý rác tài liệu: chuẩn hóa lỗi mã hóa (`ƣ` -> `ư`), đếm tần suất xuất hiện dòng ngắn lặp lại (`Counter` vượt `REPEAT_THRESHOLD = 5`) để loại bỏ header/footer chạy trang, lọc số trang đứng riêng (`PAGE_NUMBER_PATTERN`).
- **`chunk_markdown(markdown: str, source: str, chunk_size: int, chunk_overlap: int) -> list[dict]`**: 
  - *Tầng 1:* Dùng `MarkdownHeaderTextSplitter` băm theo `h1`, `h2`, `h3`.
  - *Tầng 2:* Dùng `RecursiveCharacterTextSplitter` (`chunk_size=600`, `overlap=100`) băm phần thân.
  - *Gắn Breadcrumb:* Gọi `_with_breadcrumb()` để nhồi chuỗi phân cấp tiêu đề (`Header 1 > Header 2`) vào đầu mỗi chunk kèm metadata `source`, `chunk_index`, `headers`.
- **`extract_and_chunk_pdf(...)`**: Hàm tổng hợp toàn bộ quy trình từ validate file -> convert -> clean -> chunk 2 tầng.

#### 3. Module `app/services/rag_engine.py`
- **`check_input_guardrail(query: str) -> MedicalResponseSchema | None`**: Kiểm tra từ khóa cấp cứu (`EMERGENCY_KEYWORDS` như "tự tử", "uống thuốc trừ sâu", "ngưng thở", "bất tỉnh"...). Nếu khớp, trả ngay cảnh báo khẩn cấp mà không tốn token LLM hay truy vấn DB.
- **`retrieve_medical_contexts(...)`**: Luồng truy vấn realtime bọc trong `asyncio.wait_for` (timeout mặc định `6.0s`), gọi `embed_queries()` rồi chuyển xuống `search_similar_vectors()`.
- **`generate_medical_answer(query: str, retrieved_contexts: list[str]) -> MedicalResponseSchema`**: 
  - Ghép Context vào Prompt chung với `SYSTEM_INSTRUCTION` nghiêm ngặt (chỉ dùng tài liệu context, cấm bịa đặt liều dùng).
  - Thực hiện **Model Fallback Loop** qua danh sách `LLM_MODELS` (`gemini-3.8-flash` -> `gemini-3.1-flash-lite` -> `gemini-3.5-flash`). Nếu gặp lỗi `429`, `503`, `504` hoặc transport error, hệ thống tự động chuyển sang model dự phòng kế tiếp.
  - Cấu hình Gemini gọi ở dạng JSON structured output thông qua `response_mime_type="application/json"` và `response_schema=MedicalResponseSchema`.
- **`answer_medical_query(...)`**: Pipeline RAG hoàn chỉnh: Guardrail -> Retrieve -> Kiểm tra rỗng (từ chối lịch sự nếu không có chunk đạt chuẩn) -> Format Context -> Generate LLM.

#### 4. Module `app/db/pgvector_store.py`
- **`init_vector_db()`**: Khởi tạo extension `vector`, tạo bảng `medical_documents`, tạo Unique Index trên `chunk_key` để hỗ trợ Upsert an toàn không nhân đôi dữ liệu, và tạo Index HNSW (`vector_cosine_ops`, `m=16, ef_construction=64`).
- **`insert_chunks_with_embeddings(...)`**: Ghi hàng loạt (batch size 200) bằng `executemany` kết hợp mệnh đề `ON CONFLICT (chunk_key) DO UPDATE` để cập nhật dữ liệu khi nạp lại tài liệu cũ.
- **`search_similar_vectors(...)`**: Thiết lập `SET LOCAL hnsw.ef_search = 64;`, thực hiện truy vấn cosine distance (`1 - (embedding <=> $1) >= similarity_threshold`), hỗ trợ lọc linh hoạt theo `category_filter` trên JSONB metadata.

---

### III. Luồng Tương Tác & Phụ Thuộc (Coupling Analysis)

1. **Luồng Nạp Tài Liệu Offline (Ingestion Pipeline):**
   - API / Worker gọi `extract_and_chunk_pdf(pdf_path)` (`ingestion.py`) $\rightarrow$ Nhận danh sách chunks thô kèm metadata.
   - Gọi `ingest_document_chunks(chunks)` (`rag_engine.py`) $\rightarrow$ Chia lô, gọi `embed_documents()` (`embedding.py`) để sinh danh sách vector $\rightarrow$ Gọi `insert_chunks_with_embeddings()` (`pgvector_store.py`) để upsert xuống PostgreSQL.

2. **Luồng Truy Vấn Realtime (Zalo Chat / API Chat Pipeline):**
   - API Endpoint gọi `answer_medical_query(query)` (`rag_engine.py`).
   - `rag_engine.py` kiểm tra `check_input_guardrail()`.
   - Nếu qua guardrail, gọi `retrieve_medical_contexts()` $\rightarrow$ Gọi `embed_queries()` (`embedding.py`) $\rightarrow$ Gọi `search_similar_vectors()` (`pgvector_store.py`).
   - `rag_engine.py` định dạng context bằng `_format_retrieved_contexts()` $\rightarrow$ Gọi `generate_medical_answer()` $\rightarrow$ Thực thi gọi Gemini LLM (`_call_gemini`) với danh sách model fallback.

3. **Điểm Phụ Thuộc & Coupling Đáng Chú Ý:**
   - **Phụ thuộc chặt chẽ vào Gemini API:** Cả 2 tầng Embedding (`embedding.py`) và LLM Generation (`rag_engine.py`) đều phụ thuộc trực tiếp vào SDK `google-genai` và cấu hình `GEMINI_API_KEY`.
   - **Gắn kết giữa Embedding Dimension và DB Schema:** `app/core/config.py` định nghĩa `EMBEDDING_DIMENSIONS`, được tham chiếu trực tiếp khi tạo cột `vector({settings.EMBEDDING_DIMENSIONS})` trong `pgvector_store.py`.
   - **Chia sẻ định nghĩa Schema:** Cả `rag_engine.py` và các API endpoints (`api/v1/chat.py`) đều sử dụng chung `MedicalResponseSchema` từ `app/schemas/medical.py` để đảm bảo kiểu dữ liệu đầu ra đồng nhất.

---

### IV. Trạng Thái Triển Khai (Deployment Status Audit)

- **Đã triển khai hoàn chỉnh (Fully Implemented):**
  - Tầng Embedding đa luồng (realtime query + batch PDF với Semaphore, Pacing lock và Tenacity retry).
  - Tầng xử lý PDF 2 tầng (Markdown conversion, cleaning header/footer, recursive splitting, breadcrumb).
  - Tầng RAG Engine (Guardrail cấp cứu, Vector search HNSW, Context formatting, Structured JSON Output với `MedicalResponseSchema`, và cơ chế Model Fallback tự động).
  - Tầng Vector Database (Asyncpg connection pool, vector extension, HNSW index, Upsert qua `chunk_key`).
- **Triển khai một phần / Chưa thể xác minh (Partial / Unverified):**
  - **Zalo Webhook Service (`app/services/zalo_service.py` hoặc endpoint tương tự):** Hiện tại file `app/services/zalo_service.py` đang có dung lượng `0 bytes` (chưa viết code nghiệp vụ xử lý tin nhắn từ Zalo OA, mặc dù schema `app/schemas/zalo.py` và các ghi chú router đã được chuẩn bị sẵn). Toàn bộ hệ thống hiện đang phục vụ qua API Chat chung (`api/v1/chat.py`).