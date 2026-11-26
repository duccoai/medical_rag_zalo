from app.core.exceptions import AppBaseException
from app.schemas.chat_schema import ChatRequest, ChatResponse
from fastapi import APIRouter
from app.services.rag_engine import generate_medical_answer
from app.services.rag_engine import answer_medical_query

#router = APIRouter(prefix="/chat", tags=["Chat Test"])

##- ----- endpoit chat_with_bot nhận dữ liệu đầu vào thông qua schema Pydantic
# @router.post("", response_model=ChatResponse, summary="Gửi câu hỏi y tế (Mock)")
# async def chat_with_bot(payload: ChatRequest):
#     # Giả lập tình huống bắn lỗi nghiệp vụ để test Exception Handler ở Bước 2
#     if "lỗi" in payload.message.lower():
#         raise AppBaseException(
#             message="Không thể xử lý câu hỏi chứa từ khóa cấm.", status_code=400
#         )

#     # Dữ liệu giả lập (Sẽ thay bằng rag_engine ở Hạng mục 6)
#     mock_reply = f"[MOCK RESPONSE] Hệ thống đã nhận câu hỏi của bạn ({payload.user_id}): '{payload.message}'"

#     return ChatResponse(
#         reply=mock_reply, sources=["Duoc_Thu_Quoc_Gia_2022.pdf (Trang 45)"]
#     )

router = APIRouter(prefix="/chat", tags=["Chat"])

# Ngữ cảnh tạm thời trước khi tích hợp PDF & pgvector ở Hạng mục 4-5
TEMP_MEDICAL_CONTEXT = [
    "Nguồn: Hướng dẫn chẩn đoán và điều trị Sốt xuất huyết Dengue - Bộ Y tế (Trang 12). "
    "Khi bệnh nhân sốt cao >= 38.5 độ C, cho uống thuốc hạ sốt Paracetamol đơn chất, "
    "liều dùng từ 10 - 15 mg/kg cân nặng mỗi lần, cách nhau mỗi 4 - 6 giờ. "
    "Tuyệt đối không dùng Aspirin, Analgin, Ibuprofen để hạ sốt vì có thể gây xuất huyết, toan máu."
]

# Endpoint POST /api/v1/chat: nối trực tiếp pipeline RAG thật (Guardrail -> Vector DB -> LLM)
@router.post("", response_model=ChatResponse, summary="Tư vấn y tế qua RAG & LLM Guardrail")
async def chat_with_bot(payload: ChatRequest):
    # Gọi bộ điều phối RAG hoàn chỉnh, không còn dùng context giả lập TEMP_MEDICAL_CONTEXT nữa
    ai_result = await answer_medical_query(
        query=payload.message,
        top_k=3,
        similarity_threshold=0.5,
        category_filter=payload.category,
    )

    # Chuyển đổi kết quả từ MedicalResponseSchema sang ChatResponse
    return ChatResponse(
        reply=ai_result.answer,
        recommended_dosage=ai_result.recommended_dosage,
        sources=ai_result.sources,
        disclaimer=ai_result.disclaimer,
        urgency_flag=ai_result.urgency_flag,
        is_mock=False,
    )