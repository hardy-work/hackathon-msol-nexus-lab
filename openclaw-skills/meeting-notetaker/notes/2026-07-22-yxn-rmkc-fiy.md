# Google Meet — 2026-07-22

**Attendees:** Toan Cap Khanh, Viethoang Mai, Vi Duong, Hung Nguyen, Tung Dao, Hang Pham, Thuan Pham

## Key points
- Rà soát các feedback/bug từ phía Android — 4 mục ghi nhận "delete trong tháng 8", trong đó có 1 tác vụ đang xử lý hotfix (mã nhắc tới không rõ ràng trong transcript: "863 hay là 96").
- Bên QA (Hằng) không đủ nhân lực để test thêm các tác vụ này, nên các tác vụ đó sẽ được đẩy lên staging để bên dev/Figma tự test trước khi đóng.
- Thảo luận kỹ về logic "exit" quyền chỉnh sửa (admin/home) đối với một event có category đã ở trạng thái "Ended": exit chỉ được phép khi category đó (và các category con) chưa được đẩy/cập nhật lên cấp trên (HR).
- Chốt: nếu event chỉ có quyền admin (không có quyền home) và không có category con nào chưa cập nhật, thì được phép exit; ngược lại thì bị chặn.
- Giới hạn số ký tự cho tên file cần được đặt ra (đề xuất khoảng 20–50 ký tự), và cần kiểm tra việc tên file có chứa dấu chấm (.) có hợp lệ không.
- Task về "2 user không thể xoá cùng lúc" — Hoàng và Thuận chia nhau viết test case.
- Một task liên quan nút Cancel sẽ được đổi tên (tên chính xác không rõ do ASR nhiễu).
- Có một task (mã ~79928) trước đó dự định dời sang tháng 8 nhưng được quyết định vẫn giữ trong đợt hotfix hiện tại.

_Đã áp dụng bước lọc nhiễu (skill step 5) qua subagent: 310 segment thô → 225 giữ lại, 85 bị loại (canned outro "cảm ơn các bạn đã theo dõi / subscribe kênh lalaschool" và các câu ngoại ngữ ngắn lạc lõng: Nhật, Thái, Hàn, Hà Lan, Mã Lai, Nga, Đức, Tây Ban Nha, Trung...). Một số thuật ngữ kỹ thuật (button, popup, setting, form...) bị ASR phiên âm sai thành từ tiếng Việt gần âm ("bút tường" = button, "bốp áp"/"bộ app" = popup, "xét tinh"/"xét tình" = setting, "phơm" = form) — đã cố gắng suy luận ý nghĩa khi tóm tắt nhưng có thể không chính xác 100%, nên đối chiếu full transcript bên dưới khi cần độ chính xác cao. Mã số task (79928, 863/96) cũng có thể bị nhiễu, cần xác minh lại._

## Decisions
- Đẩy các bug/feedback Android không liên quan QA sang staging để dev/Figma tự test, thay vì chờ QA.
- Giữ nguyên logic: category đã "Ended" chỉ exit được nếu chưa có category con nào được cập nhật lên cấp trên.
- Sẽ giới hạn ký tự cho tên file (con số cụ thể chưa chốt).
- Task ~79928 giữ trong hotfix hiện tại, không dời sang tháng 8.

## Action items
- [ ] Hung Nguyen — xử lý bổ sung logic exit-permission (admin/home) theo mô tả trong cuộc họp
- [ ] Thuan Pham — kiểm tra giới hạn ký tự & dấu chấm trong tên file
- [ ] Hoang, Thuan Pham — chia nhau viết test case cho task "2 user không thể xoá cùng lúc"
- [ ] Tung Dao — xử lý phần được nhắc tới là "phiếu trợ 17" (chưa rõ chi tiết do transcript nhiễu)
- [ ] Hang Pham — xác nhận lại lý do/trạng thái task hotfix liên quan "Elan" với bên liên quan

## Full transcript (từ get_transcript, đã lọc nhiễu)

**[02:15:29 - 02:15:35] Toan Cap Khanh (vi):**
trước rồi nên là chỗ đoạn này anh nghĩ là phía bác em sẽ sửa lại là xong thôi Hoàng ạ còn lại

**[02:15:35 - 02:15:42] Toan Cap Khanh (vi):**
phía FBA thì là xóa cái xử lý là thêm một cái tab mới và mình thêm cái xử lý cho hiển thị của bác này là xong

**[02:15:52 - 02:15:59] Toan Cap Khanh (vi):**
Thích ít thì có nhé, phần này, thích ít này, thích ít này có đấy, anh sẽ gửi cho, và thôi để anh nạp luôn.

**[02:16:00 - 02:16:04] Viethoang Mai (vi):**
em thấy cái tích này chắc nặng mấy anh thôi chứ em em à

**[02:16:13 - 02:16:17] Toan Cap Khanh (vi):**
Chào anh tính nha.

**[02:16:20 - 02:16:24] Toan Cap Khanh (vi):**
Chưa tạo tích kích, đoạn đánh làm đi, tí nữa anh sẽ mang...

