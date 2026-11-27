Báo cáo kết quả kiểm tra các thành phần tích hợp và chức năng còn lại của project **Medical RAG Zalo** dựa trên việc phân tích trực tiếp mã nguồn trong source code.

---

### 1. Authentication Overview
* **Trạng thái thực tế:** **Chưa tích hợp xác thực**.
* **Chi tiết mã nguồn & Bằng chứng:**
  * File `app/core/security.py` hiện tại hoàn toàn trống (`0 bytes`).
  * Trong `api/v1/chat.py`, endpoint POST `/api/v1/chat` mở công khai (`public`), không có dependency xác thực như `OAuth2PasswordBearer`, không kiểm tra JWT Token hay API Key bắt buộc.
  * Các client khi gọi API trực tiếp truyền `user_id` tự do trong request body (`ChatRequest` schema trong `app/schemas/chat_schema.py`).

---

### 2. Conversation Management
* **Trạng thái thực tế:** **Hoạt động theo cơ chế Stateless (Chưa lưu trữ lịch sử hội thoại)**.
* **Chi tiết mã nguồn & Bằng chứng:**
  * File ORM model `app/models/chat_history.py` đang trống (`0 bytes`), CSDL không có bảng `chat_history` hay `chat_sessions`.
  * Endpoint `POST /api/v1/chat` tiếp nhận câu hỏi của `user_id`, thực hiện truy vấn RAG và trả về câu trả lời độc lập cho từng request mà không lưu lại lịch sử tin nhắn của người dùng vào cơ sở dữ liệu.

---

### 3. External Integrations
* **Các tích hợp bên ngoài thực tế:**
  1. **Google Gemini AI SDK (`google-genai`)**:
     * **Vai trò:** Xử lý sinh câu trả lời y tế thông minh (LLM) và tạo vector embedding (Embedding).
     * **Bằng chứng:** Sử dụng `genai.Client` trong `app/services/rag_engine.py` (với các model Gemini Flash dự phòng như `gemini-3.8-flash`, `gemini-3.1-flash-lite`, `gemini-3.5-flash`) và `app/services/embedding.py` (với model `gemini-embedding-001`, cấu hình 768 chiều và cơ chế retry thông minh qua `tenacity`).
  2. **Zalo OA Integration**:
     * **Vai trò:** Dự kiến tích hợp webhook tiếp nhận tin nhắn từ Zalo Official Account.
     * **Bằng chứng:** 
       * Trong `app/core/config.py` đã định nghĩa các biến cấu hình: `ZALO_APP_SECRET` và `ZALO_OA_ACCESS_TOKEN`.
       * Tuy nhiên, các file như `app/schemas/zalo.py`, `app/services/zalo_service.py` hiện đang trống (`0 bytes`) và router `zalo.router` chưa được gắn vào `api/v1/router.py` (mới chỉ có chú thích). **Tuyệt đối không khẳng định tích hợp Zalo hoạt động** vì chưa có endpoint webhook hiện thực hóa.

---

### 4. Caching & Background Processing
* **Caching (Redis):**
  * **Trạng thái:** Mới chỉ có cấu hình hạ tầng.
  * **Bằng chứng:** 
    * Trong `app/core/config.py` có khai báo biến `REDIS_URL: str = 'redis://localhost:6379/0'`.
    * Trong `docker-compose.yml` có service `redis` (Redis 7-alpine). 
    * File `app/db/redis_cache.py` hiện đang trống (`0 bytes`) và chưa có logic caching Redis nào được gọi trong luồng chat hay RAG engine.
* **Background Tasks:**
  * **Trạng thái:** Được thiết kế cho luồng nạp tài liệu ngoại tuyến (Offline Ingestion), chưa dùng qua FastAPI `BackgroundTasks` cho webhook Zalo (do webhook Zalo chưa code).
  * **Bằng chứng:** Hàm `ingest_document_chunks` trong `app/services/rag_engine.py` và script `scripts/ingest_pdfs.py` thực hiện xử lý bất đồng bộ theo batch để nạp dữ liệu PDF vào PostgreSQL.

---

### 5. Logging & Error Handling
* **Logging:**
  * **Trạng thái:** Sử dụng module `logging` chuẩn của Python xuyên suốt các service (`app/services/embedding.py`, `app/services/rag_engine.py`) để ghi log cảnh báo khi retry, log lỗi kết nối Gemini, và đo thời gian xử lý batch. File `app/core/logging.py` hiện đang trống (`0 bytes`).
* **Error Handling:**
  * **Trạng thái:** Đã xây dựng cơ chế bắt lỗi tập trung tại tầng API.
  * **Bằng chứng:** 
    * `app/core/exceptions.py` định nghĩa các exception chuẩn `AppBaseException` và `TransientServiceException` (lỗi tạm thời 503 có thể retry).
    * `app/main.py` đăng ký global exception handlers (`app_exception_handler` và `unhandled_exception_handler`) trả về JSON chuẩn hóa (`success`, `error_type`, `retryable`, `detail`).
    * Middleware `add_process_time_header` trong `app/main.py` tự động đo và trả về header `X-Process-Time-Ms` cho mọi HTTP Request.

---

### 6. Other Modules
* **PostgreSQL + pgvector (`app/db/pgvector_store.py`)**: Module quản lý connection pool `asyncpg`, tự động khởi tạo extension `vector`, tạo bảng `medical_documents` với cột `embedding vector(768)` và chỉ mục `HNSW` (`vector_cosine_ops`), hỗ trợ upsert chống trùng qua `chunk_key` và tìm kiếm tương đồng vector.
* **Ingestion Service (`app/services/ingestion.py`)**: Module xử lý chuyển đổi PDF sang Markdown (`pymupdf4llm`), làm sạch header/footer lặp lại, băm tài liệu hai tầng (`MarkdownHeaderTextSplitter` kết hợp `RecursiveCharacterTextSplitter`) và gắn Breadcrumb tiêu đề.

---

### 7. Missing / Unverified Information
1. **Zalo Webhook & Service:** Các file liên quan đến Zalo (`app/schemas/zalo.py`, `app/services/zalo_service.py`, endpoint webhook) chưa được hiện thực hóa mã nguồn, mới chỉ dừng lại ở biến cấu hình môi trường và ghi chú định hướng.
2. **Redis Caching Integration:** Biến cấu hình `REDIS_URL` và container Docker đã sẵn sàng nhưng chưa có logic code tích hợp cache câu hỏi/câu trả lời.
3. **Authentication & User Management:** Chưa có cơ chế bảo mật API, phân quyền hoặc quản lý tài khoản người dùng (`app/core/security.py` trống, không có bảng `users`).
4. **Chat Session History:** Model quản lý lịch sử hội thoại (`app/models/chat_history.py`) hiện đang trống, hệ thống đang hoạt động ở chế độ Stateless.