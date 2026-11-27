Dưới đây là bản phân tích chi tiết và toàn diện về **Tầng Dữ Liệu (Data Layer)** của dự án **Medical RAG Zalo**, dựa trên phạm vi và các yêu cầu đề ra (không thực thi code, không kết nối/thay đổi database, không chạy migration, và tuân thủ tuyệt đối quy tắc không suy diễn quan hệ).

---

### I. Tổng quan kiến trúc tầng dữ liệu

Tầng dữ liệu của project được thiết kế theo hướng **Direct Database Driver / Raw SQL kết hợp AsyncIO (`asyncpg`)** thay vì sử dụng các ORM cồng kềnh như SQLAlchemy ORM hay Tortoise ORM. Riêng đối với ORM models, hệ thống hiện tại **chưa triển khai thực tế** (các file `app/models/` đang để trống). 

Hạ tầng lưu trữ bao gồm 2 thành phần chính chạy trên Docker (`docker-compose.yml`):
1. **PostgreSQL 16 + Extension `pgvector`**: Đảm nhiệm việc lưu trữ văn bản y khoa phân đoạn (chunks), metadata dưới dạng JSONB và vector embedding (768 chiều).
2. **Redis 7 (`redis:7-alpine`)**: Được cấu hình để làm lớp cache (hiện đang chuẩn bị hạ tầng, sử dụng `redis-server --appendonly yes`).

---

### II. Liệt kê Database Model & Entity

Do hệ thống không sử dụng ORM models (thư mục `app/models/` chỉ chứa file trống `chat_history.py`), cấu trúc bảng được định nghĩa trực tiếp bằng câu lệnh DDL (`CREATE TABLE`) trong tầng khởi tạo vector store (`app/db/pgvector_store.py`).

#### 1. Entity: `medical_documents` (Bảng lưu trữ tài liệu y khoa & Vector embedding)
* **Khóa chính (Primary Key):**
  * `id`: Kiểu dữ liệu `BIGSERIAL` (tự tăng), là khóa chính định danh từng bản ghi chunk trong bảng.
* **Các Field và Kiểu dữ liệu:**
  * `id`: `BIGSERIAL` (PK)
  * `content`: `TEXT` (NOT NULL) — Chứa nội dung văn bản đoạn (chunk) trích xuất từ tài liệu PDF y tế.
  * `metadata`: `JSONB` (NOT NULL) — Chứa metadata bổ trợ như nguồn tài liệu (`source`), số trang (`page`), danh mục (`category`),...
  * `embedding`: `vector(768)` (NOT NULL) — Kiểu dữ liệu vector từ extension `pgvector`, lưu trữ mảng float 768 chiều (tương thích mô hình `gemini-embedding-001`).
  * `chunk_key`: `TEXT` (UNIQUE) — Khóa định danh duy nhất cho từng chunk (`<source>:<chunk_index>`), dùng cho việc upsert chống trùng lặp dữ liệu khi chạy lại script nạp tài liệu.

#### 2. Các Entity khác (Chat History, Zalo Session)
* **Thực tế khai báo trong ORM (`app/models/`):** **Không có**. File `app/models/chat_history.py` đang có kích thước `0 bytes` (trống).
* **Trạng thái lưu trữ hội thoại:** Theo tài liệu kỹ thuật và mã nguồn endpoint hiện tại (`api/v1/chat.py`), tính năng chat đang hoạt động ở chế độ **Stateless** (chưa lưu lịch sử hội thoại của `user_id` vào CSDL sau mỗi lượt hỏi đáp, mặc dù model đã được dự trù tên file).

---

### III. Xác định quan hệ giữa các bảng

* **Kết quả phân tích:** **Không có quan hệ (Foreign Key / Relations) nào được thiết lập** trong tầng cơ sở dữ liệu hiện tại.
* **Lý do:** Hệ thống chỉ có duy nhất 1 bảng dữ liệu độc lập là `medical_documents`. Không có bảng `users`, bảng `chat_sessions`, hay bảng `chat_history` nào có quan hệ khóa ngoại (`REFERENCES`) trỏ tới nhau.
* *Lưu ý tuân thủ:* Tuyệt đối không suy diễn quan hệ giữa các bảng vì thực tế CSDL chỉ tồn tại duy nhất một bảng `medical_documents`.

---

### IV. Phân tích PostgreSQL, pgvector và Redis

#### 1. PostgreSQL & Extension `pgvector` (`app/db/pgvector_store.py`)
* **Extension:** Sử dụng `CREATE EXTENSION IF NOT EXISTS vector;` để kích hoạt tính năng tính toán vector trực tiếp trong PostgreSQL.
* **Định dạng Vector:** 
  * Số chiều (dimensions): `768` (cấu hình qua `settings.EMBEDDING_DIMENSIONS`), phù hợp với mô hình embedding của Google Gemini (`gemini-embedding-001`).
  * Thư viện Python trung gian: `asyncpg` kết hợp với `pgvector.asyncpg.register_vector` để tự động hóa việc serialize/deserialize kiểu dữ liệu `vector` giữa Python `list[float]` và PostgreSQL.
