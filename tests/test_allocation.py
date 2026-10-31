import csv, io, json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from allocation import InsufficientStockError, ReliefSystem, ValidationError, sample_system


def make(stock=100):
    s = ReliefSystem()
    s.add_warehouse("W1", "Near", 0, 0)
    s.add_warehouse("W2", "Far", 100, 100)
    s.add_shelter("S1", "Shelter One", 3, 1, 1)
    s.add_shelter("S2", "Shelter Two", 5, 2, 2)
    if stock:
        s.add_stock("W1", "Water", stock)
    return s


class AllocationTests(unittest.TestCase):
    def test_priority_order_critical_high_moderate(self):
        s = make(stock=10)
        s.add_request("S1", "Water", 10, "Moderate")
        s.add_request("S1", "Water", 10, "High")
        s.add_request("S1", "Water", 10, "Critical")
        self.assertEqual([r["urgency"] for r in s.queue()], ["CRITICAL", "HIGH", "MODERATE"])
        s.allocate()
        done = {r["urgency"]: s.status(r) for r in s.requests}
        self.assertEqual(done["CRITICAL"], "FULFILLED")
        self.assertEqual(done["HIGH"], "UNFULFILLED")

    def test_shelter_priority_breaks_urgency_tie(self):
        s = make()
        s.add_request("S1", "Water", 5, "High")
        s.add_request("S2", "Water", 5, "High")
        self.assertEqual(s.queue()[0]["shelter_id"], "S2")

    def test_partial_fulfilment_when_stock_short(self):
        s = make(stock=30)
        s.add_request("S1", "Water", 50, "Critical")
        s.allocate()
        self.assertEqual(s.requests[0]["fulfilled"], 30)
        self.assertEqual(s.status(s.requests[0]), "PARTIAL")

    def test_stock_never_negative(self):
        s = make(stock=5)
        s.add_request("S1", "Water", 500, "Critical")
        s.add_request("S2", "Water", 500, "Critical")
        s.allocate()
        self.assertTrue(all(q >= 0 for q in s.inventory.values()))
        self.assertEqual(s.inventory[("W1", "Water")], 0)

    def test_remove_more_than_stock_raises(self):
        s = make(stock=10)
        with self.assertRaises(InsufficientStockError):
            s.remove_stock("W1", "Water", 11)
        self.assertEqual(s.inventory[("W1", "Water")], 10)

    def test_remove_from_missing_item_raises(self):
        with self.assertRaises(InsufficientStockError):
            make().remove_stock("W2", "Water", 1)

    def test_nearest_warehouse_used_first(self):
        s = make(stock=100)
        s.add_stock("W2", "Water", 100)
        s.add_request("S1", "Water", 40, "High")
        s.allocate()
        self.assertEqual(s.inventory[("W1", "Water")], 60)
        self.assertEqual(s.inventory[("W2", "Water")], 100)

    def test_spans_multiple_warehouses(self):
        s = make(stock=30)
        s.add_stock("W2", "Water", 100)
        s.add_request("S1", "Water", 50, "High")
        s.allocate()
        self.assertEqual(s.status(s.requests[0]), "FULFILLED")
        self.assertEqual(len(s.logs), 2)

    def test_allocate_is_idempotent_and_resumes_after_restock(self):
        s = make(stock=10)
        s.add_request("S1", "Water", 25, "High")
        s.allocate(); s.allocate()
        self.assertEqual(s.requests[0]["fulfilled"], 10)
        s.add_stock("W1", "Water", 50)
        s.allocate()
        self.assertEqual(s.status(s.requests[0]), "FULFILLED")
        self.assertEqual(s.inventory[("W1", "Water")], 35)

    def test_no_stock_at_all(self):
        s = make(stock=0)
        s.add_request("S1", "Water", 5, "Critical")
        self.assertEqual(s.allocate(), [])
        self.assertEqual(s.status(s.requests[0]), "UNFULFILLED")

    def test_validation(self):
        s = make()
        for bad in (0, -5, "abc", None):
            with self.assertRaises(ValidationError):
                s.add_request("S1", "Water", bad, "High")
        with self.assertRaises(ValidationError):
            s.add_request("S1", "Water", 5, "Urgent")
        with self.assertRaises(ValidationError):
            s.add_request("NOPE", "Water", 5, "High")
        with self.assertRaises(ValidationError):
            s.add_stock("W1", "Water", -1)
        with self.assertRaises(ValidationError):
            s.add_shelter("S1", "Dup", 2, 0, 0)

    def test_reports(self):
        s = make(stock=10)
        s.add_request("S1", "Water", 10, "Critical")
        s.add_request("S2", "Water", 10, "Moderate")
        s.allocate()
        rep = json.loads(s.report_json())
        self.assertEqual(rep["summary"]["fulfilled"], 1)
        self.assertEqual(rep["summary"]["unfulfilled"], 1)
        rows = list(csv.DictReader(io.StringIO(s.report_csv())))
        self.assertEqual({r["status"] for r in rows}, {"FULFILLED", "UNFULFILLED"})

    def test_empty_report_csv(self):
        self.assertIn("request_id", make().report_csv())

    def test_persistence_roundtrip(self):
        s = sample_system(); s.allocate()
        s2 = ReliefSystem.from_dict(json.loads(json.dumps(s.to_dict())))
        self.assertEqual(s2.stock_rows(), s.stock_rows())
        self.assertEqual(s2.request_rows(), s.request_rows())


if __name__ == "__main__":
    unittest.main()
