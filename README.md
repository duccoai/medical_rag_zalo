# 🏥 Medical RAG Bot — Trợ Lý Y Tế & Thường Thức Sức Khỏe Zalo OA

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.6+-e92063.svg)](https://docs.pydantic.dev/)
[![PostgreSQL pgvector](https://img.shields.io/badge/PostgreSQL-16%20%7C%20pgvector-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Redis](https://img.shields.io/badge/Redis-7-dc382d.svg?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ed.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📌 Giới Thiệu (Overview)

**Medical RAG Bot** là hệ thống Backend AI chuyên sâu hỗ trợ tra cứu dược thư, cẩm nang sức khỏe và giải đáp thường thức y tế tự động qua kênh **Zalo Official Account (Zalo OA)**. 

Dự án áp dụng kỹ thuật **Retrieval-Augmented Generation (RAG)** kết hợp cơ chế kiểm soát an toàn nghiêm ngặt **Medical Safety Guardrail** (xây dựng trên nền tảng **Pydantic v2**), giúp hạn chế tối đa hiện tượng ảo giác (Hallucination) của LLM. Mọi thông tin phản hồi đều được truy vấn có căn cứ từ kho tài liệu y khoa kiểm duyệt và luôn đi kèm khuyến cáo y tế chuyên môn.

---

## ✨ Tính Năng Nổi Bật (Key Features)

- **📚 Medical RAG Engine**: 
  - Khai thác kỹ thuật Semantic Search qua cơ sở dữ liệu vector (`pgvector`) với thuật toán HNSW / Cosine Similarity.
  - Phân đoạn tài liệu y khoa, trích xuất ngữ cảnh liên quan và tái định dạng câu trả lời kèm trích dẫn nguồn tài liệu (`sources`).
- **🛡️ Medical Safety Guardrail (Pydantic v2)**:
  - Định dạng cấu trúc đầu ra nghiêm ngặt qua schema chuẩn y khoa (`MedicalResponseSchema`).
  - Tự động nhận diện tình huống khẩn cấp (`urgency_flag` = `EMERGENCY`), lập tức gắn cảnh báo nguy hiểm và hướng dẫn gọi cấp cứu **115**.
  - Kiểm soát rủi ro, ngăn chặn LLM kê đơn thuốc chuyên khoa không an toàn.
- **⚡ Asynchronous Zalo OA Webhook (FastAPI)**:
  - Tiếp nhận Webhook từ Zalo OA và phản hồi HTTP `200 OK` tức thì (< 500ms) để không bị timeout.
  - Xử lý pipeline RAG và gửi tin nhắn phản hồi người dùng bất đồng bộ thông qua `BackgroundTasks`.
- **🚀 Caching Tăng Tốc (Redis)**:
  - Lưu bộ nhớ đệm cho các câu hỏi phổ biến, giảm chi phí gọi API OpenAI và tăng tốc độ phản hồi xuống dưới 50ms.
- **🐳 Hạ Tầng Tối Giản Với Docker Compose**:
  - Dễ dàng khởi chạy trọn gói CSDL PostgreSQL 16 tích hợp extension `pgvector` và Redis Cache chỉ với 1 câu lệnh.

---

## 🏗️ Kiến Trúc Hệ Thống (Architecture & Workflow)

### 1. Luồng Xử Lý Dữ Liệu (Processing Pipeline)

```
[Người dùng Zalo] ──(Gửi tin nhắn)──► [Zalo OA Platform]
                                              │ (Webhook POST)
                                              ▼
                                    ┌───────────────────┐
                                    │ FastAPI Webhook   │ ──► Phản hồi 200 OK ngay (<500ms)
                                    │ (api/v1/zalo)     │
                                    └─────────┬─────────┘
                                              │ (BackgroundTasks)
                                              ▼
                                    ┌───────────────────┐
                                    │ Redis Cache Check │ ──(Hit)──► Trả về kết quả ngay
                                    └─────────┬─────────┘
                                              │ (Miss)
                                              ▼
                                    ┌───────────────────┐
                                    │ pgvector Search   │ ◄── [Data Ingestion / Embeddings]
                                    │ (Cosine Distance) │
                                    └─────────┬─────────┘
                                              │ Top-K Chunks
                                              ▼
                                    ┌───────────────────┐
                                    │ LLM (OpenAI)      │
                                    └─────────┬─────────┘
                                              │
                                              ▼
                                    ┌───────────────────┐
                                    │ Pydantic Guardrail│ ──► Kiểm tra an toàn, urgency_flag,
                                    │ (Medical Schema)  │     gắn disclaimer & sources
                                    └─────────┬─────────┘
                                              │
                                              ▼
[Người dùng Zalo] ◄──(Gửi tin nhắn)── [Zalo OpenAPI Client]
```

### 2. Cấu Trúc Thư Mục Chuẩn (Project Structure)

```text
medical_rag_zalo/
├── api/                           # Tầng Routing & Giao tiếp bên ngoài
│   ├── __init__.py
│   └── v1/
│       ├── __init__.py
│       ├── router.py              # Gom nhóm các sub-routers API v1
│       └── zalo_webhook.py        # Endpoint tiếp nhận Webhook Zalo OA
├── app/                           # Lõi ứng dụng chính (Core Application)
│   ├── __init__.py
│   ├── main.py                    # Khởi tạo FastAPI App, middleware, lifecycle
│   ├── cache/                     # Tầng Caching
│   │   ├── __init__.py
│   │   └── redis_cache.py         # Kết nối và thao tác với Redis
│   ├── core/                      # Cấu hình hệ thống & Tiện ích lõi
│   │   ├── __init__.py
│   │   ├── config.py              # Pydantic BaseSettings đọc biến môi trường (.env)
│   │   ├── logging.py             # Cấu hình Logging tập trung
│   │   └── security.py            # Xác thực chữ ký Webhook (MAC/Secret)
│   ├── schemas/                   # Pydantic Schemas & DTO
│   │   ├── __init__.py
│   │   ├── chat_schema.py         # ChatRequest, ChatResponse
│   │   └── medical_schema.py      # MedicalResponseSchema, UrgencyEnum, Guardrails
│   ├── services/                  # Business Logic & Dịch vụ AI
│   │   ├── __init__.py
│   │   ├── ingestion.py           # Đọc, tiền xử lý và chia nhỏ (chunking) tài liệu
│   │   ├── rag_engine.py          # RAG Service: ghép context, prompt LLM & parse output
│   │   └── vector_store.py        # Service giao tiếp tìm kiếm vector
│   └── vectorstore/               # Database Driver / Vector Store Layer
│       ├── __init__.py
│       └── pgvector_store.py      # Kết nối PostgreSQL & truy vấn extension pgvector
├── data/                          # Kho dữ liệu y khoa
│   └── raw_pdfs/                  # Tài liệu PDF y tế, dược thư phục vụ Ingestion
├── tests/                         # Bộ kiểm thử tự động (Pytest)
│   ├── __init__.py
│   ├── test_rag_engine.py         # Test pipeline xử lý RAG
│   ├── test_schemas.py            # Test validation dữ liệu và Safety Guardrail
│   └── test_zalo_webhook.py       # Test endpoint tiếp nhận Webhook Zalo
├── .env                           # File cấu hình môi trường cục bộ (không commit)
├── .env.example                   # File mẫu cấu hình biến môi trường
├── .clinerules                    # Quy chuẩn vận hành cho AI Agent
├── docker-compose.yml             # Cấu hình container PostgreSQL (pgvector) & Redis
├── requirements.txt               # Danh sách thư viện Python phụ thuộc
├── setup.py                       # Script khởi tạo khung cấu trúc thư mục
├── COMMANDS.md                    # Bản tra cứu nhanh các lệnh terminal thường dùng
└── README.md                      # Tài liệu hướng dẫn dự án
```

---

## 🛠️ Công Nghệ Sử Dụng (Tech Stack)

| Hạng mục | Công nghệ | Chi tiết |
| :--- | :--- | :--- |
| **Ngôn ngữ** | Python 3.10+ | Lập trình hướng cấu trúc, Async/Await chuẩn |
| **Framework Web** | FastAPI | Framework bất đồng bộ hiệu năng cao, tích hợp OpenAPI/Swagger |
| **Validation & Settings** | Pydantic v2 & Pydantic-Settings | Validation dữ liệu, Guardrail an toàn, Type hints |
| **LLM Provider** | OpenAI API | Xử lý ngôn ngữ tự nhiên và tạo embedding ngữ nghĩa |
| **Vector Database** | PostgreSQL 16 + pgvector | Lưu trữ và truy vấn tương đồng vector (HNSW/Cosine) |
| **Caching Layer** | Redis 7 | Caching câu trả lời, lưu phiên hội thoại |
| **Kiểm thử** | Pytest & pytest-asyncio | Unit testing và Integration testing |
| **Container hóa** | Docker & Docker Compose | Đóng gói môi trường cơ sở dữ liệu và cache |

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Cục Bộ (Local Setup)

### 1. Yêu Cầu Tiền Đề (Prerequisites)
- Đã cài đặt **Python 3.10** trở lên.
- Đã cài đặt **Docker** và **Docker Compose**.
- Đã có tài khoản và **OpenAI API Key**.
- (Tùy chọn) Tài khoản nhà phát triển **Zalo for Developers** và Official Account.

---

### 2. Khởi Tạo Môi Trường Ảo (Virtual Environment)

Clone dự án và di chuyển vào thư mục gốc:
```bash
git clone https://github.com/your-username/medical-rag-zalo.git
cd medical-rag-zalo
```

Khởi tạo và kích hoạt môi trường ảo:

- **Trên Windows (CMD / PowerShell):**
  ```powershell
  # Khởi tạo venv
  python -m venv venv

  # Kích hoạt trên PowerShell
  .\venv\Scripts\Activate.ps1
  # Hoặc kích hoạt trên CMD
  venv\Scripts\activate.bat
  ```

- **Trên Linux / macOS:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

Cài đặt các gói thư viện phụ thuộc:
```bash
pip install -r requirements.txt
```

---

### 3. Cấu Hình Biến Môi Trường (`.env`)

Tạo file `.env` tại thư mục gốc của dự án (tham khảo mẫu dưới đây hoặc từ `.env.example`):

```ini
# --- Thông Tin Ứng Dụng ---
PROJECT_NAME="Medical RAG Bot"
VERSION="1.0.0"
ENVIRONMENT="development"

# --- Khóa API Dịch Vụ AI & Zalo ---
OPENAI_API_KEY="sk-proj-your-openai-api-key"
ZALO_APP_SECRET="your-zalo-app-secret"
ZALO_OA_ACCESS_TOKEN="your-zalo-oa-access-token"

# --- Cấu Hình PostgreSQL (pgvector) ---
POSTGRES_SERVER="localhost"
POSTGRES_PORT=5432
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="medicaloai11911"
POSTGRES_DB="medical_db"

# --- Cấu Hình Redis Cache ---
REDIS_URL="redis://localhost:6379/0"
```

> **Lưu ý**: Các thông số `POSTGRES_*` và `REDIS_URL` trên đã được cấu hình đồng bộ với file `docker-compose.yml` của dự án.

---

### 4. Khởi Động Hạ Tầng (PostgreSQL & Redis) Bằng Docker

Chạy lệnh Docker Compose để khởi chạy dịch vụ CSDL PostgreSQL và Redis:

```bash
docker-compose up -d
```

Kiểm tra trạng thái các container đang hoạt động:
```bash
docker-compose ps
```

Container `medical-rag-pos` (PostgreSQL 16) và `medical-rag-redis` (Redis 7) sẽ sẵn sàng lắng nghe ở các cổng `5432` và `6379`.

---

### 5. Khởi Chạy Ứng Dụng FastAPI

Khởi động server phát triển bằng Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Sau khi server khởi động thành công, truy cập tài liệu Swagger UI để kiểm tra trực quan các API:
- **Swagger UI Interactive Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Redoc Alternative Docs**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Chạy Kiểm Thử Tự Động (Testing)

Dự án sử dụng **Pytest** để kiểm thử tự động toàn diện:

```bash
# Chạy toàn bộ các bài test
pytest -v

# Chạy riêng kiểm thử Schemas và Medical Guardrail
pytest tests/test_schemas.py -v

# Chạy kiểm thử RAG Engine
pytest tests/test_rag_engine.py -v

# Chạy kiểm thử Webhook tiếp nhận Zalo
pytest tests/test_zalo_webhook.py -v
```

---

## 🛡️ Cơ Chế An Toàn Y Tế (Medical Safety & Guardrails)

Hệ thống tuân thủ nghiêm ngặt các nguyên tắc bảo vệ sức khỏe người dùng:

1. **Phân Loại Tình Huống Cấp Cứu (`Urgency Assessment`)**:
   - Tự động quét và phát hiện các dấu hiệu cấp cứu nguy kịch (khó thở dữ dội, đau ngực lan tỏa, bất tỉnh, xuất huyết cấp tính...).
   - Nếu phát hiện dấu hiệu khẩn cấp, hệ thống lập tức ưu tiên cảnh báo người dùng liên hệ ngay tổng đài cấp cứu **115** hoặc tới cơ sở y tế gần nhất, đồng thời ngắt pipeline kê đơn/tư vấn sâu.
2. **Loại Bỏ Ảo Giác (Grounded Retrieval)**:
   - Câu trả lời bắt buộc chỉ được tổng hợp dựa trên ngữ cảnh trích xuất từ dữ liệu nguồn y khoa đã kiểm duyệt. Nếu không đủ tài liệu, hệ thống thông báo rõ ràng về giới hạn dữ liệu thay vì tự suy diễn.
3. **Minh Bạch Nguồn Gốc (Citation & Sources)**:
   - Luôn kèm theo danh sách tài liệu tham khảo (`sources`) trong cấu trúc phản hồi.
4. **Miễn Trừ Trách Nhiệm Y Tế Bắt Buộc (Mandatory Disclaimer)**:
   - Mọi tư vấn từ bot đều được gắn kèm tuyên bố cảnh báo tiêu chuẩn: *"Thông tin chỉ mang tính tham khảo thường thức, không thay thế cho chẩn đoán hay phác đồ điều trị trực tiếp từ bác sĩ chuyên môn."*

---

## 🤝 Đóng Góp & Phát Triển (Contributing)

1. Fork dự án về tài khoản cá nhân.
2. Tạo nhánh tính năng mới (`git checkout -b feature/AmazingFeature`).
3. Commit các thay đổi (`git commit -m 'Add some AmazingFeature'`).
4. Push nhánh lên remote (`git push origin feature/AmazingFeature`).
5. Tạo một Pull Request mô tả chi tiết nội dung đã hoàn thành.

---

## 📄 Bản Quyền & Tuyên Bố Miễn Trừ Trách Nhiệm (Disclaimer)

- **Giấy phép**: Phân phối theo giấy phép mã nguồn mở **MIT License**.
- **Tuyên bố y tế quan trọng**: Ứng dụng này là một giải pháp công nghệ hỗ trợ tìm kiếm tài liệu thông tin y học. Ứng dụng **không phải là thiết bị y tế** và **không cung cấp dịch vụ khám chữa bệnh**. Người dùng tuyệt đối không tự ý áp dụng các thông tin để tự điều trị hoặc thay đổi chỉ định của nhân viên y tế có chuyên môn.