**[02:16:25 - 02:16:29] Viethoang Mai (vi):**
Nói chung cái này FBA chắc nhanh thôi nhỉ Anh cứ chết

**[02:16:31 - 02:16:37] Toan Cap Khanh (vi):**
Đấy ngoài ra thì đoạn này cũng có V thì cái hẳn này thì anh sẽ thêm nhé

**[02:16:38 - 02:16:48] Toan Cap Khanh (vi):**
ở phía làm thích này đội đội đi ra ấy thì nó sẽ có thêm 4 cái tích này cái ở trong cái file

**[02:17:13 - 02:17:24] Toan Cap Khanh (vi):**
Đấy, thì bên cái châu đoạn này, các cái feedback bao gồm cả feedback và cái bug mà bên phía Android nẫn phía feedback.

**[02:17:25 - 02:17:33] Toan Cap Khanh (vi):**
Thì trong này ở đây sẽ có 4 cái này mà họ ghi là delete trong tháng 8.

**[02:17:35 - 02:17:46] Toan Cap Khanh (vi):**
bốn trong bốn cái này thì là có cái này là đang hotfix rồi là cái tác số 863 hay là 96

**[02:17:48 - 02:17:48] Toan Cap Khanh (vi):**
trong tháng 8 thì hôm qua nói chuyện thì là bên phía Hằng bảo nó không có công số để test thêm mấy tác này nên là bên phía Figma họ bảo là mấy tác này chỉ cần đẩy đến staging họ test ok xong rồi thì sẽ là cho đi con nói thì thì là như thế xong anh cũng

**[02:17:49 - 02:17:53] Toan Cap Khanh (vi):**
trong tháng 8 thì hôm qua nói chuyện thì là bên phía Hằng bảo nó không có công số để test thêm

**[02:17:53 - 02:17:59] Toan Cap Khanh (vi):**
mấy tác này nên là bên phía Figma họ bảo là mấy tác này chỉ cần đẩy đến staging họ test ok xong rồi

**[02:17:59 - 02:18:28] Toan Cap Khanh (vi):**
thì sẽ là cho đi còn oi thì thì là như thế xong anh cũng bảo với họ nè nếu mà mấy cái tác này mà không liên quan đến phía QAQC mà phải test ấy thì cũng phải nó vào đâu đấy không để cho các bên khác đều biết đấy nên là có 3 cái tác này là sẽ bên phía bên phía Figma họ test ok thì mình sẽ đi còn oi nên

**[02:18:31 - 02:18:33] Toan Cap Khanh (vi):**
Nó chỉ select hay gì đấy.

**[02:18:36 - 02:18:40] Vi Duong (vi):**
Cái này là có tạo đất mai quản lý không? Hay là như thế nào không?

**[02:18:40 - 02:18:48] Toan Cap Khanh (vi):**
Cái này là sẽ tạo Deadmine.

**[02:18:49 - 02:18:52] Toan Cap Khanh (vi):**
tác này là chưa tạo này và cái tác bên trên này cũng chưa tạo này

**[02:19:05 - 02:19:09] Toan Cap Khanh (vi):**
Rồi, vậy nha, sang phía Hưng nha. Hưng xem giúp anh tí nha Hưng ơi.

**[02:19:09 - 02:19:13] Hung Nguyen (vi):**
Anh quay lại cái bàn đi

**[02:19:15 - 02:19:30] Hung Nguyen (vi):**
Ở cái bốp áp này nè thì cái chỗ phân phối này thì khi mà kích vào nút xanh á thì nó sẽ nhảy sang cái màn thêm bố xét tinh á ở cái màn đấy mới gọi là thực sự là mới là phân phối đấy

**[02:19:35 - 02:19:41] Toan Cap Khanh (vi):**
Đấy, châu đoạn này không phải tạo mới sheet đâu nhá.

**[02:19:42 - 02:19:56] Toan Cap Khanh (vi):**
Có nghĩa là ông HD phân phối xuống level 1 rồi, xong rồi ông muốn sửa lại thì anh đang hiểu là hiện tại bức tường xanh ở đây của mình là mình đang call API và update data ngay từ bữa này.

**[02:19:58 - 02:20:01] Hung Nguyen (vi):**
Và kích vào đâu thì nó ra được cái màn này anh nhỉ

**[02:20:03 - 02:20:07] Toan Cap Khanh (vi):**
Tích vào đâu ra được màn này, tích vào đâu ra được màn hình đây. Chào anh Tí.

**[02:20:09 - 02:20:13] Toan Cap Khanh (vi):**
Anh để anh qua đây đi, anh điểm 098 đi, để anh click vào đây.

**[02:20:14 - 02:20:18] Hung Nguyen (vi):**
ở trước là trước là nó ra màn thêm một xét tình anh

**[02:20:18 - 02:20:22] Toan Cap Khanh (vi):**
Ừ không trước đấy nào ra màn hình màn hình

**[02:20:23 - 02:20:25] Hung Nguyen (vi):**
Ok anh chỉ là cái này chỉ là thêm cái bộ app này đúng không?

**[02:20:25 - 02:20:26] Toan Cap Khanh (vi):**
Đúng, thêm cái pop-up.

