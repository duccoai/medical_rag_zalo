# Medical RAG Zalo - Tổng quan dự án

> Tài liệu này mô tả mục tiêu, công nghệ, cấu trúc thư mục và cách khởi chạy hệ thống.
> Kiến trúc chi tiết: [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md). Luồng dữ liệu: [DATA_FLOW.md](./DATA_FLOW.md).
> Trạng thái từng module: [PROJECT_STATUS.md](./PROJECT_STATUS.md).

---

## 1. Mục tiêu hệ thống

Hệ thống là backend **Trợ lý Tư vấn Y tế & Thường thức Sức khỏe** theo kiến trúc RAG (Retrieval-Augmented Generation).
Người dùng đặt câu hỏi về triệu chứng hoặc cách dùng thuốc; hệ thống tìm đoạn văn liên quan trong tài liệu y khoa đã nạp
(hiện là tài liệu PDF về triệu chứng bệnh tại nhà thuốc) rồi dùng LLM sinh câu trả lời có cấu trúc kèm cảnh báo và nguồn tham khảo.

### 1.1. Bài toán giải quyết

| Vấn đề | Cách hệ thống xử lý | Bằng chứng |
|---|---|---|
| LLM có thể bịa thông tin y khoa, liều dùng | Chỉ trả lời dựa trên Context truy xuất; không có Context đạt ngưỡng thì từ chối | `answer_medical_query` trong `app/services/rag_engine.py` |
| Tình huống cấp cứu cần phản hồi tức thì | Lọc từ khóa cấp cứu trước khi gọi DB hoặc LLM | `check_input_guardrail` trong `app/services/rag_engine.py` |
| Kết quả cần cấu trúc để client hiển thị | Ép LLM trả JSON theo Pydantic schema | `MedicalResponseSchema` trong `app/schemas/medical.py` |
| Tài liệu PDF tiếng Việt có lỗi font và header/footer lặp | Làm sạch và chuẩn hóa trước khi băm | `clean_markdown_text` trong `app/services/ingestion.py` |

### 1.2. Phạm vi hiện tại

- **Đã có:** nạp tài liệu PDF, tìm kiếm ngữ nghĩa, sinh câu trả lời qua Gemini, API `POST /api/v1/chat`.
- **Chưa có:** tích hợp Zalo OA, xác thực người dùng, lưu lịch sử hội thoại, cache Redis.
- Chi tiết: [PROJECT_STATUS.md](./PROJECT_STATUS.md).

---

## 2. Tech stack

| Nhóm | Công nghệ | Ghi chú |
|---|---|---|
| Ngôn ngữ | Python | Chưa khai báo phiên bản tối thiểu trong repo |
| Web framework | FastAPI, Uvicorn, Starlette | Entry point `app/main.py` |
| Validation & cấu hình | Pydantic v2, pydantic-settings, python-dotenv | Cấu hình đọc từ `.env` |
| LLM & Embedding | `google-genai` (Gemini) | LLM sinh câu trả lời; `gemini-embedding-001` tạo vector 768 chiều |
| Chuỗi xử lý tài liệu | `pymupdf4llm`, `pypdf`, `pymupdf`, LangChain text splitters | PDF -> Markdown -> chunk |
| Cơ sở dữ liệu | PostgreSQL 16 + extension `pgvector` | Driver `asyncpg`, không dùng ORM |
| Cache | Redis 7 | Mới có hạ tầng và biến cấu hình, chưa dùng trong code |
| Retry | `tenacity` | Retry embedding và backoff |
| Test | `pytest`, `pytest-asyncio` | Xem [PROJECT_STATUS.md](./PROJECT_STATUS.md) mục kiểm thử |
| Hạ tầng cục bộ | Docker Compose | Chỉ khai báo service `db` và `redis` |

Danh sách đầy đủ phiên bản nằm trong `requirements.txt` (xem [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) về định dạng file này).

---

## 3. Cấu trúc thư mục chính

```text
medical_rag_zalo/
├── app/                        Lõi ứng dụng
│   ├── main.py                 Khởi tạo FastAPI, middleware, exception handlers, /health
│   ├── core/                   Cấu hình và exception dùng chung
│   │   ├── config.py           Lớp Settings (pydantic-settings), biến settings
│   │   ├── exceptions.py       AppBaseException, TransientServiceException, handler
│   │   ├── security.py         Trống - chưa có xác thực
│   │   └── logging.py          Trống - chưa có cấu hình logging tập trung
│   ├── db/
│   │   ├── pgvector_store.py   Connection pool, DDL, upsert, tìm kiếm vector
│   │   ├── redis_cache.py      Trống - chưa dùng
│   │   └── postgres.py         Trống
│   ├── models/chat_history.py  Trống - chưa có ORM model
│   ├── schemas/                Pydantic schema: chat_schema.py, medical.py (zalo.py trống)
│   └── services/
│       ├── embedding.py        Gọi Gemini Embedding, retry, pacing
│       ├── ingestion.py        PDF -> Markdown -> chunk 2 tầng + breadcrumb
│       └── rag_engine.py       Guardrail, retrieval, gọi LLM, fallback model
├── api/v1/
│   ├── router.py               Gom router v1 (api_router)
│   └── chat.py                 Endpoint POST /chat
├── scripts/ingest_pdfs.py      CLI nạp toàn bộ PDF trong data/raw_pdfs
├── tests/                      Test pytest (xem PROJECT_STATUS.md)
├── data/raw_pdfs/              Thư mục đầu vào cho script nạp tài liệu
├── docs/                       Tài liệu kỹ thuật (thư mục này); _audit/ là ghi chú trung gian
├── docker-compose.yml          Service PostgreSQL+pgvector và Redis
├── requirements.txt            Phụ thuộc Python
├── .env.example                Mẫu biến môi trường (không chứa giá trị thật)
├── list_models.py              Tiện ích liệt kê model Gemini khả dụng (xem TECHNICAL_DEBT.md)
└── Dockerfile                  Trống
```

