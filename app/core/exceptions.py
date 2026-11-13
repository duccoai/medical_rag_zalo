from fastapi import Request
from fastapi.responses import JSONResponse


# Tạo class lỗi nghiệp vụ riêng để phân biệt với lỗi sập hệ thống (500)
# Cho phép chủ động ngắt luồng (raise) và tự chọn mã lỗi HTTP (400, 404...)
class AppBaseException(Exception):

  def __init__(self, message: str, status_code: int = 400):
    self.message = message
    self.status_code = status_code


# Bắt các lỗi nghiệp vụ do mình tự ném ra và ép về chung 1 format JSON cho Frontend dễ đọc
async def app_exception_handler(request: Request, exc: AppBaseException):
  return JSONResponse(
      status_code=exc.status_code,
      content={
          "success": False,
          "error_type": "BusinessError",
          "detail": exc.message,
      },
  )


# Bắt mọi lỗi code bất ngờ (chia cho 0, mất mạng...) để giấu vết lỗi (stack trace) và tránh sập server
async def unhandled_exception_handler(request: Request, exc: Exception):
  return JSONResponse(
      status_code=500,
      content={
          "success": False,
          "error_type": "InternalServerError",
          "detail": "Hệ thống đang gặp sự cố nội bộ, vui lòng thử lại sau.",
      },
  )
