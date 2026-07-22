# Google Meet — 2026-07-21

**Attendees:** Toan Cap Khanh, Tung Dao, Duong Tran, Hung Nguyen, Hang Pham, Viethoang Mai

## Key points
- Thảo luận về xử lý "exit" cho một event, có thể trigger từ màn hình admin hoặc từ màn hình home.
- Bàn về việc đặt tên biến/key ngắn gọn (`admin` / `home`) và chuyển phần xử lý xuống backend để dễ validate.
- Có nhắc tới việc thêm một popup confirm trước khi insert/update data, mở tab mới để xác nhận trước khi "insert vào DB".
- Quyết định không cần thêm setting mới cho phần đang bàn — sẽ insert trực tiếp.
- Có nhắc tới mốc sửa đổi "từ 31 tháng 7".
- Cuối buổi, ưu tiên xử lý hotfix trước phần đang thảo luận.

_Đã áp dụng bước lọc nhiễu (skill step 5): 32 đoạn khớp mẫu canned outro/quảng cáo hoặc ngoại ngữ ngắn lạc lõng (hallucination điển hình của Whisper) đã bị loại hẳn khỏi full transcript bên dưới._

## Decisions
- Chuyển đoạn xử lý "exit event" (từ admin/home) xuống backend, đội khác sẽ validate lại.
- Không thêm setting mới cho luồng insert/update đang bàn.
- Ưu tiên hotfix trước, phần còn lại xử lý sau.

## Action items
- [ ] (chưa xác định rõ owner do transcript nhiễu) — chuyển logic exit-event xuống backend
- [ ] (chưa xác định rõ owner) — cập nhật lại theo mốc 31/7

## Full transcript (từ get_transcript, đã lọc nhiễu)

**[08:17:16 - 08:17:35] Toan Cap Khanh (vi):**
thì có thể exit cho một event từ phía thẳng là menu admin này như ở đây mình đang có này cái hr event dòng admin này đấy xong rồi đi vào đây thì có thể exit cho một event ở đây và một cái nữa là exit từ màn hình home nó sẽ đi

**[08:17:37 - 08:17:51] Toan Cap Khanh (vi):**
thì hai cái chỗ đặt này đang côn cùng API và

**[08:17:53 - 08:17:54] Toan Cap Khanh (vi):**
Mình đang...

**[08:18:33 - 08:18:50] Toan Cap Khanh (vi):**
Đấy, nên là đối với cái trường hợp mà update exit một cái event ấy, từ home hay từ admin thì mọi người chuyển lên giúp anh một cái core.

**[08:18:51 - 08:18:54] Toan Cap Khanh (vi):**
để họ validate cho đúng

**[08:18:58 - 08:18:59] Tung Dao (vi):**
Cái này được

**[08:18:58 - 08:19:00] Tung Dao (vi):**
Em thấy ok đấy nhỉ.

**[08:19:01 - 08:19:03] Toan Cap Khanh (vi):**
Ừ, thế thì đoạn này dưa ngàn nhé, 5 phút thôi.

**[08:19:04 - 08:19:09] Tung Dao (vi):**
Thế là mình sẽ đặt cái tên key ngắn rồi anh ạ Hoặc là tên chỉ là admin Hoặc là tên chỉ là home

**[08:19:10 - 08:19:13] Duong Tran (vi):**
quan trọng là chốt chốt chốt kỳ đã anh ạ cho kỳ rồi kỳ tiếp

**[08:19:14 - 08:19:17] Toan Cap Khanh (vi):**
Ok, cái đoạn này back end, back end.

**[08:19:14 - 08:19:15] Toan Cap Khanh (vi):**
Thực kỳ về bác em.

**[08:19:19 - 08:19:26] Hung Nguyen (vi):**
Khi hôn ăn mịn được hoặc là

**[08:19:27 - 08:19:31] Duong Tran (vi):**
có trọng lại cái chốt một cái chuyển chuyển vào đâu nữa thì

