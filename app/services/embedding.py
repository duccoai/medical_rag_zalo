import asyncio
from typing import Callable, Literal, overload
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from app.core.config import settings
from app.core.exceptions import AppBaseException, TransientServiceException

EmbeddingTaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
WaitStrategy = Callable[[RetryCallState], float]

# Luồng chat realtime Zalo: backoff ngắn (0.5s -> 2s) để không vượt retrieval_timeout
_QUERY_WAIT: WaitStrategy = wait_exponential(multiplier=0.5, min=0.5, max=2)
# Luồng nạp PDF nền: chờ tối thiểu 5s, tăng dần tới 60s để vượt qua cửa sổ giới hạn theo phút của Gemini
_BATCH_WAIT: WaitStrategy = wait_exponential(multiplier=2, min=5, max=60)

_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    """Lazy-init Gemini Client giúp quản lý vòng đời gọn và dễ mock khi Unit Test"""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())
    return _client


def set_genai_client(client: genai.Client | None) -> None:
    """Cho phép inject Mock Client trong test hoặc reset client khi xoay vòng key"""
    global _client
    _client = client


def _is_transient_error(exc: Exception) -> bool:
    """Phân loại lỗi tạm thời (Timeout, Mạng, Rate Limit 429, Server 503/504)"""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, genai_errors.APIError):
        return exc.code in {429, 500, 502, 503, 504}
    msg = str(exc).lower()
    return any(code in msg for code in ("429", "503", "504", "rate limit", "timeout"))


async def _embed_single_payload_with_retry(
    payload: str | list[str],
    task_type: EmbeddingTaskType,
    timeout: float,
    max_retries: int,
    wait: WaitStrategy,
) -> list[list[float]]:
    """Gọi Gemini Embedding cho 1 payload (1 chuỗi hoặc 1 batch) kèm timeout & retry bằng tenacity"""
    client = get_genai_client()

    async def _call_api() -> list[list[float]]:
        response = await asyncio.wait_for(
            client.aio.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=payload,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.EMBEDDING_DIMENSIONS,
                ),
            ),
            timeout=timeout,
        )
        return [emb.values for emb in response.embeddings]

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait,
            retry=retry_if_exception(_is_transient_error),
            reraise=True,
        ):
            with attempt:
                return await _call_api()

    except Exception as exc:
        if _is_transient_error(exc):
            raise TransientServiceException(
                f"Dịch vụ Embedding tạm thời quá tải hoặc timeout sau {max_retries + 1} lần thử: {exc}"
            ) from exc
        # Lỗi không thể retry (API Key sai, sai model, payload không hợp lệ từ phía API)
        raise AppBaseException(
            message=f"Lỗi gọi Gemini Embedding API ({task_type}): {exc}",
            status_code=502,
            retryable=False,
        ) from exc

    raise TransientServiceException("Lỗi không xác định khi tạo embedding.")


async def _embed_core(
    texts: str | list[str],
    task_type: EmbeddingTaskType,
) -> list[float] | list[list[float]]:
    """Điều phối embedding theo kích thước đầu vào (1D realtime vs 2D Batching + Semaphore)"""
    # Trường hợp 1: Truyền 1 chuỗi đơn lẻ (thường dùng cho luồng realtime Zalo Query)
    if isinstance(texts, str):
        if not texts.strip():
            raise AppBaseException(
                message="Văn bản đầu vào để tạo embedding không được để trống.",
                status_code=400,
            )
        vectors = await _embed_single_payload_with_retry(
            payload=texts,
            task_type=task_type,
            timeout=settings.EMBEDDING_QUERY_TIMEOUT,
            max_retries=2,
            wait=_QUERY_WAIT,
        )
        return vectors[0]

    # Trường hợp 2: Truyền danh sách văn bản (thường dùng cho luồng nạp PDF lớn)
    if not texts:
        return []

    if any(not isinstance(t, str) or not t.strip() for t in texts):
        raise AppBaseException(
            message="Danh sách văn bản chứa phần tử rỗng hoặc không hợp lệ.",
            status_code=400,
        )

    batch_size = settings.EMBEDDING_BATCH_SIZE
    batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
    semaphore = asyncio.Semaphore(settings.EMBEDDING_MAX_CONCURRENCY)

    async def _bounded_batch(batch: list[str]) -> list[list[float]]:
        async with semaphore:
            vectors = await _embed_single_payload_with_retry(
                payload=batch,
                task_type=task_type,
                timeout=settings.EMBEDDING_BATCH_TIMEOUT,
                max_retries=settings.EMBEDDING_BATCH_MAX_RETRIES,
                wait=_BATCH_WAIT,
            )
            # Nghỉ giữa các batch để không dồn request trong cùng một phút
            await asyncio.sleep(settings.EMBEDDING_BATCH_INTERVAL_SECONDS)
            return vectors

    batch_results = await asyncio.gather(*(_bounded_batch(b) for b in batches))
    # Gộp kết quả các batch theo đúng thứ tự ban đầu
    return [vec for batch_vecs in batch_results for vec in batch_vecs]


@overload
async def embed_documents(texts: str) -> list[float]: ...
@overload
async def embed_documents(texts: list[str]) -> list[list[float]]: ...
async def embed_documents(
    texts: str | list[str],
) -> list[float] | list[list[float]]:
    """Nhúng nội dung tài liệu lưu trữ (task_type='RETRIEVAL_DOCUMENT')."""
    return await _embed_core(texts, task_type="RETRIEVAL_DOCUMENT")


@overload
async def embed_queries(texts: str) -> list[float]: ...
@overload
async def embed_queries(texts: list[str]) -> list[list[float]]: ...
async def embed_queries(
    texts: str | list[str],
) -> list[float] | list[list[float]]:
    """Nhúng câu hỏi truy vấn tìm kiếm (task_type='RETRIEVAL_QUERY')."""
    return await _embed_core(texts, task_type="RETRIEVAL_QUERY")
