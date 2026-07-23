# Google Meet — 2026-07-23

**Languages:** Vietnamese (confirmed before joining)

**Attendees:** Tung Dao, Nguyen Vinh (2 segments labeled generically "Speaker" — unresolved diarization, not a third participant)

## Key points
- **Tung Dao đang xây dựng một skill tích hợp Jira: hỗ trợ log, tạo epic, tạo task, và update thông tin task.**
- **Skill sẽ được gọi qua Slack (hoặc kênh khác) — mỗi lần gọi, hệ thống nhận diện người gọi và quyền hạn tương ứng.**
- **Phân quyền (permission) được cấu hình ở "Open Clawe", theo hướng đã thống nhất từ trước (nhắc tới "XK4"/Epic 4).**
- **Cần phân biệt quyền giữa PM và các user/dev thông thường khi một dự án có nhiều thành viên.**
- **Có kế hoạch xây một bot chạy hàng ngày (khoảng 5 giờ) hỏi tiến độ từng thành viên, tổng hợp vào log/sheet, rồi tạo đánh giá tiến độ dự án (đúng tiến độ/chậm/nhanh).**
- **Đề xuất dùng email để định danh người dùng thay vì cách khác.**
- **Có nhắc tới việc lấy dữ liệu từ wiki của "anh Đô" và ý tưởng train AI để đánh giá rủi ro/tiến độ dự án dựa trên dữ liệu hiện có.**
- **Có nhắc tới "skill log time" — tự động ghi nhận thời gian làm việc của từng thành viên, không cần viết tay.**

## Decisions
- Phân quyền skill Jira được xử lý trong Open Clawe / theo hướng đã đề cập trước đó (XK4).
- Tách luồng công việc: một người phụ trách hỏi/thu thập thông tin tiến độ từ mọi người, một người (nhắc tên "Long") phụ trách tổng hợp báo cáo/đánh giá rủi ro.
- Dùng email để phân biệt người dùng, theo đề xuất của Nguyen Vinh, Tung Dao đồng ý.

## Action items
- [ ] <span style="color:green">Nguyen Vinh — hoàn thiện cấu hình permission cho skill Jira trên Open Clawe/XK4</span>
- [ ] <span style="color:green">Tung Dao — tiếp tục phát triển skill log/epic/task và cơ chế nhận diện quyền theo người gọi</span>
- [ ] <span style="color:green">(chưa rõ owner cụ thể) — xây bot hỏi tiến độ hàng ngày lúc 5 giờ, tổng hợp log vào sheet, tạo đánh giá tiến độ/rủi ro dự án (liên quan đến "Long")</span>
- [ ] <span style="color:green">(chưa rõ owner cụ thể) — xây "skill log time" tự động ghi nhận thời gian làm việc của từng thành viên</span>

_Lưu ý: bản ghi âm khá rời rạc (nhiều đoạn song song do 2 channel ghi đè lên nhau, câu ngắn/đứt quãng), nên một số chi tiết cụ thể (tên riêng như "anh Đô", "Long", "Phong", các con số ngày tháng) có thể không hoàn toàn chính xác — nên đối chiếu full transcript bên dưới khi cần độ chính xác cao. Đã sửa thủ công 2 lỗi ASR nghe nhầm được người dự họp xác nhận: "lock time" → "log time", và "Tạo tab" → "Tạo task" (08:06:52)._

## Full transcript (từ get_transcript, đã lọc nhiễu)

[08:01:08 - 08:01:14 UTC] Tung Dao (vi):
Anh dùng âm thanh của cái ơ cao của anh, đúng không, Vinh? Đúng.

[08:01:15 - 08:01:19 UTC] Tung Dao (vi):
Tên người sống luôn là anh đúng không? Ừ. Nhưng.

[08:01:20 - 08:01:22 UTC] Nguyen Vinh (vi):
Nhưng mà vừa nói là hơi nhỏ.

[08:01:24 - 08:01:24 UTC] Tung Dao (vi):
Ừm, nói hơi nhỏ.

