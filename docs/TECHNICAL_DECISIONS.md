# Medical RAG Zalo - Quyết định kỹ thuật

> Mỗi quyết định gồm: bối cảnh, quyết định đã thực hiện, bằng chứng trong code, và hệ quả.
> Các điểm yếu phát sinh từ quyết định được chuyển sang [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md).

---

## Danh mục

| ID | Chủ đề | Tóm tắt |
|---|---|---|
| TD-01 | Truy cập DB | asyncpg thuần thay vì ORM |
| TD-02 | Kho lưu trữ vector | PostgreSQL + pgvector thay vì vector DB riêng |
| TD-03 | Chỉ mục tìm kiếm | HNSW với cosine distance |
| TD-04 | Mô hình AI | Gemini cho cả embedding và LLM |
| TD-05 | Phân loại embedding | Task type bất đối xứng DOCUMENT và QUERY |
| TD-06 | Chiến lược chunking | Hai tầng: tiêu đề Markdown rồi ký tự, kèm breadcrumb |
| TD-07 | Định danh chunk và upsert | `chunk_key` theo `source:chunk_index` |
| TD-08 | Chống bịa đặt | Ngưỡng similarity và từ chối khi không có Context |
| TD-09 | Đầu ra có cấu trúc | JSON schema từ Pydantic |
| TD-10 | Độ tin cậy LLM | Chuỗi fallback model theo mã lỗi |
| TD-11 | An toàn cấp cứu | Guardrail từ khóa trước mọi lời gọi tốn kém |
| TD-12 | Lưu trạng thái hội thoại | Stateless |
| TD-13 | Xử lý lỗi | Exception có cờ `retryable` và handler tập trung |
| TD-14 | Điều tiết embedding | Hai chiến lược retry và pacing cho query và batch |
| TD-15 | Cấu hình | pydantic-settings đọc từ `.env` |
| TD-16 | Nạp tài liệu | Script CLI thay vì worker hay endpoint |

---

## TD-01. Truy cập DB bằng asyncpg thuần, không dùng ORM

- **Bối cảnh:** Hệ thống chỉ có một bảng và các truy vấn chủ yếu là upsert hàng loạt và tìm kiếm vector.
- **Quyết định:** Dùng `asyncpg` với SQL viết tay. Đăng ký codec vector bằng `register_vector` trong callback `init_conn`.
- **Bằng chứng:** `app/db/pgvector_store.py` (DDL và SQL trực tiếp). `app/models/` không có class ORM nào.
- **Hệ quả:**
  - Ưu điểm: kiểm soát được SQL và `SET LOCAL`, không có overhead ORM.
  - Nhược điểm: không có migration tự động, schema nằm trong code Python ([DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) mục 10).

---

## TD-02. PostgreSQL + pgvector làm kho lưu trữ thống nhất

- **Bối cảnh:** Cần lưu cả văn bản, metadata có cấu trúc và vector trong một hệ thống để đơn giản hóa vận hành.
- **Quyết định:** Một bảng `medical_documents` với cột `content` (TEXT), `metadata` (JSONB) và `embedding` (vector).
- **Bằng chứng:** `init_vector_db()` trong `pgvector_store.py`. `docker-compose.yml` dùng image `pgvector/pgvector:pg16`.
- **Hệ quả:**
  - Lọc theo metadata và tìm kiếm vector nằm trong cùng một truy vấn SQL.
  - Không tách được tải đọc và ghi vector sang hệ thống khác mà không thay đổi nhiều.

---

## TD-03. Chỉ mục HNSW với cosine distance

- **Bối cảnh:** Cần tìm kiếm nhanh trên tập chunk tăng dần.
- **Quyết định:** `USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`. Khi truy vấn, đặt `SET LOCAL hnsw.ef_search = 64`.
- **Bằng chứng:** `pgvector_store.py` dòng 83-90 và 161.
- **Hệ quả:**
  - Tham số `ef_search` được hardcode, không đưa qua cấu hình. Thay đổi cần sửa code.
  - Không có bộ đo recall. Không biết `ef_search=64` đã đủ tốt hay chưa.
  - HNSW không hỗ trợ tốt khi lọc theo `category` làm giảm mạnh số ứng viên. Cần đo thực tế.