**[02:20:30 - 02:20:42] Toan Cap Khanh (vi):**
Và một cái nữa, hiện tại nhé, là đối với một cái ship mà đã hoàn thành xong rồi hứa Hưng ạ. Ví dụ như...

**[02:20:47 - 02:20:50] Toan Cap Khanh (vi):**
Nột xít mà đã hoàn thành rồi. Nột xít đã hoàn thành rồi.

**[02:21:23 - 02:21:26] Toan Cap Khanh (vi):**
ship mà đã hoàn thành rồi có cần không nhỉ hay là chỉ cần

**[02:21:27 - 02:21:32] Toan Cap Khanh (vi):**
Một xít chưa hoàn thành là được nhỉ? Thôi, chắc là chỉ cần đối cho cái xít mà nó chưa hoàn thành thôi.

**[02:21:36 - 02:21:38] Toan Cap Khanh (vi):**
Anh sẽ để mô luôn cho mọi người

**[02:25:15 - 02:25:17] Toan Cap Khanh (vi):**
ừ ừ

**[02:25:25 - 02:25:27] Toan Cap Khanh (vi):**
Đậu xanh, mới đi ra ta rồi.

**[02:25:42 - 02:25:44] Toan Cap Khanh (vi):**
Mượn đăng ký kênh của Vy nhé.

**[02:25:44 - 02:25:46] Vi Duong (vi):**
Cho thuê

**[02:25:48 - 02:25:52] Toan Cap Khanh (vi):**
mượn rồi không thể nào cái đối tượng ở đây thì tìm được ai thì được nào

**[02:25:52 - 02:25:59] Vi Duong (vi):**
Vì hay không? Mình cứ ra hai không mấy đó là gì? Vì hay không? Rồi, đấy.

**[02:26:35 - 02:26:40] Viethoang Mai (vi):**
chị viên chị có thép lại cái message hôm qua

**[02:26:41 - 02:26:45] Vi Duong (vi):**
Cái boot up thì thế lại nó vẫn như cũ.

**[02:26:46 - 02:26:48] Vi Duong (vi):**
Vẫn chữ là cancel à.

**[02:26:48 - 02:26:49] Viethoang Mai (vi):**
Anh Tùng ơi

**[02:26:51 - 02:26:53] Tung Dao (vi):**
Ơi anh nghe đây

**[02:26:53 - 02:27:00] Viethoang Mai (vi):**
Em check ở trong cái deploy Cái nhánh

**[02:27:01 - 02:27:08] Viethoang Mai (vi):**
Em chạy trên local nhanh cái cũng có cái code mới rồi nhưng mà

**[02:27:08 - 02:27:09] Viethoang Mai (vi):**
Được không?

**[02:27:10 - 02:27:12] Tung Dao (vi):**
Thế anh nhắn lại phòng.

**[02:27:20 - 02:27:29] Toan Cap Khanh (vi):**
Đây thì là cái kênh này, anh đang là bằng ông Ami1.

**[02:27:30 - 02:27:35] Toan Cap Khanh (vi):**
Nó ra đối với rằng khách ở thì

**[02:27:37 - 02:27:46] Toan Cap Khanh (vi):**
ở cái tên tốt như thế này sau anh sẽ tiến hành vào đây anh update lại em đếp của nó

**[02:27:48 - 02:27:53] Toan Cap Khanh (vi):**
anh vào đây thì cái đoạn này data của nó nó đang không được thay đổi

**[02:27:56 - 02:27:57] Toan Cap Khanh (vi):**
Và bên này cũng đang thế.

**[02:27:58 - 02:28:10] Toan Cap Khanh (vi):**
Nên là cái chỗ API update sheet có vẻ như mình đang validate theo điều kiện gì đấy để cho cái thằng Ended ở đây đang không được update, không được thay đổi hết

**[02:28:14 - 02:28:17] Hung Nguyen (vi):**
Anh tích vào cái nút

**[02:28:18 - 02:28:19] Toan Cap Khanh (vi):**
Thích nút to to.

**[02:28:23 - 02:28:38] Hung Nguyen (vi):**
Trường hợp nha, trường hợp ở trong này nó có thể là có cái bản đi, có tay đi đã gửi lên rồi, có cái đang open.

**[02:28:39 - 02:28:43] Toan Cap Khanh (vi):**
Những cái mà một sám này chắc chắn đã có update rồi này

**[02:28:46 - 02:28:47] Toan Cap Khanh (vi):**
Còn những cái mà

**[02:28:49 - 02:28:59] Toan Cap Khanh (vi):**
Còn những cái mà nó đã phân phối xuống cấp dưới, có nghĩa là thằng category 1 này nó có group 1, group 2, trong thằng này đã có con rồi này.

**[02:29:03 - 02:29:11] Toan Cap Khanh (vi):**
Còn nếu mà ví dụ như là ở đây em tạo ra một cái em có một cái category mới hoàn toàn là category 3 và em chưa phân phối

