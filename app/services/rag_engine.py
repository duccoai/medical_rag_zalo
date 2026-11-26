import logging
import math
import asyncio
import time

import httpx
import httpx2
from google import genai
from google.genai import errors, types

from app.core.config import settings
from app.core.exceptions import (AppBaseException, TransientServiceException)
from app.schemas.medical import MedicalResponseSchema
from app.db.pgvector_store import (
    insert_chunks_with_embeddings,
    search_similar_vectors,
)
from app.services.embedding import embed_documents, embed_queries

logger = logging.getLogger(__name__)

# Cho phép đủ thời gian sinh JSON; vẫn giới hạn từng model trước khi fallback.
LLM_TIMEOUT_MS = 30_000

# Client Gemini (google-genai). Dùng client.aio để gọi bất đồng bộ, không block event loop của FastAPI
client = genai.Client(
    api_key=settings.GEMINI_API_KEY.get_secret_value(),
    http_options=types.HttpOptions(
        timeout=LLM_TIMEOUT_MS,
        retry_options=types.HttpRetryOptions(attempts=1),
    ),
)

# Danh sách model theo thứ tự ưu tiên: phần tử đầu là model chính, các phần tử sau là model dự phòng.
LLM_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
]
# Mã lỗi quá tải (503) hoặc hết thời gian chờ phía server (504) thì mới chuyển sang model kế tiếp
FALLBACK_STATUS_CODES = {429, 503, 504}

SYSTEM_INSTRUCTION = (
    "Bạn là Trợ lý Y tế Thông minh. Chỉ sử dụng thông tin trong tài liệu Context được cung cấp để tư vấn.\n"
    "Tuyệt đối không tự suy đoán hoặc bịa đặt liều dùng thuốc ngoài tài liệu. "
    "Nếu Context không chứa thông tin liên quan đến câu hỏi, hãy lịch sự từ chối trả lời và khuyên người dùng hỏi bác sĩ."
)

EMERGENCY_KEYWORDS = [
    "tự tử", "uống thuốc trừ sâu", "uống thuốc sâu",
    "ngưng thở", "bất tỉnh", "co giật", "đau ngực dữ dội", "nôn ra máu"
]


# Lớp bảo vệ 1: lọc từ khóa cấp cứu để trả cảnh báo ngay, không tốn token gọi AI
def check_input_guardrail(query: str) -> MedicalResponseSchema | None:
    """Chặn ngay các tình huống cấp cứu trước khi gọi LLM"""
    query_lower = query.lower()
    if any(keyword in query_lower for keyword in EMERGENCY_KEYWORDS):
        return MedicalResponseSchema(
            answer="CẢNH BÁO KHẨN CẤP: Tình trạng bạn mô tả có nguy cơ đe dọa tính mạng. Hãy gọi ngay cấp cứu 115 hoặc đưa người bệnh đến cơ sở y tế gần nhất ngay lập tức!",
            recommended_dosage=None,
            sources=["Quy trình Sơ cấp cứu Khẩn cấp - Bộ Y tế"],
            urgency_flag=True,
        )
    return None


# Gọi một model Gemini cụ thể và parse kết quả về MedicalResponseSchema.
# Lỗi APIError được ném nguyên để tầng gọi quyết định có fallback hay không.
async def _call_gemini(model: str, full_prompt: str) -> MedicalResponseSchema:
    response = await client.aio.models.generate_content(
        model=model,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=MedicalResponseSchema,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        ),
    )
    # Ưu tiên response.parsed (đã được SDK map sang Pydantic), fallback sang parse JSON thô
    if isinstance(response.parsed, MedicalResponseSchema):
        return response.parsed
    if not response.text:
        raise ValueError("Gemini trả về nội dung rỗng (có thể bị chặn bởi safety filter)")
    return MedicalResponseSchema.model_validate_json(response.text)


