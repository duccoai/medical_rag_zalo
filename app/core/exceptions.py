
from fastapi import Request
from fastapi.responses import JSONResponse


class AppBaseException(Exception):
    """Lỗi nghiệp vụ / hệ thống chuẩn hóa toàn dự án"""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        retryable: bool = False,
    ):
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


class TransientServiceException(AppBaseException):
    """Lỗi tạm thời từ dịch vụ ngoài (Rate Limit 429, 503, Timeout) - có thể retry"""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=503,
            retryable=True,
        )


async def app_exception_handler(request: Request, exc: AppBaseException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_type": "TransientError" if exc.retryable else "BusinessError",
            "retryable": exc.retryable,
            "detail": exc.message,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_type": "InternalServerError",
            "retryable": False,
            "detail": "Hệ thống đang gặp sự cố nội bộ, vui lòng thử lại sau.",
        },
    )