[08:01:27 - 08:01:57 UTC] Tung Dao (vi):
Như hiện tại nhé, thì anh đang trên, đã trên Ninh Skill của cái thằng, các cái thao tác liên quan đến Jira. Ví dụ như là log, epic, log task, và update các cái thông tin liên quan đến task.

[08:01:59 - 08:04:11 UTC] Tung Dao (vi):
Thằng này nó sẽ được tích hợp vào Slack hay tích hợp vào đâu đó ấy, thì mỗi với mỗi một lần mà được gọi ra thì nó sẽ biết được là ai đang gọi nó, và có cái quyền gì. Ví dụ như một ông Pierre.

[08:02:11 - 08:02:13 UTC] Tung Dao (vi):
Những bộ lọc.

[08:02:58 - 08:02:59 UTC] Tung Dao (vi):
Tin tức.

[08:04:13 - 08:04:16 UTC] Tung Dao (vi):
Hay là sao ta?

[08:04:16 - 08:04:39 UTC] Nguyen Vinh (vi):
Ờ, ừ, cái này thì mình sẽ xử lý cái đấy ở trong XK4, nhưng hôm trước—

[08:04:41 - 08:04:45 UTC] Nguyen Vinh (vi):
Và nó sẽ được config cái permission đấy ở trên cái Open Clawe.

[08:04:42 - 08:04:45 UTC] Nguyen Vinh (vi):
D ạ.

[08:04:45 - 08:04:48 UTC] Tung Dao (vi):
Không vấn đề nhé.

[08:04:47 - 08:04:48 UTC] Tung Dao (vi):
Còn được.

[08:04:49 - 08:05:02 UTC] Nguyen Vinh (vi):
Vâng .

[08:04:49 - 08:04:59 UTC] Nguyen Vinh (vi):
Đấy, ừm, đấy, đấy là việc mình gọi skill nhé. Nhưng mà còn về phần quyền ở trong dự án ấy.

[08:05:02 - 08:05:04 UTC] Tung Dao (vi):
Good này nha. Có nghĩa là.

[08:05:04 - 08:05:11 UTC] Nguyen Vinh (vi):
Có nghĩa là cái skill Jira của anh chẳng hạn.

[08:05:04 - 08:05:09 UTC] Nguyen Vinh (vi):
Thì ông bà có quyền.

[08:05:12 - 08:05:13 UTC] Tung Dao (vi):
Ông Đặng.

[08:05:12 - 08:05:13 UTC] Nguyen Vinh (vi):
Ông nào có vlog?

[08:05:14 - 08:05:24 UTC] Nguyen Vinh (vi):
Cam thì bọn anh phải xử lý ở trong cái skill của bọn anh rồi.

[08:05:25 - 08:05:42 UTC] Tung Dao (vi):
Ừ. Thế thì, thế thì để mà có những cái thông tin đấy thì chắc chắn là thằng agent ấy nó.

[08:05:26 - 08:05:27 UTC] Tung Dao (vi):
Ông nào run thế cơ?

[08:05:29 - 08:05:32 UTC] Tung Dao (vi):
Để chắc chắn

[08:05:40 - 08:05:42 UTC] Tung Dao (vi):
Đúng rồi. Thì cái này nó.

[08:05:42 - 08:05:43 UTC] Tung Dao (vi):
Tuy nhiên.

[08:05:42 - 08:05:43 UTC] Tung Dao (vi):
Em nghe.

[08:05:43 - 08:05:45 UTC] Nguyen Vinh (vi):
Sẽ liên quan đến cái phần của anh Đô.

[08:05:46 - 08:05:47 UTC] Tung Dao (vi):
Là mình.

[08:05:47 - 08:05:55 UTC] Nguyen Vinh (vi):
Ờ, cũng thấy vui lắm. Nó sẽ chứa ông nào có gì .

[08:05:47 - 08:05:52 UTC] Nguyen Vinh (vi):
Nhưng cũng.

[08:05:56 - 08:05:57 UTC] Tung Dao (vi):
Ông nào.

