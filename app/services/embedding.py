# app/services/embedding.py
from typing import Literal
from google import genai
from google.genai import types
from app.core.config import settings
from app.core.exceptions import AppBaseException

client = genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())

EMBEDDING_MODEL = "gemini-embedding-001"
VECTOR_DIMENSIONS = 768
EmbeddingTaskType = Literal["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"]


async def get_embedding(
    text: str,
    task_type: EmbeddingTaskType = "RETRIEVAL_QUERY",
) -> list[float]:
    """Nhúng đơn lẻ — mặc định phục vụ câu hỏi truy vấn của người dùng"""
    try:
        response = await client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=VECTOR_DIMENSIONS,
            ),
        )
        return response.embeddings[0].values
    except Exception as e:
        raise AppBaseException(
            message=f"Lỗi tạo Vector Embedding: {str(e)}",
            status_code=502,
        )


async def get_embeddings_batch(
    texts: list[str],
    task_type: EmbeddingTaskType = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """Nhúng hàng loạt (Batching) — mặc định phục vụ nạp tài liệu vào Vector DB"""
    if not texts:
        return []
    try:
        response = await client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=VECTOR_DIMENSIONS,
            ),
        )
        return [emb.values for emb in response.embeddings]
    except Exception as e:
        raise AppBaseException(
            message=f"Lỗi tạo Batch Vector Embeddings: {str(e)}",
            status_code=502,
        )