Bản phân tích chi tiết về kiến trúc và luồng xử lý RAG thực tế của project `medical_rag_zalo` được trình bày rõ ràng dưới đây. Mọi thông tin đều được trích xuất trực tiếp từ mã nguồn thực tế của hệ thống, tuân thủ nghiêm ngặt các yêu cầu: không suy diễn, ghi rõ đường dẫn file và tên hàm/class làm bằng chứng.

---

### I. Tổng quan Kiến trúc RAG Pipeline

Project xây dựng một hệ thống RAG y tế (tích hợp Zalo chatbot) gồm 2 luồng chính hoạt động độc lập nhưng liên kết chặt chẽ qua Vector Database PostgreSQL (`pgvector`):
1. **Luồng Ingest (Nạp tài liệu Offline):** PDF -> Markdown -> Làm sạch rác -> Băm 2 tầng (Header + Character) + Gắn Breadcrumb -> Embedding batch (Gemini) -> Lưu trữ PostgreSQL (`pgvector` với HNSW Index & Upsert chống trùng).
2. **Luồng Query (Thời gian thực Online / Zalo Chat):** Nhận câu hỏi -> Lớp bảo vệ Guardrail (Cấp cứu) -> Embed câu hỏi (`RETRIEVAL_QUERY`) -> Truy vấn HNSW trong pgvector (Cosine distance + Ngưỡng `similarity_threshold`) -> Định dạng Context kèm Nguồn -> Gọi LLM Gemini (Hỗ trợ Fallback model & Structured JSON Output qua Pydantic) -> Trả về kết quả tư vấn y tế.

---

### II. Chi tiết từng thành phần trong RAG Pipeline

#### 1. Document Processing & Document Chunking
* **Cách tiếp nhận tài liệu:** 
  * Tài liệu đầu vào là các file PDF (ví dụ: `Triệu-chứng-bệnh-ở-nhà-thuốc.pdf`).
  * File được chuyển đổi toàn bộ thành chuỗi Markdown liền mạch bằng thư viện `pymupdf4llm`.
  * **File chứng thực:** `app/services/ingestion.py` — Hàm `pdf_to_markdown(pdf_path: Path) -> str` (dòng 76).
* **Cơ chế làm sạch (Cleaning):**
  * Chuẩn hoá lỗi mã hoá font tiếng Việt (`"ƣ/Ƣ"` thành `"ư/Ư"`).
  * Lọc bỏ header/footer lặp lại dựa trên tần số xuất hiện (`REPEAT_THRESHOLD = 5`, độ dài `<= 80` ký tự) và loại bỏ các dòng chứa số trang đơn lẻ (`PAGE_NUMBER_PATTERN`).
  * **File chứng thực:** `app/services/ingestion.py` — Hàm `clean_markdown_text(markdown: str) -> str` (dòng 50).
* **Cơ chế chia Chunk (Băm 2 tầng):**
  * **Tầng 1 (Cấu trúc tiêu đề):** Sử dụng `MarkdownHeaderTextSplitter` để tách theo các cấp tiêu đề Markdown (`#`, `##`, `###`), giúp giữ nguyên phân cấp ngữ nghĩa ban đầu của văn bản.
  * **Tầng 2 (Độ dài ký tự):** Sử dụng `RecursiveCharacterTextSplitter` với `chunk_size = 600`, `chunk_overlap = 100`, và các separators `["\n\n", "\n", ". ", " ", ""]` để băm tiếp các phần vượt quá giới hạn.
  * **Cơ chế Breadcrumb (Ngữ cảnh phân cấp):** Mỗi sub-chunk được tự động gắn thêm đường dẫn tiêu đề phân cấp (`Header 1 > Header 2 > Header 3`) lên đầu nội dung trước khi đưa đi embedding để ngữ cảnh không bị mất khi đứng độc lập.
  * **File chứng thực:** `app/services/ingestion.py` — Hàm `chunk_markdown(...)` (dòng 110) và hàm `_with_breadcrumb(...)` (dòng 99).

#### 2. Embedding Generation
* **Model sử dụng:** `settings.EMBEDDING_MODEL` (Gemini Embedding model) với cấu hình `output_dimensionality` (được định nghĩa qua `settings.EMBEDDING_DIMENSIONS`).
* **Phân loại Task Type:**
  * `RETRIEVAL_DOCUMENT`: Dành cho các chunk tài liệu nạp vào (`app/services/embedding.py` - hàm `embed_documents`, dòng 256).
  * `RETRIEVAL_QUERY`: Dành cho câu hỏi truy vấn của người dùng (`app/services/embedding.py` - hàm `embed_queries`, dòng 267).