**[08:19:32 - 08:19:51] Hung Nguyen (vi):**
khi mà nhấn nút sập mít nhá thì bây loát ví dụ từ trên màn hình là hôm thì thêm một cái tham số và còn nếu mà ví dụ tham số là là là mình có thể

**[08:19:55 - 08:20:07] Tung Dao (vi):**
Anh Toàn này, mọi người này anh nghĩ

**[08:20:09 - 08:20:12] Tung Dao (vi):**
hoặc là SP để nó xong

**[08:20:12 - 08:20:16] Toan Cap Khanh (vi):**
Không dùng cờ, mà em dùng giá trị.

**[08:20:16 - 08:20:16] Tung Dao (en):**
And then...

**[08:20:16 - 08:20:28] Toan Cap Khanh (vi):**
ứng với cái biến này á, ứng với cái phiêu này á Rồi, ok, ok

**[08:20:32 - 08:20:34] Toan Cap Khanh (vi):**
Rồi ok mọi người, thế nào cũng được

**[08:20:38 - 08:20:43] Hung Nguyen (en):**
I'm okay, so I'm going to be able to do this.

**[08:20:43 - 08:20:44] Toan Cap Khanh (en):**
Talk right.

**[08:20:46 - 08:20:49] Tung Dao (en):**
Not a sweet name though, man.

**[08:20:51 - 08:21:06] Toan Cap Khanh (vi):**
Rồi đấy thì đoạn này đối ứng giúp anh nhé Nếu mà đi từ màn hình home thì mình đi từ màn hình home Và em giúp cho em về trong cái event

**[08:21:06 - 08:21:07] Duong Tran (vi):**
Cái này có gấp không anh?

**[08:21:14 - 08:21:20] Hung Nguyen (vi):**
Thế này thì lại phải

**[08:21:20 - 08:21:24] Hang Pham (vi):**
Ừ, xong mà Hương phải update hội chị cảm ơn.

**[08:21:29 - 08:21:33] Duong Tran (vi):**
thế chắc tầm 15 phút đợi em đại kia lên mấy

**[08:21:33 - 08:21:34] Toan Cap Khanh (en):**
It's a doctor.

**[08:21:33 - 08:21:35] Toan Cap Khanh (en):**
Okay, one night.

**[08:21:36 - 08:21:38] Toan Cap Khanh (en):**
Hold up.

**[08:21:42 - 08:21:43] Toan Cap Khanh (vi):**
Cái hẳn lưu cầu ấy

**[08:21:44 - 08:21:54] Hung Nguyen (vi):**
Thực ra thì nếu mà cái này, nếu mà em có từ đầu là em biết Thực ra thì nếu mà em có từ đầu là em biết

**[08:21:54 - 08:21:57] Toan Cap Khanh (vi):**
Nhưng mà em vào tự án này cũng từ đầu mà Hưng

**[08:21:57 - 08:22:00] Hung Nguyen (vi):**
Nhưng mà em làm sao em biết là nó dùng vào đâu.

**[08:22:02 - 08:22:04] Toan Cap Khanh (vi):**
Ok Hưng, rồi, hộ anh bạn đấy nhé.

**[08:22:06 - 08:22:07] Toan Cap Khanh (vi):**
Hắn có gì muốn nói thêm không?

**[08:22:07 - 08:22:09] Hang Pham (vi):**
Em hẹn tùy ngủ

**[08:22:15 - 08:22:17] Viethoang Mai (vi):**
Có sắc liếm ăn đấy của em không?

**[08:22:18 - 08:22:20] Toan Cap Khanh (vi):**
Mà đấy không phải của em thì được của ai hả, mà này

**[08:22:23 - 08:22:25] Toan Cap Khanh (vi):**
Thôi Hậu Dương đi, nó không làm được mà

**[08:22:23 - 08:22:24] Toan Cap Khanh (en):**
So, thank you.

**[08:22:26 - 08:22:29] Duong Tran (vi):**
rồi mà thôi mà lại chắc khoảng lắm đoạn

