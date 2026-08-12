import unittest

from tally import tally_by_status, top_high_priority_open

ITEMS = [
    {"id": "R-01", "priority": "High", "status": "Open"},
    {"id": "R-02", "priority": "High", "status": "In progress"},
    {"id": "R-03", "priority": "Medium", "status": "Pending"},
    {"id": "R-04", "priority": "Low", "status": "Done"},
    {"id": "R-05", "priority": "High", "status": "Cancel"},
    {"id": "R-06", "priority": "High", "status": "Done"},
]


class TallyByStatusTest(unittest.TestCase):
    def test_counts_open_pending_together(self):
        result = tally_by_status(ITEMS)
        self.assertEqual(result["open"], 2)  # R-01 (Open) + R-03 (Pending)
        self.assertEqual(result["inProgress"], 1)
        self.assertEqual(result["closed"], 3)  # Done/Done/Cancel

    def test_empty_list(self):
        self.assertEqual(tally_by_status([]), {"open": 0, "inProgress": 0, "closed": 0})


class TopHighPriorityOpenTest(unittest.TestCase):
    def test_filters_high_priority_not_closed(self):
        result = top_high_priority_open(ITEMS)
        ids = [i["id"] for i in result]
        self.assertEqual(ids, ["R-01", "R-02"])

    def test_respects_limit(self):
        result = top_high_priority_open(ITEMS, limit=1)
        self.assertEqual(len(result), 1)

    def test_case_insensitive_priority(self):
        items = [{"id": "R-99", "priority": "high", "status": "Open"}]
        self.assertEqual(len(top_high_priority_open(items)), 1)


if __name__ == "__main__":
    unittest.main()