* **Cơ chế Batching, Pacing & Retry thông minh:**
  * Chia nhỏ danh sách chunk thành các lô (`EMBEDDING_BATCH_SIZE`).
  * Sử dụng `asyncio.Semaphore` (`EMBEDDING_MAX_CONCURRENCY`) và cơ chế Pacing (`_wait_for_request_slot`) để kiểm soát tốc độ request, tránh bị quá giới hạn RPM (Requests Per Minute) của API.
  * Tích hợp thư viện `tenacity` với chiến lược Exponential Backoff (`wait_exponential`) và tự động bóc tách tham số `retryDelay` từ lỗi HTTP 429 do server trả về để chờ đúng thời gian yêu cầu.
  * **File chứng thực:** `app/services/embedding.py` — Các hàm `_embed_core`, `_embed_single_payload_with_retry`, `_batch_wait`.

#### 3. Vector Database / pgvector
* **Công nghệ:** PostgreSQL kết hợp extension `pgvector` (`CREATE EXTENSION IF NOT EXISTS vector;`).
* **Lưu trữ & Cấu trúc bảng:**
  * Bảng `medical_documents` gồm các cột: `id BIGSERIAL PRIMARY KEY`, `content TEXT NOT NULL`, `metadata JSONB NOT NULL`, `embedding vector(DIMENSIONS) NOT NULL`, và `chunk_key TEXT`.
  * `chunk_key` có định dạng `"<source>:<chunk_index>"` được áp đặt `UNIQUE INDEX` nhằm hỗ trợ cơ chế **Upsert** (`ON CONFLICT (chunk_key) DO UPDATE`), giúp chạy lại script nạp tài liệu thoải mái mà không bị nhân đôi bản ghi.
* **Chỉ mục tìm kiếm (Indexing):**
  * Sử dụng chỉ mục **HNSW** (`Hierarchical Navigable Small World`) với toán tử khoảng cách Cosine (`vector_cosine_ops`) và cấu hình `WITH (m = 16, ef_construction = 64)` để tối ưu tốc độ tìm kiếm trên tập dữ liệu lớn.
  * **File chứng thực:** `app/db/pgvector_store.py` — Hàm `init_vector_db()` (dòng 48) và `insert_chunks_with_embeddings()` (dòng 95).

#### 4. Retrieval & Search (Truy vấn)
* **Luồng tìm kiếm thời gian thực:**
  * Nhận chuỗi câu hỏi từ người dùng -> Gọi `embed_queries(query)` lấy vector 1D -> Gọi `search_similar_vectors(...)`.
  * Trong database, hệ thống thiết lập cục bộ độ sâu tìm kiếm `SET LOCAL hnsw.ef_search = 64;` trong một transaction để cân bằng giữa tốc độ và độ chính xác (recall).
  * Sử dụng toán tử Cosine Distance (`<=>`) để tính điểm tương đồng: `1 - (embedding <=> $1) AS similarity`.
  * Áp dụng bộ lọc ngưỡng điểm tối thiểu (`similarity_threshold`, mặc định `0.5`), bộ lọc danh mục tùy chọn (`category_filter` qua JSONB `metadata->>'category'`), và giới hạn số lượng kết quả (`top_k`).
  * **File chứng thực:** `app/db/pgvector_store.py` — Hàm `search_similar_vectors(...)` (dòng 147) và `app/services/rag_engine.py` — Hàm `retrieve_medical_contexts(...)` (dòng 113).

#### 5. Context Construction & Prompt Templates
* **Xây dựng Context:**
  * Các chunk tìm được từ pgvector được định dạng lại qua hàm `_format_retrieved_contexts(matches)` để gắn kèm thông tin nguồn rõ ràng (Tên file, tiêu đề phân cấp `h1 > h2...`, số trang và độ tương đồng sim).
  * **File chứng thực:** `app/services/rag_engine.py` — Hàm `_format_retrieved_contexts(...)` (dòng 214).
* **System Instruction & Prompt Structure:**
  * **System Instruction:** Xác định vai trò "Trợ lý Y tế Thông minh", bắt buộc chỉ dùng thông tin trong Context được cung cấp, tuyệt đối không tự suy đoán liều dùng thuốc, và từ chối lịch sử nếu Context thiếu thông tin.
  * **Prompt Template:**
    ```text
    Context:
    [Tài liệu 1 | Nguồn: ... | Độ tương đồng: ...]
    <nội dung chunk>
    ---
    Câu hỏi của người dùng: <query>
    ```
  * **File chứng thực:** `app/services/rag_engine.py` — Hằng số `SYSTEM_INSTRUCTION` (dòng 43) và hàm `generate_medical_answer(...)` (dòng 139).

