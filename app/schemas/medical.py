from pydantic import BaseModel, Field, field_validator


# lớp này sử dụng pydantic v2 kế thừa từ basemodel để ép kiểu dữ liệu đúng với khuôn, đủ các trường (answer, recommended,sources...)
class MedicalResponseSchema(BaseModel):
    answer: str = Field(
        ...,
        description="Nội dung tư vấn sức khỏe ngắn gọn, dễ hiểu dựa trên tài liệu gốc",
    )
    recommended_dosage: str | None = Field(
        default=None,
        description="Liều dùng khuyến nghị trích xuất từ tài liệu (nếu có)",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Danh sách tên văn bản/trang tài liệu tham khảo",
    )
    disclaimer: str = Field(
        default="Lưu ý: Thông tin chỉ mang tính chất tham khảo, không thay thế cho chỉ định trực tiếp từ Bác sĩ.",
        description="Lời cảnh báo miễn trừ trách nhiệm y khoa bắt buộc",
    )
    # cơ chế in/output này của guardrails giúp đánh dấu mức nguy hiểm của user, True sẽ ngưng chat và phát cảnh báo or gọi 115
    urgency_flag: bool = Field(
        default=False,
        description="Đánh dấu True nếu phát hiện dấu hiệu bệnh lý nguy hiểm cần đi cấp cứu ngay",
    )

    #decorator hàm này giúp check tính hợp lệ/ logic của output sau khi basemodel check xong kiểu dữ liệu
    @field_validator("answer")
    @classmethod
    def validate_answer_length(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("Câu trả lời từ LLM quá ngắn, không đảm bảo ngữ nghĩa y khoa.")
        return value.strip()