---

## 4. Entry points

| Entry point | Vai trò | Khi nào dùng |
|---|---|---|
| `app/main.py` (biến `app`) | Ứng dụng FastAPI phục vụ HTTP | Chạy server |
| `scripts/ingest_pdfs.py` (`run_ingestion_pipeline`) | Nạp PDF vào pgvector | Chạy thủ công trước khi hỏi đáp, và khi tài liệu thay đổi |
| `list_models.py` | In danh sách model Gemini | Kiểm tra model khả dụng với API key |
| `docker-compose.yml` | Dựng PostgreSQL+pgvector và Redis | Trước khi chạy app và script |

> Lưu ý: `COMMANDS.md` ghi `python main.py`, nhưng repo **không có** `main.py` ở thư mục gốc. Lệnh đúng là `uvicorn app.main:app`.

---

## 5. Biến môi trường

Chỉ liệt kê tên biến. Giá trị thật không được ghi vào tài liệu hay commit; xem `.env.example` làm mẫu.

| Biến | Bắt buộc | Mặc định trong code | Mô tả |
|---|---|---|---|
| `GEMINI_API_KEY` | Có | Không có | API key Google AI Studio |
| `ZALO_APP_SECRET` | Có (hiện tại) | Không có | Dù Zalo chưa tích hợp, thiếu biến này app vẫn không khởi động |
| `ZALO_OA_ACCESS_TOKEN` | Có (hiện tại) | Không có | Tương tự, xem [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) |
| `POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Không | Có giá trị mặc định | Kết nối PostgreSQL |
| `REDIS_URL` | Không | `redis://localhost:6379/0` | Chưa được sử dụng trong code |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | Không | `gemini-embedding-001`, `768` | Model và số chiều vector |
| `EMBEDDING_BATCH_SIZE`, `EMBEDDING_MAX_CONCURRENCY`, `EMBEDDING_BATCH_INTERVAL_SECONDS` | Không | `64`, `1`, `12.0` | Điều tiết nạp tài liệu |
| `EMBEDDING_BATCH_MAX_RETRIES`, `EMBEDDING_QUERY_TIMEOUT`, `EMBEDDING_BATCH_TIMEOUT` | Không | `5`, `5.0`, `20.0` | Retry và timeout embedding |

---

## 6. Cài đặt và khởi chạy

Các lệnh dưới đây dành cho Windows PowerShell, đúng với môi trường đang dùng.

```powershell
# 1. Khởi động PostgreSQL+pgvector và Redis
docker-compose up -d

# 2. Tạo và kích hoạt môi trường ảo
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Cài phụ thuộc
pip install -r requirements.txt

# 4. Tạo file cấu hình từ mẫu, rồi điền giá trị thật
Copy-Item .env.example .env

# 5. Đặt file PDF vào data\raw_pdfs, rồi nạp vào pgvector
#    Script tự tạo extension, bảng medical_documents và index.
python scripts\ingest_pdfs.py

# 6. Chạy API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Sau khi chạy, kiểm tra:

- `GET http://localhost:8000/health` trả về trạng thái `healthy`.
- Tài liệu Swagger do FastAPI sinh tại `http://localhost:8000/docs`.
- Thứ tự bắt buộc: bước 5 (nạp dữ liệu) phải hoàn tất trước khi gọi `POST /api/v1/chat`, vì app không tự khởi tạo schema.

Chạy test:

```powershell
pytest
```

Test tích hợp `tests/test_phase5_vectorstore.py` cần PostgreSQL đang chạy và `GEMINI_API_KEY` hợp lệ.

---

## 7. Tài liệu liên quan

| Tài liệu | Nội dung |
|---|---|
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | Sơ đồ kiến trúc, phân tầng, hạ tầng |
| [DATA_FLOW.md](./DATA_FLOW.md) | Luồng nạp tài liệu, truy vấn RAG, xử lý lỗi |
| [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) | Bảng, index, kết nối |
| [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) | Endpoint, schema, mã lỗi |
| [PROJECT_STATUS.md](./PROJECT_STATUS.md) | Trạng thái module và đối chiếu audit |
| [TECHNICAL_DECISIONS.md](./TECHNICAL_DECISIONS.md) | Quyết định kiến trúc và hệ quả |
| [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) | Nợ kỹ thuật và đề xuất refactor |

`README.md` có sẵn trong repo nhưng chưa được dùng làm nguồn đối chiếu trong bộ tài liệu này; cần rà soát lại để tránh mâu thuẫn.