**[08:22:29 - 08:22:30] Toan Cap Khanh (vi):**
Ngay nếu mà

**[08:22:30 - 08:22:37] Viethoang Mai (vi):**
Em không rõ nha, nếu có tác thì có để cho Vinh không anh Tùng

**[08:22:39 - 08:22:46] Tung Dao (vi):**
Anh nghĩ là vẫn để, nhưng mà chắc là cứ để...

**[08:22:47 - 08:23:08] Toan Cap Khanh (vi):**
ở đây trước đấy là nó sẽ có hai bút tỉnh một là bút tình còn phơm và một cái bút tình là ở đây thì khách hàng bóng ra rồi mà nó chỉ còn bút tình còn

**[08:23:09 - 08:23:10] Toan Cap Khanh (en):**
If we don't have time.

**[08:23:10 - 08:23:15] Toan Cap Khanh (vi):**
nhưng mà làm như thế thì sẽ nặng lắm họ không làm được nên là anh có nhờ khách hàng là tại

**[08:23:22 - 08:23:26] Toan Cap Khanh (en):**
We did a purpose. We did a purpose.

**[08:23:35 - 08:23:37] Toan Cap Khanh (vi):**
cái màn hình này mình sẽ cho insert và cho đi luôn chứ không cần phải sang cái tác mới đâu nên ở chỗ đặt này nó sẽ cái bút tình này là bút tình ảnh ở đây khi cái bút tình này mình sẽ hiển thị cái phút bắt còn phương như thế này dạng yếu như thế này nếu mà cancel thì không làm gì còn nếu mà yếu đây thì

**[08:23:39 - 08:23:40] Toan Cap Khanh (vi):**
Không cần thêm một setting luôn.

**[08:23:42 - 08:23:45] Tung Dao (vi):**
Trước đấy thì chưa có cái podcast

**[08:23:46 - 08:24:06] Toan Cap Khanh (vi):**
Chưa, trước đấy là không có popup confirm, mà nó chỉ có cái bút tử confirm ở đây. Và nó sẽ mở ra một cái tab mới, click vào cái tab mới đấy. Click vào đây này, mở tab mới này, bên tab mới, click vào bút tử ok. Thì mới là InSource đã cao vào trong VB.

**[08:24:07 - 08:24:08] Toan Cap Khanh (en):**
Okay, then is that

**[08:24:08 - 08:24:11] Viethoang Mai (vi):**
là đang giả thiết cho chị đúng anh toàn cánh bật tóc mới là đang giả thiết thôi chứ đúng không

**[08:24:12 - 08:24:15] Toan Cap Khanh (vi):**
Bật tác mới này ra em giả tiết. Ừ, ta giả tiết.

**[08:24:16 - 08:24:18] Viethoang Mai (vi):**
Thì cái giả thiết bây giờ mình không làm nữa đúng không?

**[08:24:19 - 08:24:19] Toan Cap Khanh (vi):**
Đúng rồi.

**[08:24:19 - 08:24:22] Viethoang Mai (vi):**
Đấy thì nên là nó không có làm nhằng đúng không?

**[08:24:22 - 08:24:27] Toan Cap Khanh (vi):**
Ừ, mà ở đây nó sẽ insert đại thao vào trong đĩa bình luôn.

**[08:24:28 - 08:24:31] Tung Dao (vi):**
qua gặp phố bác con phơm nó sẽ đơn giản hơn

**[08:24:32 - 08:24:39] Toan Cap Khanh (vi):**
Ừ có cái tốt bắp cái phố cấp này nó hiển thị ở chính là hình nền luôn kích vào ok thì đã tết

**[08:24:40 - 08:24:45] Viethoang Mai (vi):**
Cái vụ này là vụ

**[08:24:45 - 08:24:51] Toan Cap Khanh (vi):**
Đúng rồi, sáng nay anh nói

**[08:24:54 - 08:24:58] Viethoang Mai (vi):**
Đoạn này sẽ có thêm mới, có sửa đếp