async def ingest_document_chunks(chunks: list[dict]) -> int:
    """Luồng Ingest (chạy ở Background Worker): embed + lưu pgvector theo từng batch để có tiến độ và không mất công khi lỗi"""
    if not chunks:
        return 0
    batch_size = settings.EMBEDDING_BATCH_SIZE
    total = len(chunks)
    total_batches = math.ceil(total / batch_size)
    inserted_total = 0
    logger.info("Bắt đầu nạp %d chunks thành %d batch (mỗi batch tối đa %d)", total, total_batches, batch_size)
    for batch_no, start in enumerate(range(0, total, batch_size), start=1):
        batch = chunks[start : start + batch_size]
        batch_started = time.perf_counter()
        vectors = await embed_documents([item["content"] for item in batch])
        # Upsert theo chunk_key "<source>:<chunk_index>" nên chạy lại không nhân đôi dữ liệu
        inserted = await insert_chunks_with_embeddings(chunks=batch, embeddings=vectors)
        inserted_total += inserted
        logger.info(
            "Batch %d/%d hoàn tất: upsert %d chunks trong %.1fs (tổng %d/%d)",
            batch_no, total_batches, inserted, time.perf_counter() - batch_started, inserted_total, total,
        )
    return inserted_total


async def retrieve_medical_contexts(
    query: str,
    top_k: int = 3,
    similarity_threshold: float = 0.5,
    category_filter: str | None = None,
    retrieval_timeout: float = 6.0,
) -> list[dict]:
    """Luồng Query Realtime (Zalo Chat): Embed câu hỏi + Truy vấn HNSW trong giới hạn timeout"""
    async def _run_retrieval() -> list[dict]:
        query_vector = await embed_queries(query)
        return await search_similar_vectors(
            query_vector=query_vector,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            category_filter=category_filter,
        )

    try:
        return await asyncio.wait_for(_run_retrieval(), timeout=retrieval_timeout)
    except asyncio.TimeoutError as exc:
        raise TransientServiceException(
            f"Quá thời gian truy xuất dữ liệu y tế ({retrieval_timeout}s)."
        ) from exc

# Hàm điều phối chính: ghép context vào prompt và trả về câu trả lời đúng cấu trúc MedicalResponseSchema.
# Nếu model hiện tại trả về 503/504, tự động thử model dự phòng tiếp theo trong LLM_MODELS.
async def generate_medical_answer(
    query: str, retrieved_contexts: list[str]) -> MedicalResponseSchema:

    emergency_response = check_input_guardrail(query)
    if emergency_response:
        return emergency_response

    context_str = "\n---\n".join(retrieved_contexts)
    # Chỉ ghép Context và câu hỏi; chỉ dẫn vai trò đã nằm trong SYSTEM_INSTRUCTION
    full_prompt = (
        f"Context:\n{context_str}\n\n"
        f"Câu hỏi của người dùng: {query}"
    )

    last_error: Exception | None = None
    for index, model in enumerate(LLM_MODELS):
        try:
            return await _call_gemini(model, full_prompt)

        except errors.APIError as e:
            logger.error(
                "Lỗi gọi Gemini API (model=%s, code=%s, status=%s): %s",
                model, e.code, e.status, e.message,
            )
            # Chỉ fallback lỗi rate limit hoặc lỗi tạm thời phía dịch vụ.
            if e.code not in FALLBACK_STATUS_CODES:
                raise AppBaseException(
                    message="Dịch vụ tư vấn AI tạm thời không khả dụng, vui lòng thử lại sau.",
                    status_code=502,
                ) from e

            last_error = e
            has_next = index + 1 < len(LLM_MODELS)
            if has_next:
                logger.warning(
                    "Model %s quá tải (code=%s), chuyển sang model dự phòng %s",
                    model, e.code, LLM_MODELS[index + 1],
                )

        except (
            httpx.TransportError,
            httpx2.TransportError,
            TimeoutError,
            ConnectionError,
        ) as e:
            last_error = e
            has_next = index + 1 < len(LLM_MODELS)
            logger.warning(
                "Lỗi kết nối Gemini (model=%s, error=%s): %s",
                model,
                type(e).__name__,
                e,
            )
            if has_next:
                logger.warning(
                    "Chuyển từ model %s sang model dự phòng %s",
                    model,
                    LLM_MODELS[index + 1],
                )

        except Exception as ex:
            # Lỗi cấu hình, parse JSON hoặc validate không phải lỗi kết nối tạm thời.
            logger.exception("Lỗi không xác định khi gọi Gemini (model=%s): %s", model, ex)
            raise AppBaseException(
                message="Lỗi hệ thống khi gọi dịch vụ tư vấn AI.",
                status_code=502,
            ) from ex

    # Tất cả model trong danh sách đều quá tải/timeout -> Trả về TransientServiceException (503, retryable=True)
    logger.error("Tất cả model dự phòng (%s) đều không khả dụng", ", ".join(LLM_MODELS))
    raise TransientServiceException(
        "Dịch vụ tư vấn AI tạm thời quá tải hoặc hết thời gian phản hồi, vui lòng thử lại sau ít phút."
    ) from last_error