**[02:29:12 - 02:29:17] Toan Cap Khanh (vi):**
Và cái thằng chính bản thân category 3 này nó cũng chưa đẩy lên cho thằng HR thì lúc đấy là có thể exit được.

**[02:29:18 - 02:29:24] Hung Nguyen (vi):**
tức là nó ở trạng thái áp lưu gì hết và đã

**[02:29:29 - 02:29:32] Toan Cap Khanh (vi):**
Nhưng mà từ từ đã, em đang hỏi anh hay nào

**[02:29:33 - 02:29:35] Hung Nguyen (vi):**
Em đang có phơm lái đánh đấy

**[02:29:35 - 02:29:43] Toan Cap Khanh (vi):**
Ừ cái chỗ đoạn này nhé đoạn này thì đoạn này

**[02:29:46 - 02:29:50] Toan Cap Khanh (vi):**
Trong trường hợp cái người nào mà có quyền exit được cái thằng status ended ở đây ấy

**[02:29:51 - 02:29:56] Toan Cap Khanh (vi):**
chỉ cần là nó exit được và phía bell

**[02:29:59 - 02:30:02] Toan Cap Khanh (vi):**
Hay là có đang cần phải update tất cả những thằng con này không?

**[02:30:03 - 02:30:11] Hung Nguyen (vi):**
Không, hiện tại thì nó sẽ trách cái thằng nào mà

**[02:30:12 - 02:30:17] Toan Cap Khanh (vi):**
Trận thái Open to Update. Update cho cái thằng Category này hả? Hay là Update cho Startup và Endup của sheet?

**[02:30:18 - 02:30:27] Hung Nguyen (vi):**
Nó nhận lên cái gì thì nó check

**[02:30:28 - 02:30:31] Toan Cap Khanh (vi):**
Category và trạng thái open thì mới được spread update.

**[02:30:32 - 02:30:35] Hung Nguyen (vi):**
Còn cái chỗ ngày tháng kia thì em sẽ trinh lại.

**[02:30:35 - 02:30:36] Toan Cap Khanh (vi):**
Ok, xếp hư.

**[02:30:38 - 02:30:43] Toan Cap Khanh (vi):**
Bối cảnh của cái tác này nó sẽ rơi vào cái...

**[02:30:44 - 02:30:56] Toan Cap Khanh (vi):**
nhưng mà cái ông ht ông ấy bận quá hoặc là ông quên mất ông ấy chưa chưa áp ru cho cái thẳng category đấy để hoàn thành xong cái ship đấy thì

**[02:30:58 - 02:31:06] Toan Cap Khanh (vi):**
Còn đối với cái tác mà đã hoàn thành rồi

**[02:31:08 - 02:31:18] Toan Cap Khanh (vi):**
và đoạn này đoạn này thì anh sẽ nhờ phía đoạn này chắc sẽ nhờ phía

**[02:31:19 - 02:31:27] Toan Cap Khanh (vi):**
không cho không cho update chỉ với cái ship mà đang ở cái status đầu tiên này

**[02:31:29 - 02:31:30] Toan Cap Khanh (vi):**
Ok mọi người.

**[02:31:30 - 02:31:48] Hung Nguyen (vi):**
Tức là nếu mà trong cái danh sách update đấy, nó mà không có bản ghi nào, có nghĩa là tất cả các bản ghi đều ở cái trạng.

**[02:31:51 - 02:31:56] Toan Cap Khanh (vi):**
Tất cả các bạn ghi đều đã commit, commit ở đây yếu của em là cấp dưới đã đẩy lên hay là cái thằng HD đã updu hết rồi.

**[02:31:57 - 02:31:57] Hung Nguyen (vi):**
ở đây có nghĩa là cái cà tiên lưu của lúc nó đều ở trạng thái áp lưu hết rồi có nghĩa là mình mình cứ hiểu được giả là không được sửa thì khi này cái cái này cái này trạng thái rất tắt nó có đứa của axit là nó sẽ đi si bồ đi

**[02:31:58 - 02:32:04] Hung Nguyen (vi):**
ở đây có nghĩa là cái cà tiên lưu của lúc nó đều ở trạng thái áp lưu hết rồi có nghĩa là mình

**[02:32:04 - 02:32:10] Hung Nguyen (vi):**
mình cứ hiểu được giả là không được sửa thì khi này cái cái này cái này trạng thái rất tắt

**[02:32:10 - 02:32:13] Hung Nguyen (vi):**
có xích là nó sẽ đi xe bồ đi

**[02:32:15 - 02:32:32] Toan Cap Khanh (vi):**
Không phải đâu. Nhưng cái cây của Hưng nói nhất thì nó sẽ rơi vào cái cây như của anh ở bên trên này. Cái thằng các cấp con đã đẩy lên hết rồi.

**[02:32:34 - 02:32:42] Toan Cap Khanh (vi):**
status của category này nếu mà ht nhìn vào thì đang ở in progress nhưng mà cái thằng dưới đã đẩy lên rồi thì status của thằng

**[02:32:50 - 02:32:54] Hung Nguyen (vi):**
Ví dụ nhé, ở đây ý của em

