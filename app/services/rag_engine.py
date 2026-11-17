import logging
import traceback

from google import genai
from google.genai import errors, types

from app.core.config import settings
from app.core.exceptions import AppBaseException
from app.schemas.medical import MedicalResponseSchema

logger = logging.getLogger(__name__)

# Thời gian chờ tối đa cho mỗi request tới Gemini (đơn vị: mili giây).
# Không có timeout thì socket bị treo sẽ khiến loading chờ vô hạn.
LLM_TIMEOUT_MS = 60_000

# Client Gemini (google-genai). Dùng client.aio để gọi bất đồng bộ, không block event loop của FastAPI
client = genai.Client(
    api_key=settings.GEMINI_API_KEY.get_secret_value(),
    http_options=types.HttpOptions(timeout=LLM_TIMEOUT_MS),  # qly timeout 60s tránh bị treo kết nối socket vô hạn
)

# Danh sách model theo thứ tự ưu tiên: phần tử đầu là model chính, các phần tử sau là model dự phòng.
LLM_MODELS = [
    "gemini-3.5-flash",       # model chính
    "gemini-3.7-flash",       # dự phòng 1
    "gemini-3.8-flash",  # dự phòng 2
]
# Mã lỗi quá tải (503) hoặc hết thời gian chờ phía server (504) thì mới chuyển sang model kế tiếp
FALLBACK_STATUS_CODES = {503, 504}

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
            temperature=0.1,
            # Tắt hoàn toàn cơ chế thinking để tối ưu tốc độ phản hồi cho RAG (< 3s)
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    # Ưu tiên response.parsed (đã được SDK map sang Pydantic), fallback sang parse JSON thô
    if isinstance(response.parsed, MedicalResponseSchema):
        return response.parsed
    if not response.text:
        raise ValueError("Gemini trả về nội dung rỗng (có thể bị chặn bởi safety filter)")
    return MedicalResponseSchema.model_validate_json(response.text)


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

    last_error: errors.APIError | None = None
    for index, model in enumerate(LLM_MODELS):
        try:
            return await _call_gemini(model, full_prompt)

        except errors.APIError as e:
            # IN CHI TIẾT LỖI RA TERMINAL ĐỂ DEBUG
            print(f"🔥 LỖI GOOGLE API CHI TIẾT: model={model}, code={e.code}, status={e.status}, message={e.message}")
            logger.error(
                "Lỗi gọi Gemini API (model=%s, code=%s, status=%s): %s",
                model, e.code, e.status, e.message,
            )
            # Lỗi khác 503/504 (ví dụ 400, 401, 429) không phải lỗi tạm thời của server nên không fallback
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
                print(f"⚠️ Model {model} lỗi {e.code}, đang chuyển sang {LLM_MODELS[index + 1]}")

        except Exception as ex:
            # Bắt các lỗi khác: timeout/kết nối, lỗi parse JSON, lỗi validate Pydantic, lỗi thư viện
            print(f"🔥 LỖI KHÔNG XÁC ĐỊNH (model={model}): {type(ex).__name__}: {ex}")
            print(traceback.format_exc())
            logger.exception("Lỗi không xác định khi gọi Gemini (model=%s): %s", model, ex)
            raise AppBaseException(
                message=f"Lỗi hệ thống: {type(ex).__name__}: {ex}",
                status_code=502,
            ) from ex

    # Tất cả model trong danh sách đều quá tải/timeout
    logger.error("Tất cả model dự phòng (%s) đều không khả dụng", ", ".join(LLM_MODELS))
    raise AppBaseException(
        message="Dịch vụ tư vấn AI tạm thời không khả dụng, vui lòng thử lại sau.",
        status_code=502,
    ) from last_error
