# Các hàm chính (chữ ký, không phải mã hoàn chỉnh)
async def get_access_token() -> str:
    """Đọc token từ Redis. Nếu chưa có, bootstrap từ settings.ZALO_OA_ACCESS_TOKEN / REFRESH_TOKEN."""

async def refresh_access_token(stale_token: str) -> str:
    """Làm mới token có khóa Redis (SET NX). Nếu token trong Redis đã khác stale_token thì trả về luôn (đã có người làm mới)."""