**[02:32:55 - 02:32:58] Hung Nguyen (vi):**
Ví dụ ở đây nhé, thằng này là mình không được phép chỉ sửa nữa đúng không?

**[02:32:59 - 02:33:02] Hung Nguyen (vi):**
Không được phép thủy sửa thì có nghĩa là cái thần sật

**[02:33:03 - 02:33:05] Hung Nguyen (vi):**
Thì mình cũng không được phép chỉnh sửa nữa

**[02:33:08 - 02:33:09] Toan Cap Khanh (vi):**
phải cho nó chỉnh sửa chứ

**[02:33:11 - 02:33:16] Hung Nguyen (vi):**
Thì cái cây của anh vừa nói là nó cầm list là không được phép vì sửa start date and list là của cái trường hợp nào anh nhỉ.

**[02:33:16 - 02:33:17] Toan Cap Khanh (vi):**
Của cái trường hợp

**[02:33:16 - 02:33:22] Viethoang Mai (vi):**
Complete là khi HR nó uprui, lúc SSH nó uprui xong rồi.

**[02:33:22 - 02:33:34] Toan Cap Khanh (vi):**
Ừ anh em nói về cái trường hợp mà cái cái xít đấy nó đã hoàn thành rồi ý có nghĩa là cái hưng

**[02:33:36 - 02:33:38] Hung Nguyen (en):**
So, okay.

**[02:33:38 - 02:33:39] Toan Cap Khanh (vi):**
Ok, dễ phương.

**[02:33:41 - 02:33:47] Toan Cap Khanh (vi):**
Ừ ok nhưng mà cái đoạn này để sau đi sẽ hướng sửa cho anh cái chỗ đoạn là

**[02:33:53 - 02:33:58] Hang Pham (vi):**
Anh Toán là cái chỗ Elan nó thiết này là không thành hotfix hay không

**[02:34:06 - 02:34:08] Toan Cap Khanh (vi):**
Đâu cho đoạn nào khách vào thì đi thân 8, em chỉ cho anh đấy.

**[02:34:12 - 02:34:15] Toan Cap Khanh (vi):**
Từ đầu tiên chỉ cho anh đoạn nào mà họ bảo là tháng ta.

**[02:34:18 - 02:34:20] Toan Cap Khanh (vi):**
Cảm ơn ơn

**[02:34:42 - 02:34:48] Toan Cap Khanh (vi):**
cái này nhé thì là bên phía cái bạn này

**[02:34:49 - 02:34:53] Toan Cap Khanh (vi):**
79928 này nè, cái thằng này sẽ là hotfix này

**[02:35:02 - 02:35:07] Toan Cap Khanh (vi):**
Bạn này bạn ấy bảo là cái y số 1 này thì mức là...

**[02:35:08 - 02:35:11] Hang Pham (vi):**
là thí sinh 1 là thí ý mà hôm qua đúng không anh?

**[02:35:12 - 02:35:15] Hang Pham (vi):**
Nó không phải cái thằng HR đấy nha Mà nó là cái thằng

**[02:35:17 - 02:35:32] Hang Pham (vi):**
Thì bạn hỏi là ban đầu tại sao cái Hotfit, à nó lại coi là Hotfit có lý do gì không hả? Thì bạn này trả lời như thế này thì bạn này bảo là nếu mà chi tiết bạn biết xem như các bạn được không? Và sau khi trả lời như kia thì bạn này bảo là đây là...

**[02:35:38 - 02:35:46] Toan Cap Khanh (vi):**
Thế thì cái ý này, cái ý của cái bạn, chính cái bạn này là cái bạn, cái Kawanga này nó bảo là đưa vào hotfix, thế xong rồi bây giờ nó lại bảo là chuyển sang đến tháng 8 à?

**[02:35:47 - 02:35:56] Hang Pham (vi):**
Thì xong lúc bạn lại hỏi lại là tại sao, tức là phải cho bạn cái lý do giải thích hộ bạn.

**[02:36:01 - 02:36:12] Toan Cap Khanh (vi):**
Thôi để tính anh nhắn đi cái đoạn này mình sẽ vẫn đưa vào hotfix như hiện tại nhé không có nào hoặc là fix được luôn thì fix không cần phải đi đi tháng 8 đâu

**[02:36:14 - 02:36:23] Toan Cap Khanh (vi):**
Ừ cái chỗ đoạn mà chỉ định

**[02:36:23 - 02:36:27] Hang Pham (vi):**
Em phải thêm tab đây nè Em phải thêm tab viết tên cây như các kiểu đây

**[02:36:37 - 02:36:42] Toan Cap Khanh (vi):**
Thôi phần của Hằng cứ để đấy đi, bên phía Hưng hộ anh cái phần Edamexin để xong trước đã nhá Hưng nhá

**[02:36:49 - 02:37:05] Viethoang Mai (vi):**
anh toàn cái màn mà edit lâu em chưa quên là em không nhớ để mỏi cái chỗ mà nó hiển thị started và ended anh còn nó sẽ là started và ended

**[02:37:08 - 02:37:09] Viethoang Mai (vi):**
Luôn ngủ xích đúng không anh?

