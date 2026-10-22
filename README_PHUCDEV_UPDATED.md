# Phuc Dev AI 4.0 — cập nhật trang riêng

## Đường dẫn sau khi deploy lên Render
- Trang chat AI độc lập: `/ai` (không hiện form mã truy cập của ứng dụng).
- Trang Gmail độc lập: `/gmail` (mở thẳng giao diện Gmail Panel).
- Trang chính: `/`.

## Chạy local
```cmd
pip install -r requirements.txt
python server.py
```
Sau đó mở `http://127.0.0.1:8000/`, `/ai` hoặc `/gmail`.

## Mật khẩu panel
Mật khẩu mở Admin Panel trên giao diện là `1`. Nếu Render đang có biến môi trường `ADMIN_PASS` với giá trị cũ, hãy vào Render → service `phuc-dev` → Environment và đổi `ADMIN_PASS` thành `1`, rồi deploy/restart. Các thao tác GitHub vẫn cần `GITHUB_TOKEN` hợp lệ.

## AI không cần mã truy cập
Endpoint chat và danh sách model cho phép dùng mà không nhập `ACCESS_CODE`; các endpoint ESP32/tệp vẫn giữ kiểm tra quyền riêng. Để hạn chế tiêu thụ API ngoài ý muốn, chat công khai được giới hạn cơ bản 30 yêu cầu/IP trong 10 phút và body tối đa 150 KB.

**Cảnh báo:** Khi deploy trên một URL công khai, bất kỳ ai biết `/ai` đều có thể dùng hạn mức API của server. Giới hạn theo IP chỉ là bảo vệ cơ bản, không thay thế xác thực. Mật khẩu `1` rất yếu; không dùng cho GitHub token/quyền nhạy cảm trên website công khai. Hạn chế quyền của `GITHUB_TOKEN` và theo dõi usage của nhà cung cấp AI.

Gmail Panel tiếp tục lưu dữ liệu trong `localStorage` của trình duyệt (khóa `pd4_ws`), không phải database trên server. Dữ liệu dùng chung giữa `/` và `/gmail` trong cùng trình duyệt/hồ sơ. Không nên lưu mật khẩu Gmail thật vào ghi chú hoặc localStorage.


## Bản giao diện CSKH game
- Mở `/gmail` để vào giao diện **Phuc Support Desk** mới: tổng quan, hộp thư, hồ sơ khách hàng demo, mẫu trả lời và ghi chú ca trực.
- Giao diện dùng các kênh game minh họa (Game Arena, NovaPlay, Pixel World, Arcade Hub, Cloud Games, VPlay), không dùng logo hay nhận diện của nền tảng cá cược cụ thể.
- Không có chức năng tạo hóa đơn/bill hoặc nhập, lưu mật khẩu khách hàng. Các yêu cầu và hội thoại mẫu lưu trong localStorage với khóa `phuc_supportdesk_v1`, chỉ trên trình duyệt hiện tại; chưa có đồng bộ nhiều nhân viên/server database.
- Dữ liệu Gmail/bill cũ (nếu có) trong khóa localStorage `pd4_ws` có thể vẫn tồn tại trên trình duyệt, nhưng giao diện mới không hiển thị hay sử dụng nó. Xóa dữ liệu cũ chỉ khi đã chắc chắn không còn cần.
