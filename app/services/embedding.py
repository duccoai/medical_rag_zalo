import asyncio
import logging
import re
import time
from typing import Callable, Literal, overload
import httpx
import httpx2
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

# TẦNG 1 - tầng cấu hình & bằng số
# khai báo 2 kiểu dữ liệu để truy xuất (docs pdf và query từ user)
EmbeddingTaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
WaitStrategy = Callable[[RetryCallState], float]

# Luồng chat realtime Zalo: backoff ngắn (0.5s -> 2s) để không vượt retrieval_timeout
_QUERY_WAIT: WaitStrategy = wait_exponential(multiplier=0.5, min=0.5, max=2)
# Luồng nạp PDF nền: backoff tối thiểu 15s, tăng dần tới 60s để vượt qua cửa sổ giới hạn theo phút của Gemini
_BATCH_BACKOFF: WaitStrategy = wait_exponential(multiplier=5, min=15, max=60)
_RETRY_DELAY_PATTERN = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", re.IGNORECASE)

# Pacing giữa các request nạp tài liệu: dùng lock riêng (không phải semaphore) để xếp hàng và nghỉ
_pace_lock = asyncio.Lock()
_last_request_started_at: float | None = None

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

# TẦNG 2 quản lý client
# khởi tạo hàm lazy client
def get_genai_client() -> genai.Client:
    """Lazy-init Gemini Client giúp quản lý vòng đời gọn và dễ mock khi Unit Test"""
    global _client
    if _client is None:
        request_timeout_ms = int(
            max(
                settings.EMBEDDING_QUERY_TIMEOUT,
                settings.EMBEDDING_BATCH_TIMEOUT,
            )
            * 1000
        )
        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY.get_secret_value(),
            http_options=types.HttpOptions(
                timeout=request_timeout_ms,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    return _client

 # công tắc cho phép thay/ mock client từ bên ngoài (tiện cho unit test or đổi key)
def set_genai_client(client: genai.Client | None) -> None:
    """Cho phép inject Mock Client trong test hoặc reset client khi xoay vòng key"""
    global _client
    _client = client

# lọc các lỗi tạm thời như timeout, rớt mạng.. để cho phép thử lại khi đang embedding
# các lỗi này chạy qua batch wait để tự tính giờ nghỉ (ngoại trừ lỗi 429) 
def _is_transient_error(exc: Exception) -> bool:
    """Phân loại lỗi tạm thời (Timeout, Mạng, Rate Limit 429, Server 503/504)"""
    if isinstance(
        exc,
        (
            asyncio.TimeoutError,
            TimeoutError,
            ConnectionError,
            httpx.TransportError,
            httpx2.TransportError,
        ),
    ):
        return True
    if isinstance(exc, genai_errors.APIError):
        return exc.code in {429, 500, 502, 503, 504}
    msg = str(exc).lower()
    return any(code in msg for code in ("429", "503", "504", "rate limit", "timeout"))

# in cảnh báo mỗi lần chuẩn bị thử lại khi gặp các lỗi tạm thời trên
def _log_retry(state: RetryCallState) -> None:
    """Ghi log mỗi lần retry để không bị 'im lặng' khi Gemini trả 429/5xx"""
    sleep_seconds = state.next_action.sleep if state.next_action else 0.0
    logger.warning(
        "Embedding gặp lỗi tạm thời (lần thử %d), chờ %.1fs rồi thử lại: %s",
        state.attempt_number,
        sleep_seconds,
        state.outcome.exception() if state.outcome else "unknown",
    )

# riêng lỗi 429 thì sẽ dc gemini gửi dặn số giây và hàm này sẽ đọc để gửi cho batch wait chốt time delay
def _extract_retry_delay(exc: BaseException | None) -> float | None:
    """Đọc retryDelay (ví dụ '41s') Gemini gửi kèm lỗi 429 để chờ đúng thời gian server yêu cầu"""
    if exc is None:
        return None
    text = f"{exc} {getattr(exc, 'details', '') or ''}"
    match = _RETRY_DELAY_PATTERN.search(text)
    return float(match.group(1)) if match else None

# hàm chốt time delay
def _batch_wait(state: RetryCallState) -> float:
    """Thời gian chờ retry cho batch nạp PDF: max(backoff, retryDelay do server trả về)"""
    backoff = _BATCH_BACKOFF(state)
    server_delay = _extract_retry_delay(state.outcome.exception() if state.outcome else None)
    return max(backoff, server_delay or 0.0)


_BATCH_WAIT: WaitStrategy = _batch_wait

# TẦNG 4 - CỤC MÁY THỰC THI gọi Gemini model embed và nhận kết quả từ gemnini trước khi trả kết quả về biến ở tầng 5
# hàm giúp giữ khoảng cách time giữa các request khi từng batch
async def _wait_for_request_slot() -> None:
    """Giữ khoảng cách tối thiểu EMBEDDING_BATCH_INTERVAL_SECONDS giữa 2 request nạp tài liệu.
    Chỉ giữ _pace_lock để xếp hàng và nghỉ; semaphore không bị giữ nên không chặn batch khác."""
    global _last_request_started_at
    async with _pace_lock: # dùng pace lock để các batch xếp hàng giãn cách đều nhau theo EMBEDDING_BATCH_INTERVAL_SERCONS (thiết lập trong config)
        interval = settings.EMBEDDING_BATCH_INTERVAL_SECONDS
        if _last_request_started_at is not None: 
            remaining = _last_request_started_at + interval - time.monotonic()
            if remaining > 0:
                logger.info("Nghỉ %.1fs trước request embedding kế tiếp (tránh giới hạn RPM)", remaining)
                await asyncio.sleep(remaining) # nếu requets trước chưa xong thì nhả nhịp sau đó cập nhật lại với hàm bên dưới
        _last_request_started_at = time.monotonic()

# hàm giám sát và bảo vệ bên ngoài cho hàm con (hàm nội bộ _call_api() bên trong trực tiếp làm))
async def _embed_single_payload_with_retry(
    payload: str | list[str],
    task_type: EmbeddingTaskType,
    timeout: float,
    max_retries: int,
    wait: WaitStrategy,
) -> list[list[float]]:
    """Gọi Gemini Embedding cho 1 payload (1 chuỗi hoặc 1 batch) kèm timeout & retry bằng tenacity"""
    client = get_genai_client() # lấy kết nối chuẩn bị sẵn đề hàm _cal_api() dùng

    # hàm nội bộ gọi model gemini-embedding-001 có bọc 
    async def _call_api() -> list[list[float]]:
        response = await asyncio.wait_for( # bọc chống bị treo
            client.aio.models.embed_content( # gọi model embed với model, contents, task_type..
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
        async for attempt in AsyncRetrying( # dùng AsyncRetrying của tenacity để tự động thử lại với quy định thử lại rõ ràng bên dưới
            stop=stop_after_attempt(max_retries + 1), # quy định số lần dc phép thử lại đến khi dừng hẳn (set trong config, còn "+1" là lần gọi chính)
            wait=wait, # quy tắc số giây ngủ (chờ) đến lượt thử lại sau khi lỗi (với wait = _QUERY_WAIT; _BATCH_WAIT)
            retry=retry_if_exception(_is_transient_error),
            before_sleep=_log_retry,
            reraise=True,
        ):
            with attempt:
                return await _call_api()

# trường hợp thất bại hoàn toàn (nhiều lần thử lại vẫn lỗi)
    except Exception as exc:
        if _is_transient_error(exc):
            raise TransientServiceException( # lỗi tạm thời sẽ biến thành TransientServiceExc ko thể retry
                f"Dịch vụ Embedding tạm thời quá tải hoặc timeout sau {max_retries + 1} lần thử: {exc}"
            ) from exc
        # Lỗi không thể retry (API Key sai, sai model, payload không hợp lệ từ phía API)
        raise AppBaseException(
            message=f"Lỗi gọi Gemini Embedding API ({task_type}): {exc}",
            status_code=502,
            retryable=False,
        ) from exc

    raise TransientServiceException("Lỗi không xác định khi tạo embedding.")

# TẦNG 5
# HÀM ĐIỀU PHỐI LÕI (nhận từ 2 hàm chính, check rồi phân loại theo 2 hướng, and gửi -> model Embed -> nhận vectors)
# hướng 1: nếu là str -> cho đi làn nhanh (timeout ngắn, retry nhanh rồi đẩy thẳng xuống TẦNG 4)
# hướng 2: nếu là list[str] -> chia thành từng lô (batch), dùng Semaphore giới hạn số lô chạy cùng lúc rồi đẩy từng lô xuống TẦNG 4
async def _embed_core(
    texts: str | list[str],
    task_type: EmbeddingTaskType,
) -> list[float] | list[list[float]]:
    """Điều phối embedding theo kích thước đầu vào (1D realtime vs 2D Batching + Semaphore)"""
    # Trường hợp 1: Truyền 1 chuỗi đơn lẻ (thường dùng cho luồng realtime Zalo Query)
    if isinstance(texts, str):
        if not texts.strip():
            raise AppBaseException(   # kiểm tra nếu rỗng thì raise ngay cho AppBaseExc
                message="Văn bản đầu vào để tạo embedding không được để trống.",
                status_code=400,
            )
        # sau khi check và phân loại theo 2 hướng để embed xong thì
        # hàm này là lệnh gọi nhờ tầng 4 làm việc (nơi xử lý chính việc gọi model và await sẽ chờ đến lúc tầng 4 xử lý và trả về cho biến vectors)
        vectors = await _embed_single_payload_with_retry(  # await báo cho python biết tạm dừng luồng này đợi model gửi vectordb về rồi mới chạy tiếp luồng sau
            payload=texts,
            task_type=task_type,
            timeout=settings.EMBEDDING_QUERY_TIMEOUT,
            max_retries=2,
            wait=_QUERY_WAIT,
        )
        return vectors[0] # biến vectors nhận kết quả trả về từ model sau khi tầng 4 xử lý

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

    total_batches = len(batches)
    completed = 0

    async def _bounded_batch(batch: list[str]) -> list[list[float]]:
        nonlocal completed
        # Pacing trước semaphore: chờ đến lượt gửi request mà không giữ slot đồng thời
        await _wait_for_request_slot()
        async with semaphore:
            vectors = await _embed_single_payload_with_retry(
                payload=batch,
                task_type=task_type,
                timeout=settings.EMBEDDING_BATCH_TIMEOUT,
                max_retries=settings.EMBEDDING_BATCH_MAX_RETRIES,
                wait=_BATCH_WAIT,
            )
        completed += 1
        logger.info("Embedding batch %d/%d xong (%d vectors)", completed, total_batches, len(vectors))
        return vectors

    batch_results = await asyncio.gather(*(_bounded_batch(b) for b in batches))
    # Gộp kết quả các batch theo đúng thứ tự ban đầu
    return [vec for batch_vecs in batch_results for vec in batch_vecs]


# Cổng giao tiếp (nhận chunks và queries)
# 2 hàm chính embed_docs và embed_queries chỉ nhận đầu vào (str or list[str]), gán type task rồi chuyển xuống _embed_core
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