**[02:37:10 - 02:37:11] Viethoang Mai (vi):**
Còn comment thì sao?

**[02:37:24 - 02:37:30] Viethoang Mai (vi):**
Nhưng nếu anh đi sâu

**[02:37:54 - 02:37:56] Toan Cap Khanh (vi):**
Không, không phải đâu.

**[02:37:56 - 02:38:06] Toan Cap Khanh (vi):**
Cái đoạn này, cái vòng category này, đây nó chỉ có thằng Ended thôi.

**[02:38:07 - 02:38:10] Toan Cap Khanh (vi):**
Phần comment đây là sẽ đi theo từng L nhé Hoàng nhé

**[02:38:12 - 02:38:13] Toan Cap Khanh (vi):**
Thế mọi người,

**[02:38:16 - 02:38:18] Toan Cap Khanh (vi):**
Ok, bên phía Hưng có ý siêu, có vấn đề gì không Hưng ơi?

**[02:38:20 - 02:38:22] Hung Nguyen (vi):**
Anh vừa bảo em làm cái gì á

**[02:38:22 - 02:38:27] Toan Cap Khanh (vi):**
Anh nhờ em sửa lại ra cái thằng EDA message ở đây

**[02:38:32 - 02:38:36] Hung Nguyen (vi):**
Cái này em đang hiểu là trường hợp.

**[02:38:36 - 02:38:44] Hung Nguyen (vi):**
thêm mới Evan thì nó vẫn giữ như cũ có nghĩa là cần cần cả hai quần Home và Admin

**[02:38:44 - 02:38:56] Toan Cap Khanh (vi):**
Có phải thêm vài exit này, thêm vài exit cho một event từ cái thằng menu.

**[02:39:00 - 02:39:02] Hung Nguyen (vi):**
Không cần quên hôn

**[02:39:02 - 02:39:13] Toan Cap Khanh (vi):**
không cần quyền hôn Còn nếu mà thêm còn nếu mà exit một Evan đi từ màn hình hôm ấy thì lúc đấy mình sẽ chết cho quyền hôn

**[02:39:15 - 02:39:22] Toan Cap Khanh (vi):**
mình sẽ chỉ để lại một cái cây quyền admin này thôi còn cái cây màn hình Home cả admin cái cây màn hình hôm này mình sẽ xóa đi

**[02:39:24 - 02:39:28] Hang Pham (vi):**
Anh ta nói vậy là vẫn còn 2 Neskip Hôm

**[02:39:37 - 02:39:47] Hung Nguyen (vi):**
không biết đâu cái tính năng edit nếu mà người ta edit ở màn hình home thì chỉ cần quen hô

**[02:39:49 - 02:39:49] Toan Cap Khanh (vi):**
Đúng rồi.

**[02:39:53 - 02:39:57] Hung Nguyen (vi):**
Cái edit mà mình hôn ra nó đã được xử lý đâu.

**[02:40:00 - 02:40:02] Toan Cap Khanh (vi):**
Chưa được xử lý là sao, lý em là sao?

**[02:40:02 - 02:40:05] Hung Nguyen (vi):**
Có nghĩa là cái nút edit của anh.

**[02:40:06 - 02:40:12] Hung Nguyen (vi):**
Thì mình vẫn dựa cốt như cũ, cái đấy em chưa xử lý thêm gì đâu

**[02:40:12 - 02:40:15] Toan Cap Khanh (vi):**
Ừ thì đoạn này em xử lý thêm giúp anh để chỗ đoạn này nếu mà em

**[02:40:16 - 02:40:25] Toan Cap Khanh (vi):**
Tiếp từ màn hình hộp thì sẽ check

**[02:40:35 - 02:40:36] Toan Cap Khanh (vi):**
Ok, xếp hơn.

**[02:40:36 - 02:40:45] Hang Pham (vi):**
Anh nghe em hỏi thêm tí là cái chỗ bây giờ cũng lại thì cái cái khít này nó chỉ rơi vào cái cây mà một cái thằng UZA đang xa tác và cái thằng UZB nó

**[02:40:51 - 02:40:59] Hang Pham (vi):**
Tại vì về bản chất thì nếu như mà thằng IRA chỉ có quyền vào không thì ban đầu ngay từ đầu

**[02:41:11 - 02:41:16] Hang Pham (vi):**
Sau đấy tìm một cái thẳng ING C

**[02:41:16 - 02:41:19] Hang Pham (vi):**
vào admin của cái thằng B đi

**[02:41:28 - 02:41:32] Toan Cap Khanh (vi):**
ý của em là em muốn làm sao để em tết được cái cây mà hiển thị nét xít đúng không

**[02:41:33 - 02:41:51] Hang Pham (vi):**
chẳng không em confirm lại thôi tại vì là lúc trước này trường hợp mà ba nét xít thì nó em đang nhớ là có cái cây mà cái thằng ba nét xít nha thì bạn với lại với

**[02:41:53 - 02:41:58] Hang Pham (vi):**
à vào được admin đi nhưng mà nó lại nó đang edit ở admin nhưng mà nó lại không có quyền home

