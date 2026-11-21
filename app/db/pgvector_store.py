import json
import asyncpg
from pgvector.asyncpg import register_vector
from app.core.config import settings
from app.core.exceptions import AppBaseException

_pool: asyncpg.Pool | None = None


def _get_asyncpg_dsn() -> str:
    """Chuyển đổi URL chuẩn SQLAlchemy sang DSN thuần cho asyncpg"""
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def get_db_pool() -> asyncpg.Pool:
    """Khởi tạo hoặc tái sử dụng Connection Pool đã đăng ký kiểu dữ liệu vector"""
    global _pool
    if _pool is None:
        async def init_conn(conn: asyncpg.Connection) -> None:
            await register_vector(conn)

        _pool = await asyncpg.create_pool(
            _get_asyncpg_dsn(),
            min_size=2,
            max_size=10,
            init=init_conn,
        )
    return _pool


async def close_db_pool() -> None:
    """Đóng Connection Pool khi tắt server hoặc kết thúc test"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def init_vector_db() -> None:
    """Khởi tạo extension vector, bảng medical_documents và chỉ mục HNSW"""
    raw_conn = await asyncpg.connect(_get_asyncpg_dsn())
    try:
        await raw_conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    finally:
        await raw_conn.close()

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS medical_documents (
                id BIGSERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                metadata JSONB NOT NULL,
                embedding vector({settings.EMBEDDING_DIMENSIONS}) NOT NULL
            );
            """
        )

        # chunk_key = "<source>:<chunk_index>" giúp chạy lại script upsert đúng bản ghi, không nhân đôi dữ liệu
        await conn.execute(
            "ALTER TABLE medical_documents ADD COLUMN IF NOT EXISTS chunk_key TEXT;"
        )
        await conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_medical_documents_chunk_key
            ON medical_documents (chunk_key);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_medical_documents_embedding_hnsw
            ON medical_documents
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
            """
        )


async def insert_chunks_with_embeddings(
    chunks: list[dict],
    embeddings: list[list[float]],
    db_batch_size: int = 200,
) -> int:
    """Lưu danh sách chunks kèm vector đã tính sẵn vào PostgreSQL bằng executemany"""
    if not chunks:
        return 0
    if len(chunks) != len(embeddings):
        raise AppBaseException(
            message=f"Số lượng chunks ({len(chunks)}) không khớp số lượng vectors ({len(embeddings)}).",
            status_code=400,
        )

    pool = await get_db_pool()
    inserted_count = 0

    for i in range(0, len(chunks), db_batch_size):
        chunk_slice = chunks[i : i + db_batch_size]
        emb_slice = embeddings[i : i + db_batch_size]

        records = [
            (
                item["content"],
                json.dumps(item["metadata"], ensure_ascii=False),
                emb,  # Truyền trực tiếp list[float], bỏ str(emb)
                f"{item['metadata']['source']}:{item['metadata']['chunk_index']}",
            )
            for item, emb in zip(chunk_slice, emb_slice)
        ]

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO medical_documents (content, metadata, embedding, chunk_key)
                VALUES ($1, $2::jsonb, $3, $4)
                ON CONFLICT (chunk_key) DO UPDATE SET
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding
                """,
                records,
            )
        inserted_count += len(records)

    return inserted_count


async def search_similar_vectors(
    query_vector: list[float],
    top_k: int = 3,
    similarity_threshold: float = 0.5,
    category_filter: str | None = None,
) -> list[dict]:
    """Tìm top_k bản ghi gần nhất với query_vector sử dụng HNSW Index & bộ lọc JSONB"""
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL hnsw.ef_search = 64;")

            sql = """
                SELECT
                    id,
                    content,
                    metadata,
                    1 - (embedding <=> $1) AS similarity
                FROM medical_documents
                WHERE 1 - (embedding <=> $1) >= $2
            """
            params: list = [query_vector, similarity_threshold]  # Truyền trực tiếp list[float]

            if category_filter:
                sql += f" AND metadata->>'category' = ${len(params) + 1}"
                params.append(category_filter)

            sql += f" ORDER BY embedding <=> $1 LIMIT ${len(params) + 1};"
            params.append(top_k)

            rows = await conn.fetch(sql, *params)

    return [
        {
            "id": row["id"],
            "content": row["content"],
            "metadata": (
                row["metadata"]
                if isinstance(row["metadata"], dict)
                else json.loads(row["metadata"])
            ),
            "similarity": round(float(row["similarity"]), 4),
        }
        for row in rows
    ]