---

## TD-04. Gemini cho cả embedding và sinh câu trả lời

- **Bối cảnh:** Cần một nhà cung cấp AI duy nhất để giảm số khóa API và số SDK.
- **Quyết định:** `gemini-embedding-001` (cấu hình 768 chiều qua `output_dimensionality`, theo ghi chú "Matryoshka" trong `config.py`) và chuỗi model Gemini cho LLM.
- **Bằng chứng:** `app/core/config.py` dòng 11-12, `embedding.py` dòng 149-153, `rag_engine.py` dòng 35-39.
- **Hệ quả:**
  - Phụ thuộc chặt vào một nhà cung cấp. Đổi nhà cung cấp cần sửa hai module và schema vector.
  - Hai client `genai.Client` được tạo độc lập ở `rag_engine.py` và `embedding.py`, có cấu hình timeout khác nhau.

---

## TD-05. Task type bất đối xứng cho tài liệu và câu hỏi

- **Bối cảnh:** Câu hỏi ngắn và đoạn văn dài có phân bố khác nhau. Mô hình retrieval của Gemini hỗ trợ tách hai vai trò.
- **Quyết định:** Chunk nạp với `RETRIEVAL_DOCUMENT`. Câu hỏi truy vấn với `RETRIEVAL_QUERY`.
- **Bằng chứng:** `embed_documents` và `embed_queries` trong `embedding.py` dòng 256-271.
- **Hệ quả:** Bắt buộc dùng cùng model và cùng số chiều cho cả hai phía. Nếu đổi model, phải nạp lại toàn bộ tài liệu.

---

## TD-06. Chunking hai tầng kèm breadcrumb

- **Bối cảnh:** PDF y khoa có cấu trúc tiêu đề. Chunk đứng riêng mất ngữ cảnh nếu không có tiêu đề.
- **Quyết định:**
  1. `MarkdownHeaderTextSplitter` theo `#`, `##`, `###` (giữ headers trong metadata).
  2. `RecursiveCharacterTextSplitter` với `chunk_size=600`, `chunk_overlap=100`, separators `["\n\n", "\n", ". ", " ", ""]`.
  3. Gắn `Tiêu đề: h1 > h2 > h3` vào đầu `content` trước khi embed.
- **Bằng chứng:** `ingestion.py` dòng 107-153.
- **Hệ quả:**
  - Tiêu đề xuất hiện hai lần: trong `content` và trong `metadata.headers`. Tốn dung lượng, nhưng giúp embedding có ngữ cảnh.
  - Ngưỡng 600 ký tự được hardcode mặc định trong hàm, không đưa qua `Settings`.
  - Overlap 100 ký tự làm tăng số chunk và chi phí embedding.

---

## TD-07. Định danh chunk theo `source:chunk_index` và upsert

- **Bối cảnh:** Cần nạp lại tài liệu nhiều lần mà không nhân đôi dữ liệu.
- **Quyết định:**
  - `chunk_key = "<source>:<chunk_index>"`, có UNIQUE INDEX.
  - Trước khi nạp lại một file, xóa toàn bộ bản ghi có cùng `source`.
  - Ghi bằng `ON CONFLICT (chunk_key) DO UPDATE`.
- **Bằng chứng:** `pgvector_store.py` dòng 71-80, 123, 132-138. `scripts/ingest_pdfs.py` dòng 24-32, 71.
- **Hệ quả:**
  - `chunk_index` là vị trí, không phải định danh nội dung. Khi nội dung thay đổi, các chunk sau có thể đổi chỉ số.
  - Xóa và ghi không atomic (xem [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) mục D-08).