**[02:41:58 - 02:42:07] Hang Pham (vi):**
thì lúc ấy không một thằng nào edit quyền của nó gì cả nhưng mà nó vẫn hiển thị cái message là home lên ấy tại vì lúc khi ban đầu là mình đang yêu cầu cả hai quyền

**[02:42:09 - 02:42:12] Hang Pham (vi):**
Thì bây giờ em muốn con phơm lại là sẽ không còn cái cây đấy nữa

**[02:42:12 - 02:42:19] Hang Pham (vi):**
mà chỉ có cái trường hợp mà cái thằng user A đang phao tác cái thằng B vào update chuyển của nó đi thì nó nhị message này

**[02:42:24 - 02:42:46] Toan Cap Khanh (vi):**
đúng rồi đấy khi mà em đang ở màn hình home chẳng hạn mà em đang ở màn hình exit thằng màn hình phía admin chẳng hạn em làm gì đấy xong rồi em có lấy bút tường update hoặc là bút tường clip lúc này nó sẽ trách quyền nếu mà

**[02:42:53 - 02:42:55] Toan Cap Khanh (vi):**
Rồi, vậy nha.

**[02:42:56 - 02:43:01] Toan Cap Khanh (vi):**
mọi người mọi người còn lại là một con phương thêm không đấy liên quan đến cái tác này

**[02:43:15 - 02:43:19] Toan Cap Khanh (vi):**
Rồi ok mọi người vậy nhé, thì sang về thuần nhé.

**[02:43:25 - 02:43:28] Thuan Pham (vi):**
Qua thì em xong cái tắc kia rồi

**[02:43:29 - 02:43:31] Thuan Pham (vi):**
ừ ừ

**[02:43:32 - 02:43:35] Thuan Pham (vi):**
em có xem, em có sửa lại cái

**[02:43:36 - 02:43:39] Thuan Pham (vi):**
X-Bot, em sửa lại lợi

**[02:43:40 - 02:43:41] Thuan Pham (vi):**
đoạn tên thay

**[02:43:47 - 02:43:52] Thuan Pham (vi):**
thì cái nền thai đấy hiện tại nó cũng

**[02:43:53 - 02:43:57] Thuan Pham (vi):**
Còn cái cây mà cái tên file nó nằm trong cái file nó giết lại thì

**[02:43:59 - 02:44:06] Thuan Pham (vi):**
em không chắc là nếu để tên giày nó sẽ nói trong những con

**[02:44:08 - 02:44:10] Toan Cap Khanh (vi):**
Sự bây giờ không cho đặt tiếng phai cả ra.

**[02:44:12 - 02:44:15] Thuan Pham (vi):**
những tên pha thực tế của em thì nó dài quá thì nó không cho đập

**[02:44:18 - 02:44:25] Thuan Pham (vi):**
Còn cái file mà khi nó trả về cho người dùng như thế nào thì em cũng chưa test kỹ kết quả đấy. Nhưng mà nếu mà nó trường hợp mà nó.

**[02:44:25 - 02:44:39] Toan Cap Khanh (vi):**
đúng đoạn này thật ra là anh cũng đang anh cũng đã nghĩ trường hợp là trong trường hợp tên phai mình sẽ cần giới hạn cho nó một số lượng cái tự nhất định chứ không thể để cho nó ví dụ anh mà anh mà

**[02:44:39 - 02:44:43] Thuan Pham (vi):**
Vâng, bởi vì cái tên đấy mình phong nhập tự do mà

**[02:44:43 - 02:44:57] Toan Cap Khanh (vi):**
mình sẽ giới hạn cái số lượng ký tự cho một tên sai Ví dụ như 20 chẳng hạn hoặc 30 hoặc 50 ký tự chẳng hạn còn nếu mà vượt quá cái

**[02:45:01 - 02:45:05] Toan Cap Khanh (vi):**
trong tên file có được không trong tên file có dấu dấu chấm được không nhỉ không đúng không thấy được

**[02:45:06 - 02:45:08] Thuan Pham (vi):**
Nếu được thì phải xem lại

**[02:45:36 - 02:45:41] Toan Cap Khanh (vi):**
Ờ, tên xa có thể được đấy, thế thì...

**[02:45:42 - 02:45:46] Toan Cap Khanh (vi):**
Thì lúc đấy mình sẽ hiển thị

**[02:45:48 - 02:45:48] Thuan Pham (vi):**
Còn cái số nữa

**[02:45:48 - 02:45:50] Toan Cap Khanh (vi):**
và cái tiện kết thì

**[02:45:51 - 02:46:00] Toan Cap Khanh (vi):**
thì để cho em quyết trước đấy cho em em đi phải chứ gì xong rồi

**[02:46:04 - 02:46:08] Toan Cap Khanh (vi):**
Tên phai là một người chỗ này đẹp.

**[02:46:10 - 02:46:18] Toan Cap Khanh (vi):**
Hôm nay vẫn tiếp tục phần bổ sung test case cho tác 2 user không thể giết cùng cho người phải không?

**[02:46:18 - 02:46:23] Thuan Pham (vi):**
Đấy thì chắc là nếu Hoàng viết được thì viết không là hai em chia nhau thôi nhỉ

