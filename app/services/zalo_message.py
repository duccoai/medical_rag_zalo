from app.schemas.medical import MedicalResponseSchema

FALLBACK_TEXT = "Hệ thống đang bận, bạn vui lòng thử lại sau ít phút."
HINT_TEXT = "Vui lòng nhập câu hỏi có ít nhất 2 ký tự và không quá 1000 ký tự."


def split_text(text: str, limit: int) -> list[str]:
    """Chia theo đoạn văn, rồi theo dòng, rồi theo ký tự khi một đoạn vẫn quá dài."""
    ...


def format_zalo_reply(result: MedicalResponseSchema, limit: int) -> list[str]:
    """Ghép answer, liều khuyến nghị, nguồn và disclaimer thành các tin <= limit ký tự.

    Thứ tự: answer -> recommended_dosage (nếu có) -> sources (nếu có) -> disclaimer.
    sources chỉ lấy từ result.sources đã được kiểm chứng.
    """
    ...
