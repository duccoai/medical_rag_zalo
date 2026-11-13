import time
from api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import (
    AppBaseException,
    app_exception_handler,
    unhandled_exception_handler,
)
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API cho hệ thống Trợ lý Tư vấn Y tế & Thường thức Sức khỏe",
)

# 1. Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. Middleware tự động đo thời gian xử lý mỗi HTTP Request
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = round((time.time() - start_time) * 1000, 2)  # Tính theo ms
    response.headers["X-Process-Time-Ms"] = str(process_time)
    return response


# 3. Đăng ký Exception Handlers tập trung
app.add_exception_handler(AppBaseException, app_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


# 4. Endpoint kiểm tra sức khỏe server (Health Check)
@app.get("/health", tags=["System"], summary="Kiểm tra trạng thái hoạt động")
async def health_check():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


# 5. Gắn toàn bộ nhánh API v1
app.include_router(api_router, prefix="/api/v1")