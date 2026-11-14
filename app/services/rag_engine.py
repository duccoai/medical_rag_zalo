from google import genai
from google.genai import errors
from app.core.config import settings
from app.core.exceptions import AppBaseException
from app.schemas.medical import MedicalResponseSchema


# khởi tạo kết nối với OpenAI nhưng là bất đồng bộ (Async) -> tránh nghẽn server khi nhiều ng truy cập
client = genai.Client(api_key=settings.OPENAI_API_KEY.get_secret_value())

EMERGENCY_KEYWORDS = [
    "tự tử", "uống thuốc trừ sâu", "uống thuốc sâu",
    "ngưng thở", "bất tỉnh", "co giật", "đau ngực dữ dội", "nôn ra máu"
]


# định nghĩa hàm chốt chặn lọc các từ khóa cấm từ (EMERGENCY_KEYWORDS) để trả cảnh báo lập tức mà ko cần tốn token gọi AI 
def check_input_guardrail(query: str) -> MedicalResponseSchema | None:
    """Lớp bảo vệ 1: Chặn ngay các tình huống cấp cứu trước khi gọi LLM"""
    query_lower = query.lower()
    if any(keyword in query_lower for keyword in EMERGENCY_KEYWORDS):
        return MedicalResponseSchema(
            answer="CẢNH BÁO KHẨN CẤP: Tình trạng bạn mô tả có nguy cơ đe dọa tính mạng. Hãy gọi ngay cấp cứu 115 hoặc đưa người bệnh đến cơ sở y tế gần nhất ngay lập tức!",
            recommended_dosage=None,
            sources=["Quy trình Sơ cấp cứu Khẩn cấp - Bộ Y tế"],
            urgency_flag=True,
        )
    return None

# định nghĩa hàm điều phối chính (nơi gói data vào prompt được thiết kế chuẩn để AI nhận và trả về answer chuẩn cấu trúc và tránh hallucination)
async def generate_medical_answer(
    query: str, retrieved_contexts: list[str]) -> MedicalResponseSchema:
    
    # 1. Kiểm tra Input Guardrail trước
    emergency_response = check_input_guardrail(query)
    if emergency_response:
        return emergency_response

    # 2. Ghép ngữ cảnh y tế vào System Prompt
    context_str = "\n---\n".join(retrieved_contexts)
    full_prompt = (
        "Bạn là Trợ lý Y tế Thông minh. Chỉ sử dụng thông tin trong tài liệu Context được cung cấp để tư vấn.\n"
        "Tuyệt đối không tự suy đoán hoặc bịa đặt liều dùng thuốc ngoài tài liệu. "
        "Nếu Context không chứa thông tin liên quan đến câu hỏi, hãy lịch sự từ chối trả lời và khuyên người dùng hỏi bác sĩ.\n\n"
        f"Context:\n{context_str}\n\n"
        f"Câu hỏi của người dùng: {query}"
    )

    # 3. Gọi LLM bất đồng bộ và ép kiểu đầu ra theo MedicalResponseSchema
    try:
            # Sử dụng client.aio cho bất đồng bộ (async) để không block FastAPI
            response = await client.aio.models.generate_content(
                model="gemini-1.5-flash",  # Model tối ưu và mới nhất của Google
                contents=full_prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": MedicalResponseSchema, # Ép đúng cấu trúc Pydantic
                    "temperature": 0.1,  # Giảm tối đa ảo giác
                },
            )
            
            # SDK mới của Google trả về đối tượng đã được parse tự động vào parsed
            parsed_result = response.parsed
            if not parsed_result:
                raise AppBaseException("Mô hình AI không trả về dữ liệu hợp lệ.", status_code=502)
            return parsed_result

    except errors.APIError as e:
            # Bắt lỗi từ Google API và đưa về chuẩn AppBaseException (502 Bad Gateway)
            raise AppBaseException(
                message=f"Lỗi kết nối dịch vụ Google AI: {str(e)}", status_code=502
            )