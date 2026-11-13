from pydantic import BaseModel, Field

#khai báo đầy đủ các field cho cả ChatRequest và ChatReponse với Pydantic Field(...)
class ChatRequest(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
        examples=["user_001"],
        description="ID định danh người dùng",
    )
    message: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        examples=["Trẻ bị sốt xuất huyết nên uống thuốc gì?"],
        description="Câu hỏi tư vấn y tế",
    )


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Câu trả lời tư vấn từ hệ thống")
    sources: list[str] = Field(
        default_factory=list, description="Danh sách tài liệu y tế trích dẫn"
    )
    disclaimer: str = Field(
        default="Lưu ý: Thông tin chỉ mang tính tham khảo, không thay thế chỉ định của bác sĩ.",
        description="Cảnh báo y khoa bắt buộc",
    )