---

## TD-08. Chống bịa đặt bằng ngưỡng similarity và từ chối khi không có Context

- **Bối cảnh:** Yêu cầu nghiệp vụ không cho phép LLM tự suy đoán liều dùng thuốc.
- **Quyết định:**
  - Chỉ lấy chunk có `similarity >= 0.5`, tối đa `top_k=3`.
  - Nếu không có chunk nào, trả về câu từ chối cố định và không gọi LLM.
  - `SYSTEM_INSTRUCTION` yêu cầu chỉ dùng Context và cấm tự suy đoán liều dùng.
- **Bằng chứng:** `answer_medical_query` trong `rag_engine.py` dòng 259-270. `SYSTEM_INSTRUCTION` dòng 43-47.
- **Hệ quả:**
  - Ngưỡng 0.5 không được đánh giá trên bộ dữ liệu thực. Có thể quá chặt hoặc quá lỏng.
  - Ràng buộc "không bịa liều" chỉ dựa vào prompt, không có kiểm tra hậu xử lý trên `recommended_dosage`.

---

## TD-09. Đầu ra có cấu trúc bằng JSON schema từ Pydantic

- **Bối cảnh:** Client cần các trường cố định (cảnh báo, liều, nguồn).
- **Quyết định:** Truyền `response_schema=MedicalResponseSchema` và `response_mime_type="application/json"` cho Gemini. Validate lại bằng Pydantic, kèm validator độ dài tối thiểu 10 ký tự cho `answer`.
- **Bằng chứng:** `_call_gemini` trong `rag_engine.py` dòng 71-87. `app/schemas/medical.py`.
- **Hệ quả:**
  - Schema trở thành hợp đồng giữa LLM và API. Sửa schema ảnh hưởng cả hai phía.
  - Dùng `thinking_level="low"` để giảm độ trễ, đánh đổi bằng khả năng suy luận.

---

## TD-10. Chuỗi fallback model theo mã lỗi

- **Bối cảnh:** Gemini có thể quá tải theo từng model, đặc biệt ở tầng miễn phí.
- **Quyết định:**
  - Thử tuần tự `LLM_MODELS`.
  - Chỉ fallback với 429, 503, 504 và lỗi transport (`httpx`, `httpx2`, `TimeoutError`, `ConnectionError`).
  - Các lỗi khác dừng ngay với 502.
- **Bằng chứng:** `FALLBACK_STATUS_CODES` và vòng lặp trong `generate_medical_answer` (`rag_engine.py` dòng 41, 154-211).
- **Hệ quả:**
  - Thời gian chờ tối đa là số model nhân với `LLM_TIMEOUT_MS` (30s), không có deadline tổng cho request.
  - Thứ tự và tên model nằm trong code.

---

## TD-11. Guardrail cấp cứu trước mọi lời gọi tốn kém

- **Bối cảnh:** Tình huống nguy hiểm không được chờ DB hay LLM.
- **Quyết định:** So khớp chuỗi con với `EMERGENCY_KEYWORDS`, trả cảnh báo cố định kèm `urgency_flag=True`.
- **Bằng chứng:** `check_input_guardrail` (`rag_engine.py` dòng 49-66), gọi trong `answer_medical_query` và `generate_medical_answer`.
- **Hệ quả:**
  - Không có chuẩn hóa tiếng Việt (bỏ dấu, viết tắt, lỗi chính tả), nên có thể bỏ sót.
  - Khớp chuỗi con có thể gây báo động nhầm với câu có từ tương tự.
  - Không có bộ test riêng cho guardrail trong repo (xem [PROJECT_STATUS.md](./PROJECT_STATUS.md)).

---

## TD-12. Chat stateless

