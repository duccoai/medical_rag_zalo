# Medical RAG Zalo - Tài liệu API

> Tài liệu này mô tả các endpoint thực tế trong `app/main.py` và `api/v1/chat.py`.
> Luồng xử lý phía sau endpoint: [DATA_FLOW.md](./DATA_FLOW.md). Schema bảng: [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md).

---

## 1. Thông tin chung

| Thuộc tính | Giá trị |
|---|---|
| Base URL (cục bộ) | `http://localhost:8000` |
| Tiền tố API | `/api/v1` |
| Định dạng | JSON (`application/json`) |
| Tài liệu tương tác | `/docs` (Swagger UI), `/redoc` (do FastAPI sinh) |
| CORS | `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True` |
| Header phản hồi | `X-Process-Time-Ms`: thời gian xử lý tính theo mili giây, thêm cho mọi response |

---

## 2. Xác thực và phân quyền

| Hạng mục | Trạng thái |
|---|---|
| Cơ chế | **Chưa có** |
| Bằng chứng | `app/core/security.py` trống; endpoint không khai báo dependency nào |
| Hệ quả | Mọi client có thể gọi `POST /api/v1/chat` mà không cần token hay API key |
| `user_id` | Client tự khai báo trong body, không được xác minh, và không được dùng trong xử lý |

Không có endpoint đăng ký, đăng nhập hay quản lý người dùng.

---

## 3. Danh sách endpoint

| # | Method | URL | Tags | Mô tả | Xác thực | Trạng thái |
|---|---|---|---|---|---|---|
| 1 | `GET` | `/health` | System | Kiểm tra server còn hoạt động | Không | Hoàn thiện |
| 2 | `POST` | `/api/v1/chat` | Chat | Hỏi đáp tư vấn y tế qua RAG | Không | Hoàn thiện |

### 3.1. `GET /health`

| Mục | Nội dung |
|---|---|
| Request | Không có tham số, không có body |
| Response `200` | `{"status": "healthy", "project": "<PROJECT_NAME>", "version": "<VERSION>"}` |
| Service được gọi | Không gọi service nào, đọc trực tiếp `settings` |
| Ghi chú | Không kiểm tra kết nối DB hay Gemini, nên luôn trả 200 khi process còn chạy |

### 3.2. `POST /api/v1/chat`

Handler: `chat_with_bot` trong `api/v1/chat.py`. Router có prefix `/chat`, gắn vào `/api/v1` qua `api_router`.

#### Request body: `ChatRequest`

| Trường | Kiểu | Bắt buộc | Ràng buộc | Mô tả |
|---|---|---|---|---|
| `user_id` | `string` | Có | `min_length=1` | Mã định danh người dùng, không được xác minh |
| `message` | `string` | Có | `min_length=2`, `max_length=1000` | Câu hỏi tư vấn |
| `category` | `string \| null` | Không | Không có ràng buộc | Lọc theo `metadata->>'category'`. Giá trị không tồn tại trả về danh sách rỗng |

```json
{
  "user_id": "user-001",
  "message": "Triệu chứng sốt xuất huyết cần theo dõi những gì?",
  "category": "tu_van_nha_thuoc"
}
```

#### Response `200`: `ChatResponse`

| Trường | Kiểu | Mặc định | Nguồn giá trị |
|---|---|---|---|
| `reply` | `string` | Bắt buộc | `MedicalResponseSchema.answer` |
| `sources` | `list[string]` | `[]` | `MedicalResponseSchema.sources` |
| `disclaimer` | `string` | Câu cảnh báo y khoa chuẩn | `MedicalResponseSchema.disclaimer` |
| `recommended_dosage` | `string \| null` | `null` | `MedicalResponseSchema.recommended_dosage` |
| `urgency_flag` | `boolean` | `false` | `MedicalResponseSchema.urgency_flag` |
| `is_mock` | `boolean` | `false` | Luôn `false`, được gán cứng trong `chat.py` |

