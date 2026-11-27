Báo cáo kết quả Codebase Audit cho dự án **Medical RAG Zalo**:

---

### 1. Cấu trúc thư mục thực tế & Vai trò từng thành phần
```text
medical_rag_zalo/
│
├── api/                     # Định nghĩa các API endpoints (được gom nhóm theo version)
│   └── v1/                  # API Version 1
│       ├── chat.py          # Endpoint xử lý chat, tin nhắn, RAG pipeline cho Zalo/Client
│       └── router.py        # File tổng hợp router của v1
│
├── app/                     # Core application logic
│   ├── core/                # Cấu hình cốt lõi (config.py, exceptions.py, security, logging)
│   ├── db/                  # Tương tác cơ sở dữ liệu & Vector store (pgvector_store.py)
│   ├── models/              # ORM models (nếu có, ví dụ chat_history.py)
│   ├── schemas/             # Pydantic schemas (chat_schema.py, medical.py...) để validate request/response
│   ├── services/            # Business logic chính (rag_engine.py, ingestion.py, embedding.py...)
│   └── main.py              # Entry point khởi tạo ứng dụng FastAPI
│
├── tests/                   # Bộ test tự động bằng pytest (test_rag_engine.py, test_ingest.py, ...)
├── .env.example             # File mẫu cấu hình biến môi trường
├── docker-compose.yml       # Cấu hình container cho PostgreSQL (pgvector) và Redis
├── requirements.txt         # Danh sách các thư viện Python phụ thuộc
└── README.md                # Tài liệu hướng dẫn sử dụng dự án
```

---

### 2. Ngôn ngữ, Framework, Thư viện & Công nghệ
* **Ngôn ngữ:** Python (3.12+)
* **Web Framework:** FastAPI, Uvicorn, Starlette
* **AI & LLM / RAG Stack:** 
  * `google-genai`, `openai` (tích hợp các mô hình ngôn ngữ lớn như Google Gemini)
  * LangChain ecosystem (`langchain-core`, `langchain-text-splitters`)
  * Xử lý tài liệu PDF: `pypdf`, `pymupdf` (PyMuPDF)
* **Database & Caching:** 
  * PostgreSQL với extension `pgvector` (`pgvector` python client, `asyncpg`) cho Vector Search / Embedding Storage
  * Redis (`redis` client) cho caching
* **Validation & Configuration:** `pydantic`, `pydantic-settings`, `python-dotenv`
* **Testing:** `pytest`, `pytest-asyncio`
* **Containerization:** Docker, Docker Compose (PostgreSQL + pgvector, Redis)

---

### 3. Entry Point & Cách khởi chạy ứng dụng
* **Entry Point chính:** `app/main.py` (khởi tạo ứng dụng FastAPI với `app = FastAPI(...)`).
* **Cách khởi chạy ứng dụng (Development / Production):**
  1. Khởi động các dịch vụ cơ sở dữ liệu (PostgreSQL/pgvector & Redis) qua Docker:
     ```bash
     docker-compose up -d
     ```
  2. Kích hoạt môi trường ảo (Virtual Environment):
     * Trên Windows: `venv\Scripts\activate`
     * Trên Linux/macOS: `source venv/bin/activate`
  3. Cài đặt các thư viện (nếu cần):
     ```bash
     pip install -r requirements.txt
     ```
  4. Chạy ứng dụng FastAPI bằng `uvicorn`:
     ```bash
     uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
     ```