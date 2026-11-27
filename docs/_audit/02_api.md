Dưới đây là bản phân tích chi tiết các thành phần API của project hiện tại (`medical_rag_zalo`) dựa trên phạm vi và các mục tiêu yêu cầu.

---

### I. Cấu trúc Thành phần API & Router
Project được xây dựng bằng **FastAPI**, với cấu trúc phân tầng rõ ràng:
1. **Application Entrypoint (`app/main.py`)**: Khởi tạo ứng dụng FastAPI, cấu hình CORS Middleware, Custom Process Time Middleware, đăng ký Exception Handlers (`AppBaseException`, `Exception`), health check endpoint và mount toàn bộ router v1 vào tiền tố `/api/v1`.
2. **API Router tổng hợp (`api/v1/router.py`)**: Tập hợp các sub-router thuộc phiên bản v1 (hiện tại bao gồm `chat.router`).
3. **Routers & Endpoints (`api/v1/chat.py`)**: Chứa router `/chat` gắn trực tiếp vào pipeline RAG y tế thông minh.
4. **Schemas (`app/schemas/`)**:
   - `chat_schema.py`: Định nghĩa `ChatRequest` và `ChatResponse` cho API client/Zalo.
   - `medical.py`: Định nghĩa `MedicalResponseSchema` cùng các Pydantic field validators cho RAG engine.
   - `zalo.py`: (Hiện đang trống, chuẩn bị cho webhook Zalo OA sau này).
5. **Authentication & Security (`app/core/security.py`)**: Hiện tại đang trống (chưa có cơ chế xác thực JWT hoặc API Key bắt buộc trên các endpoint chat).

---

### II. Chi tiết các API Endpoint thực tế

#### 1. System Health Check Endpoint
* **HTTP Method**: `GET`
* **URL**: `/health`
* **Chức năng**: Kiểm tra trạng thái hoạt động của server và phiên bản dự án.
* **Request Parameters**: Không có.
* **Request Body**: Không có.
* **Response Schema**: JSON object gồm `status`, `project`, `version`.
* **Authentication/Authorization**: Không yêu cầu (Public).
* **Validation**: Không có.
* **Gọi đến Service**: Không gọi service ngoài, đọc từ `app.core.config.settings`.
* **Trạng thái**: **Hoàn thiện**.

---

#### 2. Medical RAG Chat Endpoint
* **HTTP Method**: `POST`
* **URL**: `/api/v1/chat`
* **Tags**: `Chat`
* **Chức năng**: Tiếp nhận câu hỏi y tế từ người dùng/client, thực thi luồng RAG hoàn chỉnh (Guardrail -> Vector DB Retrieval -> Format Context -> LLM Generation) và trả về câu trả lời y tế chuẩn cấu trúc kèm cảnh báo, nguồn tài liệu và liều dùng.
* **Request Parameters**: Không có query/path parameters.
* **Request Body (`ChatRequest` schema)**:
  - `user_id` (string, bắt buộc, `min_length=1`): ID định danh người dùng.
  - `message` (string, bắt buộc, `min_length=2`, `max_length=1000`): Câu hỏi tư vấn y tế.
  - `category` (string | null, tùy chọn): Danh mục tài liệu y tế để lọc.
* **Response Schema (`ChatResponse` schema)**:
  - `reply` (string): Câu trả lời tư vấn từ hệ thống.
  - `sources` (list[string]): Danh sách tài liệu y tế trích dẫn (ví dụ: tên tài liệu, số trang, tiêu đề section).
  - `disclaimer` (string): Cảnh báo y khoa bắt buộc (mặc định: *"Lưu ý: Thông tin chỉ mang tính tham khảo..."*).
  - `recommended_dosage` (string | null): Liều dùng khuyến nghị trích xuất từ tài liệu (nếu có).
  - `urgency_flag` (boolean): Cờ đánh dấu tình trạng cấp cứu (`True` nếu phát hiện từ khóa nguy hiểm).
  - `is_mock` (boolean): Cờ đánh dấu dữ liệu thật/giả lập (`False` vì đã nối RAG thật).
* **Authentication/Authorization**: 
  - Chưa tích hợp xác thực (`app/core/security.py` đang trống). Mọi client đều gọi được trực tiếp.
* **Validation**: 
  - FastAPI + Pydantic tự động validate `ChatRequest` (kiểm tra độ dài `message`, `user_id`).
  - `MedicalResponseSchema` sử dụng `@field_validator` để kiểm tra độ dài tối thiểu của câu trả lời từ LLM (`>= 10` ký tự).
* **API gọi đến Service nào**:
  - `app.services.rag_engine.answer_medical_query(...)`
  - Gọi đến **Google GenAI SDK** (`client.aio.models.generate_content`) sử dụng các model Gemini (`gemini-3.8-flash`, `gemini-3.1-flash-lite`, `gemini-3.5-flash`) với cơ chế tự động fallback khi gặp lỗi quá tải (429/503/504).
  - Gọi đến **PostgreSQL + pgvector** (`app.db.pgvector_store`) để tìm kiếm vector tương đồng (HNSW search).
* **Trạng thái**: **Hoàn thiện**.

---

### III. Ghi nhận các Endpoint / Thành phần chưa hoàn thiện hoặc chưa xác minh được
1. **Zalo Webhook Endpoint (`api/v1/zalo_webhook.py` hoặc tương tự)**: 
   - Trong `api/v1/router.py` có ghi chú: `# api_router.include_router(zalo.router)`. File `app/schemas/zalo.py` và service `app/services/zalo_service.py` hiện đang trống hoặc chưa được cài đặt endpoint nhận tin nhắn từ Zalo OA.
2. **Authentication / Authorization**:
   - Chưa có endpoint đăng ký/đăng nhập, chưa có middleware kiểm tra JWT Token hay API Key bảo vệ các route `/api/v1/chat`.
3. **Chat History / Session Management**:
   - Mặc dù có model database `app/models/chat_history.py`, endpoint `/api/v1/chat` hiện tại chưa lưu trữ lịch sử hội thoại của `user_id` vào CSDL sau mỗi lượt hỏi đáp (tính năng stateless).