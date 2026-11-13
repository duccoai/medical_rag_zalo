# 🏥 Medical RAG Bot — Trợ Lý Y Tế & Thường Thức Sức Khỏe Zalo OA

[![Python 3.10+]([suspicious link removed])]([suspicious link removed])
[![FastAPI]([suspicious link removed])]([suspicious link removed])
[![Pydantic v2]([suspicious link removed])]([suspicious link removed])
[![PostgreSQL pgvector]([suspicious link removed])]([suspicious link removed])
[![Docker]([suspicious link removed])]([suspicious link removed])

---

## 📌 Giới Thiệu (Overview)

**Medical RAG Bot** là hệ thống Backend AI chuyên sâu hỗ trợ tư vấn thông tin dược thư và thường thức y tế tự động qua kênh **Zalo Official Account (Zalo OA)**. 

Dự án áp dụng kỹ thuật **Retrieval-Augmented Generation (RAG)** kết hợp với **Medical Safety Guardrail** (Pydantic v2) giúp loại bỏ hoàn toàn hiện tượng ảo giác (Hallucination) của LLM, đảm bảo mọi phản hồi đều trích dẫn chính xác từ nguồn Dược thư Quốc gia và Hướng dẫn Y tế đã qua kiểm duyệt.

---

## ✨ Tính Năng Nổi Bật (Key Features)

- **📚 Medical RAG Engine**: Trích xuất và tra cứu dữ liệu y khoa chính xác cao với kỹ thuật Semantic Search qua toán tử HNSW Cosine Similarity (`pgvector`).
- **🛡️ Safety Guardrail (Pydantic v2)**: Đóng gói phản hồi LLM vào `MedicalResponseSchema` JSON chuẩn xác; tự động phát hiện tình trạng cấp cứu khẩn cấp (`urgency_flag`) và gắn cảnh báo y tế bắt buộc.
- **⚡ Async FastAPI Backend**: Xử lý Webhook Zalo bất đồng bộ với phản hồi HTTP 200 nhanh chóng (< 500ms) qua `BackgroundTasks`.
- **🚀 Redis Semantic Caching**: Cache các câu hỏi phổ biến giúp giảm 70% chi phí gọi API và giảm thời gian phản hồi xuống dưới 50ms.
- **🐳 1-Click Docker Deployment**: Đóng gói hoàn chỉnh ứng dụng, CSDL PostgreSQL (pgvector) và Redis Caching bằng Docker Compose.

---

## 🏗️ Kiến Trúc Hệ Thống (Clean Layered Architecture)

```text
medical-rag-zalo/
├── app/
│   ├── api/                  # FastAPI Routers & Zalo Webhook Handlers
│   │   ├── v1/
│   │   │   ├── chat.py       # API Endpoint RAG Chat
│   │   │   └── zalo.py       # Zalo OA Webhook Receiver
│   │   └── deps.py           # Dependency Injections
│   ├── core/                 # App Configurations & Security
│   │   ├── config.py         # Pydantic Settings & Env Parser
│   │   └── security.py       # Webhook Verification & JWT
│   ├── schemas/              # Pydantic Schemas & Medical Guardrails
│   │   ├── chat.py           # Request / Response Models
│   │   └── medical.py        # MedicalResponseSchema & Validation
│   ├── services/             # Core Business Logic & AI Services
│   │   ├── embedding.py      # Embedding Generation Service
│   │   ├── ingestion.py      # Document Cleaning & Chunking
│   │   ├── rag_engine.py     # Context Building & LLM Prompting
│   │   ├── vector_store.py   # PostgreSQL pgvector Service
│   │   └── zalo_client.py    # Zalo OpenAPI Messenger Service
│   └── main.py               # FastAPI App Initialization
├── data/                     # Medical Documents (PDFs / Text)
├── tests/                    # Pytest Automation Suite
├── .env.example              # Sample Environment Variables
├── .clinerules               # AI Coding Agent Guidelines
├── docker-compose.yml        # Docker Multi-container Orchestration
├── Dockerfile                # Multi-stage Python Build
├── requirements.txt          # Production Dependencies
└── README.md                 # Project Documentation

🚀 Hướng Dẫn Cài Đặt & Chạy Cục Bộ (Local Setup)
1. Yêu Cầu Tiền Đề
Python 3.10 trở lên
PostgreSQL 15+ (Đã cài extension pgvector)
Redis Server (Tùy chọn cho Caching)
2. Khởi Tạo Môi Trường Virtualenv
# Clone project
git clone [suspicious link removed]
cd medical-rag-zalo

# Khởi tạo và kích hoạt virtualenv
python -m venv venv
source venv/bin/activate  # Trên Windows: venv\Scripts\activate

# Cài đặt thư viện dependencies
pip install -r requirements.txt
3. Cấu Hình Biến Môi Trường (.env)
Tạo file .env từ file mẫu .env.example:
PROJECT_NAME="Medical RAG Bot"
ENVIRONMENT="development"

# API Keys
OPENAI_API_KEY="sk-proj-your-openai-key"
ZALO_APP_SECRET="your-zalo-app-secret"
ZALO_ACCESS_TOKEN="your-zalo-access-token"

# Database Configuration
POSTGRES_SERVER="localhost"
POSTGRES_PORT=5432
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="postgres_password"
POSTGRES_DB="medical_rag_db"

# Redis Configuration
REDIS_URL="redis://localhost:6379/0"
4. Chạy Server FastAPI (Development Mode)
uvicorn app.main:app --reload --port 8000
TRUY CẬP SWAGGER UI DOCS: http://localhost:8000/docs
🐳 Triển Khai Bằng Docker Compose (Production Staging)
Chỉ với 1 câu lệnh duy nhất để khởi chạy toàn bộ 3 dịch vụ (FastAPI Backend, PostgreSQL + pgvector, Redis):
docker-compose up --build -d
Kiểm tra trạng thái các Containers:
docker-compose ps
🧪 Chạy Kiểm Thử Tự Động (Testing)
Dự án tích hợp bộ kiểm thử tự động với Pytest bao gồm Unit Test cho Schema Guardrail và Integration Test cho API Endpoints:
# Chạy toàn bộ Test Cases
pytest -v

# Chạy riêng kiểm thử Pydantic Medical Guardrail
pytest tests/test_medical_guardrail.py -v
📄 Bản Quyền & Cảnh Báo (Disclaimer)
Giấy phép: MIT License.
Cảnh báo chuyên ngành: Hệ thống chỉ đóng vai trò hỗ trợ cung cấp thông tin thường thức y tế. Mọi quyết định điều trị và chẩn đoán y khoa phải tuân theo chỉ định trực tiếp từ bác sĩ chuyên khoa.
