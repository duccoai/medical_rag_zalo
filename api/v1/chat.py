from app.core.exceptions import AppBaseException
from app.schemas.chat_schema import ChatRequest, ChatResponse
from fastapi import APIRouter
from app.services.chat_memory_service import answer_with_memory

from pydantic import BaseModel, Field
from app.services.chat_memory import clear_history

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("", response_model=ChatResponse, summary="Tư vấn y tế qua RAG & LLM Guardrail")
async def chat_with_bot(payload: ChatRequest):
    ai_result = await answer_with_memory(
        user_id=payload.user_id,
        message=payload.message,
        category=payload.category,
    )
    return ChatResponse(
        reply=ai_result.answer,
        recommended_dosage=ai_result.recommended_dosage,
        sources=ai_result.sources,
        disclaimer=ai_result.disclaimer,
        urgency_flag=ai_result.urgency_flag,
        is_mock=False,
    )



class ResetMemoryRequest(BaseModel):
    user_id: str = Field(..., min_length=1)

@router.post("/memory/reset", summary="Xóa lịch sử hội thoại của một người dùng")
async def reset_memory(payload: ResetMemoryRequest):
    await clear_history(payload.user_id)
    return {"success": True}
