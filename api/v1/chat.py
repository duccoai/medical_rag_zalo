from app.core.exceptions import AppBaseException
from app.schemas.chat_schema import ChatRequest, ChatResponse
from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["Chat Test"])

#endpoit chat_with_bot nhận dữ liệu đầu vào thông qua schema Pydantic
@router.post("", response_model=ChatResponse, summary="Gửi câu hỏi y tế (Mock)")
async def chat_with_bot(payload: ChatRequest):
    # Giả lập tình huống bắn lỗi nghiệp vụ để test Exception Handler ở Bước 2
    if "lỗi" in payload.message.lower():
        raise AppBaseException(
            message="Không thể xử lý câu hỏi chứa từ khóa cấm.", status_code=400
        )

    # Dữ liệu giả lập (Sẽ thay bằng rag_engine ở Hạng mục 6)
    mock_reply = f"[MOCK RESPONSE] Hệ thống đã nhận câu hỏi của bạn ({payload.user_id}): '{payload.message}'"

    return ChatResponse(
        reply=mock_reply, sources=["Duoc_Thu_Quoc_Gia_2022.pdf (Trang 45)"]
    )