[08:05:59 - 08:05:59 UTC] Tung Dao (vi):
Ông bà.

[08:05:59 - 08:06:02 UTC] Nguyen Vinh (vi):
Ông nào có roll deck, ông nào roll tester?

[08:06:02 - 08:06:04 UTC] Nguyen Vinh (vi):
Hỏi em.

[08:06:02 - 08:06:09 UTC] Nguyen Vinh (vi):
Cái con AI nó sẽ biết.

[08:06:06 - 08:06:09 UTC] Nguyen Vinh (vi):
In bên nông. Anh cảm giác là nó vẫn ở trong cái—

[08:06:10 - 08:06:11 UTC] Tung Dao (vi):
Phân quyền.

[08:06:10 - 08:06:11 UTC] Tung Dao (vi):
Vàng, đúng rồi.

[08:06:11 - 08:06:11 UTC] Nguyen Vinh (vi):
Mình sẽ.

[08:06:12 - 08:06:13 UTC] Tung Dao (vi):
Đúng rồi.

[08:06:12 - 08:06:13 UTC] Tung Dao (vi):
Đúng rồi, thì.

[08:06:13 - 08:06:14 UTC] Nguyen Vinh (vi):
Việt Nam.

[08:06:13 - 08:06:13 UTC] Nguyen Vinh (vi):
Ý nó là.

[08:06:14 - 08:06:14 UTC] Tung Dao (vi):
Có được tiền.

[08:06:14 - 08:06:14 UTC] Tung Dao (vi):
Có được cái.

[08:06:14 - 08:06:18 UTC] Nguyen Vinh (vi):
Chính sách kinh tế rồi thì.

[08:06:14 - 08:06:18 UTC] Nguyen Vinh (vi):
Tranh sát user rồi thì lúc ấy mình có thể phân quyền được nó trên.

[08:06:18 - 08:06:22 UTC] Tung Dao (vi):
Ví dụ một ông bừa nào đấy, ví dụ ông member bừa nào đấy, ông ấy gọi.

[08:06:22 - 08:06:28 UTC] Tung Dao (vi):
Để mẹ con, ờ...

[08:06:27 - 08:06:28 UTC] Tung Dao (vi):
Thì nó sẽ.

[08:06:28 - 08:06:31 UTC] Tung Dao (vi):
Và nó sẽ báo là không có quyền hay gì đấy chẳng hạn.

[08:06:31 - 08:06:32 UTC] Tung Dao (vi):
Nhật Bản.

[08:06:32 - 08:06:35 UTC] Nguyen Vinh (vi):
Việc đấy mình sẽ làm theo Inkscape 4, nhưng hôm trước mình đề cập rồi.

[08:06:35 - 08:06:44 UTC] Tung Dao (vi):
Như hiện tại nhà cắt skill mọi người sẽ.

[08:06:43 - 08:06:47 UTC] Nguyen Vinh (vi):
Thì tất nhiên là mọi người sẽ đang training nó theo dạng là—

[08:06:44 - 08:06:47 UTC] Nguyen Vinh (vi):
Còn xin anh.

[08:06:47 - 08:06:50 UTC] Tung Dao (vi):
Em đang làm một video về.

[08:06:47 - 08:06:50 UTC] Tung Dao (vi):
Anh đang làm một user rồi, à, một ki—

[08:06:50 - 08:06:52 UTC] Nguyen Vinh (vi):
Như vậy là có phương tiện.

[08:06:50 - 08:06:52 UTC] Nguyen Vinh (vi):
Rồi, của anh đang có full quyền.

[08:06:52 - 08:07:12 UTC] Tung Dao (vi):
Ờ, bởi vì cái skill của anh chỉ dành cho việc là tạo tác, hay là— Hiện tại thì những cái thông tin liên quan đến—

[08:06:52 - 08:06:57 UTC] Tung Dao (vi):
Bởi vì cái skill của anh nó chỉ dành cho việc là... Tạo task, hay là agile cho ai đấy thôi.