# Hàm chuyển danh sách kết quả từ pgvector thành các khối text có ghi rõ nguồn & tiêu đề để LLM trích dẫn chuẩn
def _format_retrieved_contexts(matches: list[dict]) -> list[str]:
    """Định dạng kết quả từ pgvector kèm metadata nguồn rõ ràng để LLM trích dẫn chính xác"""
    formatted_contexts: list[str] = []
    for idx, item in enumerate(matches, start=1):
        meta = item.get("metadata") or {}
        source = meta.get("source", "Tài liệu y khoa")
        headers = meta.get("headers")

        # Ghép chuỗi phân cấp tiêu đề (h1 > h2...) nếu có, không thì fallback sang số trang hoặc tên nguồn
        if isinstance(headers, dict) and headers:
            section = " > ".join(str(v) for v in headers.values() if v)
            citation = f"{source} ({section})" if section else source
        elif meta.get("page"):
            citation = f"{source} (Trang {meta['page']})"
        else:
            citation = source

        formatted_contexts.append(
            f"[Tài liệu {idx} | Nguồn: {citation} | Độ tương đồng: {item['similarity']}]\n"
            f"{item['content']}"
        )
    return formatted_contexts


# Hàm điều phối trọn luồng hỏi - đáp RAG: Guardrail -> Tìm vector -> Chặn nếu rỗng -> Ghép ngữ cảnh & gọi LLM
async def answer_medical_query(
    query: str,
    top_k: int = 3,
    similarity_threshold: float = 0.5,
    category_filter: str | None = None,
) -> MedicalResponseSchema:
    """Pipeline RAG hoàn chỉnh: Guardrail -> Retrieve pgvector -> Format Context -> Generate LLM"""
    # Bước 1: Kiểm tra từ khóa cấp cứu ngay từ đầu (0ms DB, 0 token LLM)
    emergency_response = check_input_guardrail(query)
    if emergency_response:
        return emergency_response

    # Bước 2: Nhúng câu hỏi và truy vấn các đoạn tài liệu y tế liên quan nhất từ PostgreSQL
    matches = await retrieve_medical_contexts(
        query=query,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        category_filter=category_filter,
    )

    # Bước 3: Nếu không có chunk nào đạt ngưỡng tương đồng thì từ chối lịch sự, không gọi LLM đoán mò
    if not matches:
        return MedicalResponseSchema(
            answer=(
                "Xin lỗi, cơ sở dữ liệu y khoa hiện tại của tôi chưa có thông tin chính thức "
                "về vấn đề bạn đang hỏi. Bạn vui lòng tham khảo ý kiến trực tiếp của bác sĩ "
                "hoặc dược sĩ chuyên môn để được tư vấn chính xác."
            ),
            recommended_dosage=None,
            sources=[],
            urgency_flag=False,
        )

    # Bước 4: Chuẩn hóa context kèm thông tin nguồn rồi gọi hàm sinh câu trả lời có cấu trúc
    formatted_contexts = _format_retrieved_contexts(matches)
    return await generate_medical_answer(
        query=query,
        retrieved_contexts=formatted_contexts,
    )