* **Index & Tối ưu hóa hiệu năng truy vấn:**
  * **Unique Index (`idx_medical_documents_chunk_key`):** Đảm bảo không bị trùng lặp dữ liệu chunk khi chạy script ingest lặp lại (`ON CONFLICT (chunk_key) DO UPDATE`).
  * **HNSW Index (`idx_medical_documents_embedding_hnsw`):** 
    * Sử dụng thuật toán **HNSW (Hierarchical Navigable Small World)** với toán tử khoảng cách **Cosine Distance** (`vector_cosine_ops`).
    * Tham số cấu trúc: `WITH (m = 16, ef_construction = 64)`.
    * Khi truy vấn (`search_similar_vectors`), hệ thống sử dụng lệnh `SET LOCAL hnsw.ef_search = 64;` bên trong transaction để cân bằng tối ưu giữa tốc độ tìm kiếm và độ chính xác (recall).
  * **Bộ lọc kết hợp (Hybrid/Metadata Filtering):** Hỗ trợ lọc nâng cao dựa trên trường JSONB `metadata->>'category'` kết hợp với điểm ngưỡng tương đồng `similarity >= 0.5`.

#### 2. Redis (`docker-compose.yml` & `app/core/config.py`)
* **Cấu hình:** Khởi chạy Redis 7 qua Docker (`image: redis:7-alpine`, port `6379`), bật chế độ lưu trữ bền vững `appendonly yes`.
* **Mức độ sử dụng trong code hiện tại:** Biến cấu hình `REDIS_URL` đã được khai báo trong `Settings` (`redis://localhost:6379/0`), tuy nhiên tầng code kết nối trực tiếp (`app/db/redis_cache.py`) hiện đang **trống (0 bytes)**, nghĩa là tầng cache Redis chưa được tích hợp vào luồng chạy chính của ứng dụng tại thời điểm hiện tại.

---

### V. Quản lý Connection, Session và Transaction

#### 1. Quản lý Kết nối (Connection Pool)
* Dự án sử dụng **Asyncpg Connection Pool** (`asyncpg.Pool`) thay vì SQLAlchemy Session.
* **Cấu hình Pool (`get_db_pool`):**
  * `min_size = 2`: Duy trì sẵn ít nhất 2 kết nối ngầm.
  * `max_size = 10`: Giới hạn tối đa 10 kết nối đồng thời nhằm bảo vệ tài nguyên Database Server.
  * `init = init_conn`: Tự động gọi hàm `register_vector(conn)` cho mọi kết nối mới mở trong pool, giúp kết nối sẵn sàng hiểu kiểu dữ liệu `vector`.
* **Vòng đời kết nối:** Pool được khởi tạo lazily khi có request gọi database đầu tiên và được đóng lại thông qua hàm `close_db_pool()` khi ứng dụng tắt hoặc kết thúc test.

#### 2. Quản lý Transaction
* **Chế độ tự động commit (Auto-commit):** Các thao tác ghi đơn lẻ hoặc `executemany` trong `insert_chunks_with_embeddings` sử dụng kết nối lấy từ pool theo dạng `async with pool.acquire() as conn:` và chạy trực tiếp lệnh SQL (mặc định commit theo từng lệnh/lô).
* **Transaction tường minh (Explicit Transaction):** Được áp dụng rõ ràng tại luồng truy vấn online (`search_similar_vectors`):
  ```python
  async with pool.acquire() as conn:
      async with conn.transaction():
          # Đảm bảo lệnh SET LOCAL chỉ có hiệu lực cục bộ trong phạm vi transaction này
          await conn.execute("SET LOCAL hnsw.ef_search = 64;")
          rows = await conn.fetch(sql, *params)
  ```
  Việc sử dụng `async with conn.transaction()` giúp thiết lập `SET LOCAL` an toàn, không ảnh hưởng đến các session/transaction khác dùng chung connection trong pool.

---

### VI. Phân biệt Database Schema thực tế với khai báo ORM

| Thành phần | Khai báo trong ORM (`app/models/`) | Schema thực tế trong Database (Code DDL / Migration) |
| :--- | :--- | :--- |
| **Model `chat_history`** | Khai báo tên file `chat_history.py` nhưng **nội dung hoàn toàn trống (0 bytes)**. Không có class ORM nào được định nghĩa. | **Không tồn tại** trong cơ sở dữ liệu thực tế (bảng `chat_history` chưa từng được tạo trong CSDL). |
| **Model `medical_documents`** | **Không có** class ORM nào trong thư mục `app/models/`. | **Được định nghĩa trực tiếp bằng DDL** tại `app/db/pgvector_store.py` (`init_vector_db`), gồm các cột: `id` (BIGSERIAL), `content` (TEXT), `metadata` (JSONB), `embedding` (vector 768), `chunk_key` (TEXT UNIQUE). |
| **Migration Files** | **Không có** thư mục quản lý migration (như Alembic `alembic/versions/`). | **Không sử dụng Migration Tool**. Schema được khởi tạo và cập nhật tự động bằng code Python (`init_vector_db` chạy câu lệnh `CREATE TABLE IF NOT EXISTS` và `ALTER TABLE ADD COLUMN IF NOT EXISTS`). |

---
*Báo cáo được hoàn thành tuân thủ nghiêm ngặt các tiêu chí: không thực thi code, không kết nối/thay đổi database, không chạy migration và không suy diễn quan hệ.*