[08:06:59 - 08:06:59 UTC] Tung Dao (vi):
Địa phận.

[08:07:04 - 08:07:06 UTC] Tung Dao (vi):
Vâng .

[08:07:13 - 08:07:21 UTC] Tung Dao (vi):
Nó sẽ trỏ đến cái—

[08:07:15 - 08:07:16 UTC] Tung Dao (vi):
Khánh Linh.

[08:07:21 - 08:07:32 UTC] Tung Dao (vi):
Và anh cũng sẽ phải nghĩ.

[08:07:32 - 08:07:42 UTC] Tung Dao (vi):
Thì có thể đâu đó thì những cái thông tin đấy.

[08:07:38 - 08:07:39 UTC] Tung Dao (vi):
Để bảo vệ.

[08:07:42 - 08:07:49 UTC] Nguyen Vinh (vi):
Mà anh em bây giờ anh em.

[08:07:49 - 08:07:50 UTC] Tung Dao (vi):
Còn khi mà.

[08:07:50 - 08:07:53 UTC] Nguyen Vinh (vi):
Ừm, để tài khoản nhiều dự án thì—

[08:07:50 - 08:07:53 UTC] Nguyen Vinh (vi):
Ừm, đến cái bài toán mà nhiều dự án thì—

[08:07:53 - 08:07:54 UTC] Tung Dao (vi):
Mình bắt buộc.

[08:07:53 - 08:07:54 UTC] Tung Dao (vi):
Đắc Ngộ.

[08:07:54 - 08:07:58 UTC] Nguyen Vinh (vi):
Mình muốn đi sâu vào cái quy luật—

[08:07:54 - 08:07:58 UTC] Nguyen Vinh (vi):
Cái xử lý đi sâu vào cái vector DB rồi.

[08:07:59 - 08:08:00 UTC] Tung Dao (vi):
Cốt nhân.

[08:08:00 - 08:08:02 UTC] Nguyen Vinh (vi):
Thì anh chị cần làm trong một dự án như thế nào?

[08:08:00 - 08:08:06 UTC] Nguyen Vinh (vi):
Thì anh em cứ làm trong một dự án đi.

[08:08:02 - 08:08:04 UTC] Tung Dao (vi):
Chúng em trong.

[08:08:04 - 08:08:07 UTC] Nguyen Vinh (vi):
Là tất nhiên không được trả lời.

[08:08:07 - 08:08:11 UTC] Nguyen Vinh (vi):
Phật quyền.

[08:08:07 - 08:08:11 UTC] Nguyen Vinh (vi):
Phải cần cái phân quyền của PM và các user bình thường, dev đơn giản.

[08:08:11 - 08:08:21 UTC] Tung Dao (vi):
Mặc dù thì mình bảo là đây là—

[08:08:20 - 08:08:23 UTC] Nguyen Vinh (vi):
Đúng rồi, MDF chỉ lốp bậc thang thôi.

[08:08:21 - 08:08:24 UTC] Nguyen Vinh (vi):
Chị Lộc Hàm.

[08:08:24 - 08:08:30 UTC] Tung Dao (vi):
Ví dụ như là lốc tát, hay là app.

[08:08:24 - 08:08:25 UTC] Tung Dao (vi):
Có nghĩa là.

[08:08:29 - 08:08:30 UTC] Tung Dao (vi):
Tôi biết.

[08:08:30 - 08:08:35 UTC] Nguyen Vinh (vi):
Chuẩn. Hôm nay anh được gì ?

[08:08:30 - 08:08:35 UTC] Nguyen Vinh (vi):
Nút chuẩn từ con AI rồi thì gần như là DEX sẽ không phải động đến cái phần log.

[08:08:35 - 08:08:54 UTC] Tung Dao (vi):
Như anh, anh, anh, anh bảo con, con agent ấy, thông qua cloud ấy, thì—

[08:08:36 - 08:08:37 UTC] Tung Dao (vi):
Không biết nữa.

[08:08:47 - 08:08:49 UTC] Tung Dao (vi):
Tạm biệt.