**[02:46:24 - 02:46:35] Toan Cap Khanh (vi):**
Rồi ok phần xong rồi cái phần đấy xong thì anh em mình sẽ anh sẽ nhờ bên phía vì gửi cho mình đi

**[02:46:38 - 02:46:40] Toan Cap Khanh (en):**
Okay, step done.

**[02:46:42 - 02:46:44] Toan Cap Khanh (vi):**
Bên vi đưa hằng có ý xíu được vấn đề gì không?

**[02:46:50 - 02:46:54] Vi Duong (vi):**
Ờ, nó cái ticket mà hai người...

**[02:46:57 - 02:47:00] Vi Duong (vi):**
Cái này là tính năng mới hay là bức vậy?

**[02:47:05 - 02:47:07] Toan Cap Khanh (vi):**
Cái này là một tab đấy, không phải bắt đâu.

**[02:47:08 - 02:47:15] Vi Duong (vi):**
Sau thế, ông Yonamine và ông mới đọc.

**[02:47:19 - 02:47:21] Toan Cap Khanh (vi):**
Em hỏi ông ấy tại sao?

**[02:47:21 - 02:47:25] Viethoang Mai (en):**
I think I can pop up in any one.

**[02:47:26 - 02:47:28] Toan Cap Khanh (vi):**
Mấy cái popup đấy cũng đều là mới đấy

**[02:47:29 - 02:47:34] Vi Duong (en):**
No, I don't know.

**[02:47:33 - 02:47:34] Vi Duong (en):**
So you can make up the name.

**[02:47:37 - 02:47:45] Vi Duong (vi):**
Nhưng mà cái này thành bức phải kết thêm đáy tất cài.

**[02:47:52 - 02:47:56] Toan Cap Khanh (vi):**
có vấn đề gì nữa không liên quan đến với hai cái tác mà mọi người đang tết đấy

**[02:47:58 - 02:48:07] Vi Duong (vi):**
Cái chỗ hôm qua

**[02:48:08 - 02:48:09] Toan Cap Khanh (en):**
Cancel now.

**[02:48:09 - 02:48:17] Vi Duong (vi):**
Cái test mà đổi cái button cancel thành Tô Di Rữ

**[02:48:18 - 02:48:19] Toan Cap Khanh (vi):**
Ok mọi người

**[02:48:19 - 02:48:24] Toan Cap Khanh (vi):**
Chỗ đoạn này Tùng sẽ giúp anh nhé Tùng nhé, cái việc có nói nên cái thằng phíu trợ 17 ấy.

**[02:48:34 - 02:48:43] Toan Cap Khanh (vi):**
Còn cái chỗ mà Vy anh thấy, Vy hỏi bên cái 1 hay 2 gì đấy, đội đấy chưa trả lời em à?

**[02:49:07 - 02:49:09] Vi Duong (vi):**
Cái bên HR event

**[02:49:09 - 02:49:10] Toan Cap Khanh (vi):**
Thầy đây rồi.

**[02:49:18 - 02:49:27] Toan Cap Khanh (vi):**
Chỗ đoạn này nếu mà đi theo hướng 2 không làm được đâu Nên là nếu mà

**[02:49:31 - 02:49:35] Vi Duong (vi):**
Không mà nói trước cũng được.

**[02:49:37 - 02:49:38] Viethoang Mai (vi):**
Kiểu phần lúc hôm qua đấy hả?

**[02:49:40 - 02:49:41] Toan Cap Khanh (vi):**
Anh đó hôm qua đấy

**[02:49:45 - 02:49:47] Vi Duong (vi):**
Anh vào, anh phát biện luôn đấy.

**[02:49:47 - 02:49:52] Toan Cap Khanh (vi):**
Thôi, đã đọc đến mình đâu, chứ ai làm gì cả thì mình vào mình nói làm gì, kệ họ.

**[02:49:53 - 02:49:56] Vi Duong (vi):**
Nội dung như thế này sao

**[02:50:00 - 02:50:03] Toan Cap Khanh (vi):**
Rồi chờ tí đi, tí nữa qua 12h rồi nhắn cứ từ từ

**[02:50:06 - 02:50:10] Toan Cap Khanh (vi):**
Anh thấy nè, bên này mình cứ bảo cái gì mà mình làm được ấy.

**[02:50:10 - 02:50:20] Toan Cap Khanh (vi):**
Hội này họ dí cho mình đến chết luôn ấy, đây là thôi, cứ tà tà thôi. Bây giờ cái nào làm được đi chăng nữa chẳng hạn ấy, mình cũng buffer thêm công số vào.

**[02:50:21 - 02:50:24] Toan Cap Khanh (vi):**
Không thể đi theo đúng công số được, không hội này được dí nhiều lắm.

**[02:50:26 - 02:50:28] Toan Cap Khanh (en):**
No, yeah

**[02:50:29 - 02:50:30] Vi Duong (en):**
Yeah, okay.

**[02:50:30 - 02:50:31] Toan Cap Khanh (vi):**
Chào mọi người
