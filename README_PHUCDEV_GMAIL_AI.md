# Phuc Dev AI 4.0 — Gmail Panel + AI Thầy CSKH

## Chức năng
- Màn hình chính là giao diện chat AI Phuc Dev; không còn danh sách khách/hội thoại CSKH giả.
- Ở trang chat chính, nhấn **F2** để mở Gmail Panel trong **tab/trang riêng** `/gmail`; panel không phủ lên chat chính. Nếu trình duyệt chặn tab mới, trang sẽ chuyển thẳng sang `/gmail`. Lần đầu ở tab panel nhập mật khẩu `1` (nếu Render đã đặt `ADMIN_PASS`, hãy đặt nó thành `1`). Nhấn **Esc** hoặc **Exit** để quay lại trang chat chính.
- Nhấn **F3** mở Cài đặt; **F4** mở Giao diện. Các nút điều khiển panel ở thanh bên được ẩn để giao diện gọn hơn.
- Trang `/gmail` mở workspace độc lập, mặc định vào **AI Thầy CSKH** để dễ thấy chức năng hướng dẫn. Các mục cũ vẫn đầy đủ: **Tra Gmail, Tra Bill, Thanh toán, Panel mail, Tra / Tạo TK**. Chuyển mục bằng cột bên trái của trang panel.
- AI Thầy có các vai trò: Thầy CSKH, Soạn câu trả lời, Khách mô phỏng để luyện tập, Trợ lý Gmail. Chọn mô hình trong ô Mô hình AI; các lời nhắn chỉ lưu cục bộ trong trình duyệt. AI không nhắn cho khách thật và không tự gửi phản hồi.

## Chạy cục bộ
```cmd
pip install -r requirements.txt
python server.py
```
Mở `http://127.0.0.1:8000/` để dùng chat AI. Nhấn **F2** để mở Gmail Panel trong tab riêng, hoặc truy cập trực tiếp `http://127.0.0.1:8000/gmail`.

## API và khóa
Server dùng các biến môi trường theo `server.py`, như `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `SAMBANOVA_API_KEY`, `COHERE_API_KEY`, `GITHUB_TOKEN`, `ADMIN_PASS`, `SESSION_SECRET`. Không đưa API key vào mã nguồn.

## Lưu ý dữ liệu
Dữ liệu Gmail, tài khoản nội bộ, bill và lịch sử AI trong panel đang được lưu trong `localStorage` trên trình duyệt này (`pd4_ws`), chưa đồng bộ sang máy khác. Đây không phải hệ thống đăng nhập Gmail thật; các mục tài khoản chỉ là bản ghi quản lý nội bộ. Không lưu mật khẩu Gmail thật, OTP hoặc mã khôi phục trong ứng dụng.

## Đóng gói/triển khai
Dự án được giữ theo cấu trúc tối giản phù hợp với cấu hình Render hiện tại. Đẩy các tệp trong `phuc_web/phuc-dev-main` lên đúng repository đang kết nối với Render. Sau khi deploy, truy cập website và dùng F2.