- **Bối cảnh:** Giai đoạn đầu, ưu tiên hoàn thiện pipeline hỏi đáp.
- **Quyết định:** Mỗi request độc lập. Không lưu lịch sử. `user_id` chỉ được nhận.
- **Bằng chứng:** `chat.py` không đọc `payload.user_id`. `app/models/chat_history.py` trống.
- **Hệ quả:** Không có ngữ cảnh đa lượt. Không có dữ liệu để đánh giá hay cải thiện hệ thống theo người dùng.

---

## TD-13. Exception có cờ `retryable` và handler tập trung

- **Bối cảnh:** Client cần biết lỗi nào nên thử lại.
- **Quyết định:**
  - `AppBaseException(message, status_code, retryable)`.
  - `TransientServiceException` là subclass với 503 và `retryable=True`.
  - Hai handler toàn cục trong `main.py` trả về JSON thống nhất.
- **Bằng chứng:** `app/core/exceptions.py`, `app/main.py` dòng 39-40.
- **Hệ quả:**
  - `error_type` chỉ có ba giá trị, nên lỗi phía upstream bị gắn là `BusinessError`.
  - Handler `Exception` nuốt chi tiết lỗi, chỉ log ở tầng service, không log ở handler.

---

## TD-14. Hai chiến lược retry và pacing cho embedding

- **Bối cảnh:** Gemini free tier giới hạn số request mỗi phút. Truy vấn người dùng cần phản hồi nhanh. Nạp tài liệu có thể chậm.
- **Quyết định:**

| Thuộc tính | Luồng query (`str`) | Luồng batch (`list[str]`) |
|---|---|---|
| Timeout | 5.0s (`EMBEDDING_QUERY_TIMEOUT`) | 20.0s (`EMBEDDING_BATCH_TIMEOUT`) |
| Số lần retry | 2 (hardcode) | 5 (`EMBEDDING_BATCH_MAX_RETRIES`) |
| Backoff | `wait_exponential(0.5, min 0.5, max 2)` | `wait_exponential(5, min 15, max 60)`, tối thiểu bằng `retryDelay` từ server |
| Pacing | Không | Khoảng cách tối thiểu 12s giữa hai request (`_wait_for_request_slot`) |
| Concurrency | Không giới hạn | `EMBEDDING_MAX_CONCURRENCY=1` |

- **Bằng chứng:** `embedding.py` dòng 26-30, 120-131, 189-247. `config.py` dòng 13-18.
- **Hệ quả:**
  - Trạng thái pacing (`_last_request_started_at`, `_pace_lock`) là biến module-level. Với nhiều worker Uvicorn, mỗi process có pacing riêng.
  - Luồng batch được tối ưu cho chạy thủ công, không phù hợp để chạy trong request.

---

## TD-15. Cấu hình bằng pydantic-settings

- **Bối cảnh:** Cần tham số hóa môi trường và tách bí mật khỏi code.
- **Quyết định:** Lớp `Settings(BaseSettings)` đọc từ `.env`, `extra="ignore"`. Khóa bí mật dùng `SecretStr`.
- **Bằng chứng:** `app/core/config.py`.
- **Hệ quả:**
  - Một số giá trị vẫn hardcode ngoài `Settings` (xem [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) mục D-14).
  - Giá trị mặc định của mật khẩu DB nằm trong code, gây rủi ro bảo mật (mục D-03).

---

## TD-16. Nạp tài liệu bằng script CLI thay vì worker hay endpoint

- **Bối cảnh:** Tài liệu y khoa thay đổi ít. Không cần cập nhật theo thời gian thực.
- **Quyết định:** `scripts/ingest_pdfs.py` đọc toàn bộ `data/raw_pdfs/*.pdf`, chạy tuần tự, chạy thủ công.
- **Bằng chứng:** `scripts/ingest_pdfs.py`. Không có endpoint nạp tài liệu trong `api/`.
- **Hệ quả:**
  - Không có API để quản trị viên nạp tài liệu.
  - Không có trạng thái tiến trình được lưu lại ngoài log console.
  - Cần thao tác trên máy chủ để cập nhật dữ liệu.