[08:08:54 - 08:08:56 UTC] Nguyen Vinh (vi):
Khá lâu dài rồi. Có.

[08:08:54 - 08:08:56 UTC] Nguyen Vinh (vi):
Rồi, và ơ dai được người cho anh luôn.

[08:08:56 - 08:09:06 UTC] Tung Dao (vi):
Nếu mà mình có.

[08:08:59 - 08:09:00 UTC] Tung Dao (vi):
Điện tử.

[08:09:01 - 08:09:03 UTC] Tung Dao (vi):
Nó xuất hiện.

[08:09:06 - 08:09:08 UTC] Nguyen Vinh (vi):
Em nghĩ là nên dùng theo email thì hợp lý hơn.

[08:09:08 - 08:09:12 UTC] Tung Dao (vi):
Cái đấy thì anh nghĩ tùy mình. Anh nghĩ nó, nó cũng sẽ tự biết ấy.

[08:09:12 - 08:09:14 UTC] Nguyen Vinh (vi):
Và sau này mình sẽ thay đổi cho slide này.

[08:09:12 - 08:09:14 UTC] Nguyen Vinh (vi):
Ừm, sau này mình sẽ tích hợp trên Slack mà.

[08:09:14 - 08:09:16 UTC] Tung Dao (vi):
Đây, bài toán này xong MVP rồi.

[08:09:16 - 08:09:20 UTC] Tung Dao (vi):
Ừ, thì tối nay em có việc làm email.

[08:09:17 - 08:09:20 UTC] Tung Dao (vi):
Thì số lách anh phân biệt bằng ý.

[08:09:20 - 08:09:22 UTC] Nguyen Vinh (vi):
Đơn giản hơn anh ơi.

[08:09:20 - 08:09:22 UTC] Nguyen Vinh (vi):
Nó sẽ đơn giản hơn là isolated.

[08:09:22 - 08:09:36 UTC] Tung Dao (vi):
Ừm, nhưng hiện tại thì skill thì hiện tại thì nó vẫn cần phải thêm những cái yếu tố.

[08:09:35 - 08:09:36 UTC] Tung Dao (vi):
Còn cái cây của—

[08:09:36 - 08:09:40 UTC] Nguyen Vinh (vi):
Chúng ta kể cả sự nặng gây là lúc ham cũng được.

[08:09:36 - 08:09:43 UTC] Nguyen Vinh (vi):
Sơn là cái làm, à, sơn làm cái—

[08:09:40 - 08:09:40 UTC] Tung Dao (vi):
Chị cần.

[08:09:40 - 08:09:43 UTC] Nguyen Vinh (vi):
Em chỉ muốn chào ông Nghiêm.

[08:09:43 - 08:09:44 UTC] Tung Dao (vi):
Những gọi là product.

[08:09:44 - 08:09:44 UTC] Tung Dao (vi):
Walt Disney.

[08:09:46 - 08:09:49 UTC] Nguyen Vinh (vi):
Nhắc nhở mọi người lúc 20 cũng được đấy, con Boss.

[08:09:46 - 08:09:51 UTC] Nguyen Vinh (vi):
Nhắc nhở mọi người lúc xem đi thì lúc đấy.

[08:09:49 - 08:09:54 UTC] Tung Dao (vi):
Nó sẽ nhắn tin cho từng người. Ừm, tại vì nhiều.

[08:09:52 - 08:09:54 UTC] Tung Dao (vi):
Và lúc thêm cho ta.

[08:09:54 - 08:09:58 UTC] Tung Dao (vi):
Thì từ cái trang mà bếp đấy, nó nhắn.

[08:09:54 - 08:09:58 UTC] Tung Dao (vi):
Thì từ cái time mà thằng dev đấy nó nhắn.

[08:09:58 - 08:10:00 UTC] Tung Dao (vi):
Con bóc lại hết thì con bóc.

[08:09:58 - 08:10:03 UTC] Tung Dao (vi):
Cho con mốc đấy thì con boss sẽ tổng hợp dữ liệu bằng logfile lên cái—

