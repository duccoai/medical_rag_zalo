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



(fix D-05:
Kiến thức bạn vừa nhớ ra chính là nội dung cốt lõi của môn Hệ quản trị Cơ sở dữ liệu (Database Management Systems - DBMS), cụ thể nằm ở chương Quản lý Giao dịch (Transaction Management) và Điều khiển Đồng thời (Concurrency Control).
Bản sửa lỗi RAG vừa rồi của bạn đã áp dụng trực tiếp 3 khái niệm kinh điển của môn học này:

1. Tính chất ACID (Đặc biệt là chữ A - Atomicity)

Trong môn Cơ sở dữ liệu, mỗi giao dịch (transaction) phải tuân thủ 4 nguyên tắc ACID:
• Atomicity (Tính nguyên tử): "All or Nothing" (Được ăn cả, ngã về không). Một chuỗi nhiều câu lệnh (như DELETE rồi INSERT) phải được coi là một đơn vị không thể chia cắt. Nếu lệnh sau lỗi, toàn bộ lệnh trước đó phải được hoàn tác (Rollback). Việc bạn gộp bước xóa và ghi vào chung một transaction chính là áp dụng tính chất này.
• Consistency (Tính nhất quán): Dữ liệu phải luôn chuyển từ trạng thái hợp lệ này sang trạng thái hợp lệ khác. Việc kiểm tra số lượng chunk khớp vector và từ chối chunk sai nguồn giúp giữ vững tính nhất quán này.

2. Kỹ thuật "Chuẩn bị trước, Ghi sau" (Write-Ahead / Prepare-then-Commit)

Về "thứ tự chạy" mà bạn mang máng nhớ, trong lý thuyết hệ thống và cơ sở dữ liệu có một nguyên tắc vàng: Không bao giờ giữ khóa (lock) hoặc mở transaction khi đang gọi tác vụ chậm bên ngoài (Network/API call).
• Luồng cũ vi phạm nguyên tắc này: Xóa DB trước rồi mới gọi API Embedding (tác vụ mạng rất chậm và dễ lỗi), khiến DB rơi vào trạng thái treo hoặc mất dữ liệu.
• Luồng mới tối ưu thứ tự: Tính toán xong toàn bộ trên RAM (gọi API Embedding) \(\rightarrow \) Mở transaction \(\rightarrow \) Ghi nhanh vào DB \(\rightarrow \) Đóng transaction. Cách làm này giúp thời gian khóa dữ liệu trên DB cực ngắn, tránh nghẽn cổ chai và an toàn tuyệt đối.

3. Điều khiển đồng thời (Concurrency Control & Isolation)

Nếu có hai người cùng chạy script nạp lại cùng một file PDF vào cùng một thời điểm:
• Nếu dùng 2 connection riêng lẻ như cũ, các câu lệnh xóa và ghi của hai luồng sẽ đan xen vào nhau (Interleaving), dẫn đến lỗi Dirty Read (đọc phải dữ liệu rác chưa hoàn tất) hoặc Lost Update (ghi đè mất dữ liệu của nhau).
• Khi gói gọn vào 1 transaction trên 1 connection, PostgreSQL sẽ tự động áp dụng cơ chế cô lập (Isolation), đảm bảo người dùng đang chat với AI sẽ không bao giờ bị hụt thông tin hoặc đọc nhầm dữ liệu đang cập nhật dở dang.)