**[08:24:59 - 08:24:59] Toan Cap Khanh (vi):**
Đúng rồi.

**[08:25:02 - 08:25:05] Tung Dao (vi):**
Nhưng mà cái đoạn này là bên mình đã làm.

**[08:25:07 - 08:25:09] Viethoang Mai (en):**
And then...

**[08:25:17 - 08:25:22] Viethoang Mai (vi):**
em nó không nhớ là bình thường cái này nó sẽ ra cái chủ tài luôn

**[08:25:24 - 08:25:25] Viethoang Mai (vi):**
Bình thường nhé, bình thường

**[08:25:25 - 08:25:30] Toan Cap Khanh (vi):**
nó sẽ insert

**[08:25:31 - 08:25:32] Toan Cap Khanh (en):**
Oh, okay.

**[08:25:31 - 08:25:32] Toan Cap Khanh (vi):**
Bên table setting luôn.

**[08:25:34 - 08:25:43] Viethoang Mai (vi):**
Vâng, có nó phân phối đúng không anh nhỉ? Hay là không có nhỉ? Em không nghe nhỉ.

**[08:25:47 - 08:25:51] Viethoang Mai (vi):**
bức sửa mà lại ra màn thêm một setting em lâu em chưa tết

**[08:25:52 - 08:26:00] Toan Cap Khanh (vi):**
Đây, đoạn ánh

**[08:26:03 - 08:26:06] Toan Cap Khanh (vi):**
Chỗ đoạn này anh sửa từ 31 tháng 7.

**[08:26:11 - 08:26:16] Toan Cap Khanh (vi):**
Thì cái bạn một thẳng 8 nó sẽ update rồi

**[08:26:20 - 08:26:25] Toan Cap Khanh (vi):**
Thì cái màn hình này mình không cần điển tị nữa

**[08:26:27 - 08:26:30] Viethoang Mai (vi):**
Nhưng mà bây giờ lại thêm một cái popup nữa à

**[08:26:32 - 08:26:35] Toan Cap Khanh (vi):**
Ừ, thêm cái popup trước khi update data.

**[08:26:39 - 08:26:41] Tung Dao (vi):**
Chèn thêm một cái pop-up.

**[08:26:41 - 08:26:43] Tung Dao (en):**
the console

**[08:26:42 - 08:26:43] Tung Dao (en):**
Gemma, thank you.

**[08:26:44 - 08:26:48] Tung Dao (vi):**
Thì mới cho Edith

**[08:26:54 - 08:26:57] Toan Cap Khanh (vi):**
Rồi vậy nhé, anh sang bên này, anh sang bên này thì đã nhé mọi người nhé

**[08:26:58 - 08:26:59] Tung Dao (en):**
Brilliant.

**[08:27:00 - 08:27:00] Tung Dao (en):**
Uh, uh,

**[08:27:00 - 08:27:11] Toan Cap Khanh (vi):**
Dương ơi, em giúp anh thích

**[08:27:13 - 08:27:17] Hung Nguyen (vi):**
Đối với phần này trước anh cứ lại kịp kênh em bằng nàm lại lùi lại.

**[08:27:21 - 08:27:22] Toan Cap Khanh (vi):**
Ta sẽ có chút nữa.

**[08:27:24 - 08:27:27] Toan Cap Khanh (vi):**
Mình ưu tiên cho cái thằng hotfix của mình trước đã.

**[08:27:28 - 08:27:35] Hung Nguyen (vi):**
Cái này thì phía

**[08:27:33 - 08:27:35] Hung Nguyen (en):**
Let me try to do a little bit.

**[08:27:36 - 08:27:38] Toan Cap Khanh (vi):**
Rồi vậy nha, chào mọi người

**[08:27:38 - 08:27:39] Viethoang Mai (en):**
Well, I'm sorry.

**[08:27:41 - 08:27:43] Tung Dao (en):**
Thank you very much. Thank you.