[08:10:00 - 08:10:04 UTC] Nguyen Vinh (vi):
dụ .

[08:10:03 - 08:10:04 UTC] Nguyen Vinh (vi):
Schedule của mình.

[08:10:04 - 08:11:23 UTC] Tung Dao (vi):
Ờ, thế là sơ sẽ làm được phần áp chủa đây này. Ừm, sơn như hôm trước thì anh có— Của em là em chỉ lốp phần PM thôi mà, với lại như này, tại vì— Không, cái— Cũng không hẳn là mình tập trung vào PM. À, tức là em chỉ—

[08:10:30 - 08:10:35 UTC] Tung Dao (vi):
Cả hai bạn bây giờ chọn vào đây. Vậy để làm gì?

[08:11:25 - 08:11:26 UTC] Nguyen Vinh (vi):
Việt Cường.

[08:11:25 - 08:11:26 UTC] Nguyen Vinh (vi):
Cái phần rủi ro, anh ạ.

[08:11:26 - 08:11:28 UTC] Tung Dao (vi):
Vâng. Ờ, lọc.

[08:11:28 - 08:11:29 UTC] Nguyen Vinh (vi):
Mới to nên.

[08:11:29 - 08:12:25 UTC] Tung Dao (vi):
Có thì aomen cũng ngồi nghiên cứu thử, em cũng nối thử cái bộ tủ đo và cái select 841, xong rồi là có tạo một cái con bot kiểu hàng ngày 5 giờ nó sẽ hỏi từng người.

[08:12:27 - 08:12:36 UTC] Tung Dao (vi):
Trong hoàn thành, trong sprint này không?

[08:12:35 - 08:12:36 UTC] Tung Dao (vi):
Dạ được.

[08:12:37 - 08:13:13 UTC] Tung Dao (vi):
Thế thì em đang hiểu là Sơn sẽ là làm cái phần mà để hỏi mọi người, sau đó mọi người chat lên thì em sẽ là làm cái phần thông tin nói điều thông tin. Sau khi em nhận thông tin xong thì kết quả sẽ là Long. Em hoặc là PM.

[08:13:11 - 08:13:11 UTC] Tung Dao (vi):
Chính xác.

[08:13:14 - 08:13:22 UTC] Tung Dao (vi):
Là cái tiến độ, hoặc là—

[08:13:23 - 08:13:31 UTC] Tung Dao (vi):
Gửi lên báo cáo, thì lúc đấy Long—

[08:13:28 - 08:13:30 UTC] Tung Dao (vi):
Đúng rồi.

[08:13:30 - 08:13:37 UTC] Nguyen Vinh (vi):
Ừm, bây giờ anh em đang bị tách ra nên là chưa hình dung được bài toán đâu. Thì có nghĩa là bây giờ, khi mà—

[08:13:32 - 08:13:36 UTC] Nguyen Vinh (vi):
Anh em đang tìm hiểu cách đăng ký nhận lương và—

[08:13:36 - 08:13:37 UTC] Tung Dao (vi):
Thì có nghĩa là.

[08:13:38 - 08:13:38 UTC] Tung Dao (vi):
Tất cả.

[08:13:38 - 08:13:41 UTC] Nguyen Vinh (vi):
Cái skill.

[08:13:38 - 08:13:41 UTC] Nguyen Vinh (vi):
Những cái skill của mình đã hoàn thành rồi.

[08:13:42 - 08:13:42 UTC] Nguyen Vinh (vi):
Sẽ lấy.

[08:13:43 - 08:13:44 UTC] Tung Dao (vi):
Dữ liệu.

[08:13:43 - 08:13:44 UTC] Tung Dao (vi):
Ừm, dữ liệu.

[08:13:43 - 08:13:47 UTC] Nguyen Vinh (vi):
Những cái file ở trong con wiki của anh Đô này.

[08:13:44 - 08:13:50 UTC] Nguyen Vinh (vi):
Sẽ bay ở trong con.

