import unittest

from resource_plan import parse_resource_plan

# Dữ liệu mẫu THẬT đọc từ tab "Resource plan" (session 2026-08-04) — bảng
# "Thời gian làm việc mỗi ngày" nằm bên phải, header 2 tầng (tháng rồi ngày).
REAL_SAMPLE_ROWS = [
    ["KẾ HOẠCH QUẢN LÝ NGUỒN LỰC\nDự án Project Based/ Labo host management"],
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "Thời gian làm việc mỗi ngày"],
    ["Kế hoạch phân bổ nguồn lực", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "#", "Member", "Role", "July", "", "", "", "", "August", "", "", "", "", "", "", "", "", "Name "],
    ["NGUỒN LỰC DỰ KIẾN (MM)", "", "", "", "NGUỒN LỰC PHÂN BỔ VÀO DỰ ÁN (MM)", "", "", "", "", "", "", "", "", "", "", "", "SO SÁNH \nNGUỒN LỰC", "GHI CHÚ", "", "", "", "", "", "27", "28", "29", "30", "31", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
    ["#", "Project scope", "Original estimated effort", "Re-estimated effort", "Tên nhân sự", "Vai trò", "Xếp hạng \nnhân sự", "Migration", "", "", "", "", "", "", "", "Effort theo vai trò (MM)", "Chênh lệch (MM)", "", "", "", "1", "Bùi Hồng Sơn", "BE", "8", "8", "8", "8", "8", "", "", "8", "8", "8", "8", "8", "", "", "MH_SonBH"],
    ["", "", "", "", "", "", "", "July", "", "", "", "August", "", "", "", "", "", "", "", "", "2", "Nguyễn Thành Đô", "BE", "8", "8", "8", "8", "8", "", "", "8", "8", "8", "8", "8", "", "", "MH_DoNT"],
    ["", "", "", "", "", "", "", "W1", "W2", "W3", "W4", "W1", "W2", "W3", "W4", "", "", "", "", "", "3", "Văn Ngọc Long", "BE", "8", "8", "8", "8", "8", "", "", "8", "8", "8", "8", "8", "", "", "MH_Ngoc Long"],
    ["1", "Migration", "2", "3,00", "Bùi Hồng Sơn", "Developer(BE)", "Senior", "0,00", "0,00", "0,00", "1,00", "1,00", "", "", "", "0,50", "1,00", "", "", "", "4", "Nguyễn Văn Vinh", "FE", "8", "8", "8", "8", "8", "", "", "8", "8", "8", "8", "8", "", "", "MH_VinhNV"],
    ["", "", "", "", "Nguyễn Thành Đô", "Developer(BE)", "Senior", "0,00", "0,00", "0,00", "1,00", "1,00", "", "", "", "0,50", "", "", "", "", "5", "Mai Viết Hoàng", "FE", "8", "8", "8", "8", "8", "", "", "8", "8", "8", "8", "8", "", "", "MH_HoangMV"],
    ["", "", "", "", "Văn Ngọc Long", "Developer(BE)", "Senior", "0,00", "0,00", "0,00", "1,00", "1,00", "", "", "", "0,50", "", "", "", "", "6", "Đỗ Trung Kiên", "FE", "8", "8", "8", "8", "8", "", "", "8", "8", "8", "8", "8", "", "", "MH_KìenDT"],
]

PERSON_CODE_MAP = {
    "MH_SonBH": "SơnBH",
    "MH_DoNT": "ĐôNT",
    "MH_Ngoc Long": "LongVN",
    "MH_VinhNV": "VinhNV",
    "MH_HoangMV": "HoàngMV",
    "MH_KìenDT": "KiênĐT",
}


class ParseResourcePlanTest(unittest.TestCase):
    def test_finds_all_six_people(self):
        result = parse_resource_plan(REAL_SAMPLE_ROWS, PERSON_CODE_MAP, year=2026)
        self.assertEqual(len(result), 6)

    def test_maps_name_code_to_assignee_code(self):
        result = parse_resource_plan(REAL_SAMPLE_ROWS, PERSON_CODE_MAP, year=2026)
        codes = {p["assigneeCode"] for p in result}
        self.assertEqual(codes, {"SơnBH", "ĐôNT", "LongVN", "VinhNV", "HoàngMV", "KiênĐT"})

    def test_builds_correct_iso_dates_across_month_boundary(self):
        result = parse_resource_plan(REAL_SAMPLE_ROWS, PERSON_CODE_MAP, year=2026)
        son = next(p for p in result if p["assigneeCode"] == "SơnBH")
        self.assertEqual(son["dailyHours"]["2026-07-27"], 8.0)
        self.assertEqual(son["dailyHours"]["2026-07-31"], 8.0)
        self.assertEqual(son["dailyHours"]["2026-08-01"], None)  # weekend, để trống
        self.assertEqual(son["dailyHours"]["2026-08-03"], 8.0)
        self.assertEqual(son["dailyHours"]["2026-08-09"], None)  # weekend

    def test_member_full_name_kept(self):
        result = parse_resource_plan(REAL_SAMPLE_ROWS, PERSON_CODE_MAP, year=2026)
        son = next(p for p in result if p["assigneeCode"] == "SơnBH")
        self.assertEqual(son["member"], "Bùi Hồng Sơn")

    def test_unmapped_name_code_falls_back_to_raw_code(self):
        result = parse_resource_plan(REAL_SAMPLE_ROWS, {}, year=2026)
        codes = {p["assigneeCode"] for p in result}
        self.assertIn("MH_SonBH", codes)


if __name__ == "__main__":
    unittest.main()
