from api.v1 import chat, zalo
from fastapi import APIRouter

api_router = APIRouter()

# Đăng ký nhánh /chat và /zalo vào /api/v1
api_router.include_router(chat.router)
api_router.include_router(zalo.router)