[08:13:48 - 08:13:50 UTC] Speaker (vi):
Nhưng lúc ý thì cái file scaler của anh—

[08:13:50 - 08:13:58 UTC] Tung Dao (vi):
Ừ, thì nó cũng sẽ xem.

[08:13:51 - 08:13:53 UTC] Speaker (vi):
Thì hàng long nó sẽ xem được.

[08:13:53 - 08:13:56 UTC] Tung Dao (vi):
Thì từ đấy nó sẽ tạo ra một cái đánh giá rủi ro.

[08:13:57 - 08:14:02 UTC] Nguyen Vinh (vi):
Thì, ờ, lúc đấy nó—

[08:13:58 - 08:14:02 UTC] Nguyen Vinh (vi):
Lúc đấy họ cũng kế hoạch là họ sẽ hoàn thành.

[08:14:02 - 08:14:04 UTC] Tung Dao (vi):
Đúng rồi. Còn bây giờ—

[08:14:03 - 08:14:04 UTC] Tung Dao (vi):
Còn bây giờ—

[08:14:04 - 08:14:07 UTC] Nguyen Vinh (vi):
Đang rơi rạc.

[08:14:04 - 08:14:07 UTC] Nguyen Vinh (vi):
Em đang làm background nên là chưa, chưa hình dung.

[08:14:07 - 08:14:39 UTC] Tung Dao (vi):
Ví dụ như của Long ấy, thì Long sẽ dựa vào những cái thông số đang có của Swing đấy, của dự án đấy, thì con AI nó sẽ phải— Mình sẽ phải train cho nó cách để đánh giá như thế nào, nó—

[08:14:15 - 08:14:18 UTC] Tung Dao (vi):
Của một cái hành trình.

[08:14:40 - 08:14:41 UTC] Nguyen Vinh (vi):
Đúng rồi.

[08:14:40 - 08:14:41 UTC] Nguyen Vinh (vi):
Bây giờ hiện tại của Long mà.

[08:14:42 - 08:14:49 UTC] Nguyen Vinh (vi):
Ngày 09.

[08:14:42 - 08:14:48 UTC] Nguyen Vinh (vi):
Một cái file ship, ờm, schedule như kiểu hôm trước anh Phong anh làm ấy, thì nó có đánh giá được là—

[08:14:49 - 08:14:50 UTC] Tung Dao (vi):
Có đang chuẩn bị.

[08:14:49 - 08:14:50 UTC] Tung Dao (vi):
Có đang chậm hay là đang—

[08:14:51 - 08:15:01 UTC] Tung Dao (vi):
Chính hiện tại thì em chưa làm được.

[08:14:52 - 08:14:53 UTC] Tung Dao (vi):
Hiện tại.

[08:14:56 - 08:15:00 UTC] Tung Dao (vi):
Thế hiện tại là em đang.

[08:15:01 - 08:15:04 UTC] Nguyen Vinh (vi):
D ạ.

[08:15:01 - 08:15:04 UTC] Nguyen Vinh (vi):
Trong phần hàng ngày 5 giờ.

[08:15:04 - 08:15:09 UTC] Tung Dao (vi):
Micro ai mở? Em làm hay là mình sẽ tách ra một file riêng để nó ngồi riêng? Trong file mở đi.

[08:15:09 - 08:15:11 UTC] Nguyen Vinh (vi):
Nó to, nó xuống từng ngày.

[08:15:10 - 08:15:11 UTC] Nguyen Vinh (vi):
Rồi to lên bởi vì anh đang—

[08:15:11 - 08:15:11 UTC] Tung Dao (vi):
Mình sẽ miêu tả, xong nó sẽ, nó sẽ... nó sẽ tóm gọn toàn bộ.

[08:15:11 - 08:15:13 UTC] Tung Dao (vi):
Dùng con mít.

[08:15:11 - 08:15:14 UTC] Tung Dao (vi):
Mình sẽ miêu tả, xong nó sẽ, nó sẽ...

[08:15:19 - 08:15:21 UTC] Tung Dao (vi):
Đời con.