```json
{
  "reply": "<nội dung tư vấn do LLM sinh từ Context>",
  "sources": ["<tên tài liệu và mục tham khảo>"],
  "disclaimer": "Lưu ý: Thông tin chỉ mang tính chất tham khảo, không thay thế cho chỉ định trực tiếp từ Bác sĩ.",
  "recommended_dosage": null,
  "urgency_flag": false,
  "is_mock": false
}
```

#### Các trường hợp phản hồi của endpoint

| Tình huống | HTTP | Đặc điểm |
|---|---|---|
| Câu hỏi chứa từ khóa cấp cứu | `200` | `urgency_flag=true`, `reply` là cảnh báo gọi 115, không gọi DB hay LLM |
| Không có tài liệu đạt ngưỡng 0.5 | `200` | `reply` là câu từ chối lịch sự, `sources=[]`, không gọi LLM |
| Có tài liệu, LLM trả lời thành công | `200` | Nội dung do LLM sinh theo `MedicalResponseSchema` |
| Lỗi validation request | `422` | Định dạng mặc định của FastAPI, không đi qua handler của dự án |
| Quá thời gian truy xuất, hoặc embedding lỗi tạm thời | `503` | Định dạng lỗi chuẩn, `retryable=true` |
| Tất cả model LLM quá tải | `503` | Định dạng lỗi chuẩn, `retryable=true` |
| Lỗi LLM không fallback được, hoặc lỗi embedding không retry được | `502` | Định dạng lỗi chuẩn, `retryable=false` |
| Lỗi không xác định (ví dụ DB) | `500` | Thông báo chung, không lộ chi tiết |

#### Ánh xạ sang service

```text
POST /api/v1/chat
  └─ chat_with_bot                       api/v1/chat.py
      └─ answer_medical_query            app/services/rag_engine.py
          ├─ check_input_guardrail
          ├─ retrieve_medical_contexts
          │   ├─ embed_queries           app/services/embedding.py
          │   └─ search_similar_vectors  app/db/pgvector_store.py
          ├─ _format_retrieved_contexts
          └─ generate_medical_answer
              └─ _call_gemini            (lặp qua LLM_MODELS)
```

Tham số truyền từ endpoint: `top_k=3`, `similarity_threshold=0.5`, `category_filter=payload.category`. `payload.user_id` không được truyền xuống service.

---

## 4. Định dạng lỗi chuẩn

Mọi `AppBaseException` và `TransientServiceException` được `app_exception_handler` trả về theo format:

```json
{
  "success": false,
  "error_type": "TransientError",
  "retryable": true,
  "detail": "<thông báo tiếng Việt>"
}
```

| `error_type` | Điều kiện | `retryable` |
|---|---|---|
| `TransientError` | `exc.retryable = True` | `true` |
| `BusinessError` | `exc.retryable = False` | `false` |
| `InternalServerError` | Exception không được xử lý (handler `unhandled_exception_handler`) | `false` |

Lưu ý: lỗi từ phía Gemini (HTTP 502) có `error_type` là `BusinessError`, dù có thể là lỗi hệ thống. Xem [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) mục D-12.

Lỗi validation của FastAPI (422) có format riêng: `{"detail": [ ... ]}`.

---

## 5. Giới hạn đã biết

| Hạng mục | Mô tả |
|---|---|
| Không có lịch sử hội thoại | Mỗi request độc lập, không có session |
| Không có rate limit | Không có cơ chế giới hạn số request theo `user_id` hay IP |
| Không có endpoint Zalo | `api/v1/router.py` chỉ có comment, xem [PROJECT_STATUS.md](./PROJECT_STATUS.md) |
| `sources` do LLM tạo | Không được đối chiếu với metadata của chunk đã truy xuất, xem [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) mục D-10 |
| Không có endpoint nạp tài liệu | Nạp dữ liệu chỉ thực hiện qua `scripts/ingest_pdfs.py` |
