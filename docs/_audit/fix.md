###
Fix đợt 1 (trước khi đến các phases cuối [Cleanup: Vá 6 điểm Audit] ──► [Phase 7: Redis Memory] ──► [Phase 8: Zalo OA Webhook] ──► [Phase 9: Docker & Eval])

- Đây là những lỗi trực tiếp ảnh hưởng đến độ tin cậy của dữ liệu, cấu hình và vòng đời kết nối khi bạn tích hợp Redis & Zalo:
- Đồng bộ cấu hình & bảo mật (config.py + docker-compose.yml): Bỏ mật khẩu DB mặc định trong code, đưa về .env và cho phép biến Zalo ở dạng None mặc định để app không bị crash khi chạy dev/test.
- Khóa cứng sources từ Metadata thật (rag_engine.py): Ghi đè ai_result.sources bằng metadata trích xuất từ pgvector thay vì để LLM tự sinh. Sang Phase 8 khi gửi tin nhắn ra Zalo OA, nguồn trích dẫn sai sẽ làm mất uy tín của bot y tế.
- Gắn lifespan đóng Pool DB (main.py): Đảm bảo close_db_pool() chạy khi tắt app, sẵn sàng để Phase 7 gắn thêm init_redis_pool() và close_redis_pool() vào cùng chỗ.
- Nạp tài liệu Atomic (ingest_pdfs.py): Bỏ lệnh DELETE đầu quy trình, dùng ON CONFLICT (chunk_key) DO UPDATE để tránh mất sạch dữ liệu cũ nếu API bị ngắt giữa chừng.
- Sửa encoding requirements.txt sang UTF-8 & xóa/sửa list_models.py: Tránh lỗi cú pháp và lỗi cài thư viện sau này.

###
Fix đợt 2:
Những mục này không cản trở việc viết code tính năng mới, thậm chí có mục bắt buộc phải đợi xong Phase 7–8 mới làm một thể cho gọn:

- ockerfile & docker-compose.yml hoàn chỉnh: Đợi tích hợp xong cả Redis (Phase 7) và Zalo Webhook (Phase 8) rồi đóng gói toàn bộ stack (app + postgres + redis) một lần duy nhất sẽ chuẩn xác hơn.
- Dọn code thừa (dead code) như nhánh trích dẫn số page không dùng tới: Đợi hệ thống chạy trọn vẹn rồi dọn một lượt cho sạch repo.
- Cập nhật lại bộ 8 file docs/: Làm ở bước cuối cùng sau khi mọi tính năng và technical debt đã chốt hạ, đảm bảo tài liệu phản ánh đúng 100% trạng thái "Completed" của đồ án trên GitHub.