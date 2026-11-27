# Medical RAG Zalo - Trạng thái dự án

> Trạng thái được xác định bằng cách đọc mã nguồn trực tiếp, kèm đường dẫn bằng chứng.
> Các phát hiện khác với báo cáo `_audit/` được ghi ở mục 5.
> Nợ kỹ thuật và đề xuất: [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md).

---

## 1. Phân loại trạng thái

| Ký hiệu | Ý nghĩa |
|---|---|
| **Đã hoàn thiện** | Có logic đầy đủ trong code, được gọi từ luồng chính |
| **Đang phát triển** | Có code nhưng thiếu test, cấu hình hoặc đang có lỗi đã biết |
| **Khung sườn (stub)** | File hoặc khai báo tồn tại nhưng không có logic (trống hoặc chỉ có comment) |
| **Chưa triển khai** | Không có file, không có code |
| **Chưa xác minh** | Không đủ bằng chứng trong repo để kết luận |

---

## 2. Module đã hoàn thiện

| Module | Chức năng | Bằng chứng |
|---|---|---|
| Endpoint `GET /health` | Trả trạng thái và tên dự án | `app/main.py` |
| Endpoint `POST /api/v1/chat` | Hỏi đáp RAG đầy đủ | `api/v1/chat.py`, `app/services/rag_engine.py` |
| Guardrail cấp cứu | Lọc từ khóa trước khi gọi DB và LLM | `check_input_guardrail` trong `rag_engine.py` |
| Retrieval pgvector | Cosine similarity, HNSW, lọc ngưỡng và category | `search_similar_vectors` trong `pgvector_store.py` |
| Sinh câu trả lời có cấu trúc | JSON schema theo `MedicalResponseSchema`, validate Pydantic | `_call_gemini` trong `rag_engine.py`, `app/schemas/medical.py` |
| Fallback model LLM | Chuyển model khi lỗi 429, 503, 504 hoặc lỗi kết nối | `generate_medical_answer` trong `rag_engine.py` |
| Embedding có retry và pacing | Phân biệt query (timeout ngắn) và batch nạp (backoff dài, pacing 12s) | `embedding.py` |
| Chunking hai tầng và breadcrumb | Tách theo `h1`-`h3`, sau đó 600/100 ký tự | `ingestion.py` |
| Làm sạch PDF | Chuẩn hóa `ƣ/Ư`, xóa header/footer lặp và số trang | `clean_markdown_text` trong `ingestion.py` |
| Upsert vector theo `chunk_key` | `ON CONFLICT DO UPDATE`, batch 200 dòng | `insert_chunks_with_embeddings` |
| Xử lý lỗi tập trung | Exception chuẩn và handler trả JSON thống nhất | `app/core/exceptions.py`, `app/main.py` |
| Đo thời gian xử lý | Header `X-Process-Time-Ms` | `app/main.py` |

---

## 3. Module đang phát triển

| Module | Hiện trạng | Thiếu gì | Bằng chứng |
|---|---|---|---|
| Nạp tài liệu (script) | Chạy được đầu-cuối, có kiểm chứng truy vấn cuối | Không có transaction giữa xóa và ghi; không có retry cấp file; không có test tự động cho pipeline đầy đủ | `scripts/ingest_pdfs.py` |
| Bộ test | Có test cho RAG engine, ingest và vector store | `tests/test_schemas.py` và `tests/test_zalo_webhook.py` trống. Test vector store cần DB và API key thật, không mock | `tests/` |
| Cấu hình môi trường | Có `.env.example` đầy đủ biến | Biến Zalo bắt buộc dù chưa dùng; không có validation giá trị mẫu | `app/core/config.py`, `.env.example` |
| Tài liệu vận hành | `COMMANDS.md` có lệnh | Lệnh `python main.py` không đúng (không có file này) | `COMMANDS.md` |
| Triển khai container | `docker-compose.yml` dựng DB và Redis | `Dockerfile` trống, app không được đóng gói | `Dockerfile` |

---

