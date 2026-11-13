from api.v1 import chat
from fastapi import APIRouter

api_router = APIRouter()

# Đăng ký nhánh /chat vào /api/v1
api_router.include_router(chat.router)

# Sau này làm tới Hạng mục 8 (Zalo OA) sẽ thêm:
# api_router.include_router(zalo.router)