#### 6. LLM Integration & Response Generation (kèm Citations)
* **Model LLM & Fallback Chain:**
  * Sử dụng các model Gemini thông qua Google GenAI SDK (`genai.Client` với `client.aio`).
  * Hệ thống triển khai danh sách ưu tiên (`LLM_MODELS`): `"gemini-3.8-flash"` -> `"gemini-3.1-flash-lite"` -> `"gemini-3.5-flash"`.
  * Nếu gặp lỗi quá tải/hết thời gian (`FALLBACK_STATUS_CODES = {429, 503, 504}` hoặc `TransportError`/`TimeoutError`), hệ thống tự động **fallback sang model dự phòng tiếp theo**.
  * **File chứng thực:** `app/services/rag_engine.py` — Danh sách `LLM_MODELS` (dòng 35) và vòng lặp fallback trong `generate_medical_answer(...)` (dòng 154).
* **Structured Output & Citations:**
  * Ép buộc LLM trả về kết quả tuân thủ schema Pydantic `MedicalResponseSchema` (chứa các trường: `answer`, `recommended_dosage`, `sources`, `urgency_flag`) thông qua cấu hình `response_mime_type="application/json"` và `response_schema=MedicalResponseSchema`.
  * **Trích dẫn (Citations):** Có triển khai thực tế. Nguồn tài liệu (`sources`) được trích xuất trực tiếp từ metadata của các chunk đã retrieve và đưa vào cấu trúc JSON trả về của LLM.
  * **File chứng thực:** `app/schemas/medical.py` (định nghĩa schema) và `app/services/rag_engine.py` — Hàm `_call_gemini(...)` (dòng 71).

---

### III. Cơ chế Xử lý Lỗi, Guardrail & Giới hạn

1. **Lớp bảo vệ Guardrail (Khẩn cấp):**
   * Kiểm tra từ khóa cấp cứu (`EMERGENCY_KEYWORDS` như `"tự tử"`, `"uống thuốc trừ sâu"`, `"ngưng thở"`, `"bất tỉnh"`, v.v.) ngay trước khi gọi DB hay LLM. Nếu khớp, trả về ngay cảnh báo khẩn cấp mà không tốn token hay thời gian truy vấn.
   * **File chứng thực:** `app/services/rag_engine.py` — Hàm `check_input_guardrail(...)` (dòng 56).
2. **Kiểm tra rỗng (Empty Context Handling):**
   * Nếu không tìm thấy chunk nào đạt `similarity_threshold`, hệ thống chủ động dừng lại và trả về thông báo từ chối lịch sự từ cơ sở dữ liệu y khoa, tránh tình trạng LLM "bịaa đặt" (hallucination).
   * **File chứng thực:** `app/services/rag_engine.py` — `answer_medical_query(...)` (dòng 260).
3. **Timeout & Giới hạn thời gian thực:**
   * Luồng query realtime Zalo giới hạn thời gian truy xuất (`retrieval_timeout = 6.0s`) bằng `asyncio.wait_for` để đảm bảo phản hồi nhanh chóng cho người dùng.
   * **File chứng thực:** `app/services/rag_engine.py` — Hàm `retrieve_medical_contexts(...)` (dòng 130).
4. **Phân biệt tính năng In-code vs Mới khai báo:**
   * **Vector Search (pgvector + HNSW):** Đã triển khai hoàn chỉnh.
   * **Hybrid Search (Keyword + Vector):** *Chưa thấy implementation* (chỉ thuần túy Vector Search qua Cosine distance).
   * **Reranking:** *Chưa thấy implementation* (chỉ lấy top_k dựa trực tiếp trên điểm similarity của vector search).
   * **Caching (Redis Cache):** Project có file `app/db/redis_cache.py` khai báo, tuy nhiên trong luồng RAG chính (`rag_engine.py` hay `api/v1/chat.py`) hiện chưa tích hợp gọi cache trực tiếp vào pipeline hỏi đáp.

---
*Tóm lại, project xây dựng một pipeline RAG y tế rất bài bản, chặt chẽ ở các khâu làm sạch Markdown, băm 2 tầng kèm Breadcrumb, quản lý retry/pacing embedding thông minh, đánh chỉ mục HNSW trên PostgreSQL, cùng cơ chế Fallback model LLM đa tầng và Structured Output Pydantic.*