## 4. Khung sườn và chưa triển khai

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Tích hợp Zalo OA (webhook, service, schema) | Khung sườn: file trống, router chỉ có comment | `app/schemas/zalo.py`, `app/services/zalo_service.py`, `api/v1/router.py` |
| Xác thực và phân quyền | Chưa triển khai: `security.py` trống | `app/core/security.py` |
| Lưu lịch sử hội thoại | Khung sườn: model trống, chat stateless | `app/models/chat_history.py` |
| Cache Redis | Khung sườn: chỉ có `REDIS_URL` và container, không có code kết nối | `app/db/redis_cache.py`, `app/core/config.py` |
| Logging tập trung | Khung sườn: file trống, không có cấu hình | `app/core/logging.py` |
| Kết nối PostgreSQL qua SQLAlchemy | Khung sườn: file trống, không dùng | `app/db/postgres.py` |
| ORM models | Chưa triển khai | `app/models/` không có class |
| Migration schema | Chưa triển khai | Không có thư mục migration |
| Hybrid search (keyword + vector) | Chưa triển khai | Chỉ có vector search trong `search_similar_vectors` |
| Reranking | Chưa triển khai | Không có bước rerank sau truy vấn |
| Kiểm chứng trích dẫn | Chưa triển khai | `sources` do LLM sinh, không đối chiếu với metadata |
| Số trang trong trích dẫn | Chưa triển khai | Ingestion không ghi khóa `page` vào metadata |
| Dockerfile cho ứng dụng | Khung sườn: file trống | `Dockerfile` |

---

## 5. Đối chiếu với báo cáo `_audit/`

Một số điểm trong báo cáo trung gian không khớp với mã nguồn. Bộ tài liệu này dùng thông tin đã xác minh.

| # | Báo cáo | Kết luận sau khi đối chiếu |
|---|---|---|
| 1 | `03_database.md`: `chunk_key` là `TEXT (UNIQUE)` | Sai về ràng buộc. Cột nullable, tính duy nhất nằm ở `UNIQUE INDEX` (`pgvector_store.py` dòng 71-80) |
| 2 | `03_database.md`, `06_integrations.md`: pool đóng khi app tắt | Sai. `close_db_pool()` chỉ được gọi từ `scripts/ingest_pdfs.py` và test. `main.py` không có lifespan hay shutdown hook |
| 3 | `05_rag_pipeline.md`: `sources` được trích xuất từ metadata chunk | Sai. Trường `sources` do LLM sinh theo schema. Prompt không yêu cầu LLM dẫn đúng metadata, và không có bước kiểm tra |
| 4 | `05_rag_pipeline.md`: citation có số trang | Chưa đúng. Ingestion không ghi `page`, nhánh đó không chạy bao giờ |
| 5 | `01_project_structure.md`: "Containerization: Docker" | Chỉ đúng một phần. `docker-compose.yml` có service DB và Redis. `Dockerfile` trống |
| 6 | `01_project_structure.md`: `.env.example` và `tests/` | Đúng. Cả hai tồn tại |
| 7 | `02_api.md`: `urgency_flag` "ngưng chat" | Mô tả ý định trong comment của `medical.py`. Code chỉ trả cảnh báo và không chặn hội thoại |
| 8 | `05_rag_pipeline.md`: schema có 4 trường | Schema có 5 trường, thiếu `disclaimer` trong báo cáo |
| 9 | `06_integrations.md`: `scripts/ingest_pdfs.py` là worker nền | Không đúng. Đây là script CLI chạy thủ công, không có queue hay worker |
| 10 | `03_database.md`: "Redis cache chưa tích hợp" | Đúng. Đã kiểm tra: không có import Redis trong mã nguồn |

Các phát hiện khác ngoài báo cáo `_audit/`:

- `requirements.txt` được lưu ở định dạng UTF-16 (có khoảng trắng giữa các ký tự khi đọc dạng văn bản). Xem [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) mục D-17.
- `list_models.py` có ký tự `-` thừa ở cuối dòng cuối, nhiều khả năng gây lỗi cú pháp. Chưa chạy để xác minh.

---

## 6. Chưa thể xác minh

| Hạng mục | Lý do | Cách xác minh |
|---|---|---|
| Tên model Gemini trong `LLM_MODELS` (`gemini-3.8-flash`, `gemini-3.1-flash-lite`, `gemini-3.5-flash`) có khả dụng hay không | Cần gọi API thật, không có trong repo | Chạy `list_models.py` sau khi sửa lỗi cú pháp |
| Chất lượng câu trả lời và độ chính xác truy xuất | Không có bộ đánh giá (evaluation set) | Xây dựng bộ câu hỏi mẫu có đáp án |
| Kết quả chạy test | Chưa chạy `pytest` trong phạm vi này | Chạy `pytest` với PostgreSQL và API key hợp lệ |
| Số lượng file PDF và chunk đã nạp | Không có thông tin trong repo | Truy vấn `SELECT count(*)` trên `medical_documents` |
| Phiên bản Python tối thiểu | Không khai báo. Thư mục `__pycache__` có dấu hiệu nhiều phiên bản CPython | Ghi vào tài liệu vận hành sau khi kiểm tra |
| Nội dung `README.md` (301 dòng) | Không được dùng làm nguồn đối chiếu | Rà soát và đồng bộ với tài liệu này |
| Nội dung tài liệu PDF gốc trong `data/raw_pdfs` | Không đọc nội dung PDF trong phạm vi này | Kiểm tra thủ công |