[08:15:25 - 08:15:26 UTC] Tung Dao (vi):
Dạ. Ừ.

[08:15:32 - 08:15:33 UTC] Tung Dao (vi):
Cái này á.

[08:15:34 - 08:15:49 UTC] Tung Dao (vi):
Ờ, em sẽ hiểu là công việc của em là sẽ được nhận.

[08:15:52 - 08:15:55 UTC] Tung Dao (vi):
Anh em trong team lúc tham đi thì con của em—

[08:15:52 - 08:15:56 UTC] Tung Dao (vi):
Mình sẽ tập trung kiểu như vậy vào những cái thao tác như update.

[08:15:56 - 08:15:57 UTC] Nguyen Vinh (vi):
Họ biết một thông tin rồi.

[08:15:56 - 08:15:57 UTC] Nguyen Vinh (vi):
Sẽ USD.

[08:15:57 - 08:15:59 UTC] Tung Dao (vi):
Từng có một ở trong tim.

[08:15:57 - 08:15:59 UTC] Tung Dao (vi):
Từng ông 1 ở trong team.

[08:16:00 - 08:16:02 UTC] Tung Dao (vi):
Rồi, tách logic ra.

[08:16:00 - 08:16:02 UTC] Tung Dao (vi):
Là hỏi người ta xem.

[08:16:03 - 08:16:07 UTC] Tung Dao (vi):
Bảo người ta log time đi, log time cho em, thì lúc đấy người ta sẽ cho em cái—

[08:16:03 - 08:16:08 UTC] Tung Dao (vi):
Cái này mình không phải viết ý, nhưng cái này mình không phải viết. Nó sẽ viết cho mình.

[08:16:08 - 08:16:10 UTC] Nguyen Vinh (vi):
Để bác sĩ tổng hợp cho mình, và mình—

[08:16:08 - 08:16:10 UTC] Nguyen Vinh (vi):
Cái cái đoạn text nó cao như lúc sáng anh bảo.

[08:16:10 - 08:16:16 UTC] Tung Dao (vi):
Tìm thì nếu còn vấn đề gì không, qua các nhiều lần bài test.

[08:16:11 - 08:16:17 UTC] Tung Dao (vi):
Cái lúc ấy em từ cái đấy thì em sẽ log lên cái file sheet kia, đúng không? Khi mà—

[08:16:16 - 08:16:17 UTC] Tung Dao (vi):
Em ước sau.

[08:16:17 - 08:16:18 UTC] Nguyen Vinh (vi):
Em lớp xong rồi.

[08:16:18 - 08:16:34 UTC] Tung Dao (vi):
Còn kiếm một cái, tức là mình sẽ thêm, mình sẽ bắt chước cái thằng, mình sẽ tạo một cái blocking riêng, hay là mình sẽ—

[08:16:18 - 08:16:28 UTC] Tung Dao (vi):
Thì, ừm, đấy là xong con skill log time.

[08:16:29 - 08:16:34 UTC] Tung Dao (vi):
Để nó đánh giá được cái tiến độ của dự án trong sprint đang được hoàn thành.

[08:16:35 - 08:16:38 UTC] Tung Dao (vi):
Chậm hay là nhanh, hay là vẫn đang đúng tiến độ?

[08:16:35 - 08:17:05 UTC] Tung Dao (vi):
Hỗ trợ, tức là toàn bộ những cái này nó cũng sinh ra cho mình. Vâng, nhưng mà ý em là cái dự án của mình thì mình có dùng được blocking market không, hay là— Như hiện tại là anh có, có dùng. Nhưng mà thực tế thì khó lắm, tại vì nếu em— em nghĩ là, em hiểu.

[08:17:05 - 08:17:39 UTC] Tung Dao (vi):
Chuẩn. Công viên xây dựng, đấy, thì anh sẽ sử dụng cái bộ flow này. Để anh xây dựng ra cái phân tích từ skill như này, em hiểu là mình sẽ lấy cái chuẩn về market, nhưng mà ý em là sau này cái skill của anh em mình ấy.
