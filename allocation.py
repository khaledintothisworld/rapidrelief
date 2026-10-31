"""RapidRelief core: data models, priority allocation engine, inventory tracking, reporting."""
import csv
import io
import json
import math
from datetime import datetime

URGENCY_RANK = {"CRITICAL": 3, "HIGH": 2, "MODERATE": 1}  # Critical > High > Moderate


class ValidationError(ValueError):
    """Raised for malformed input."""


class InsufficientStockError(Exception):
    """Raised when a withdrawal would push stock below zero."""


def _pos_int(value, field):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number")
    if n <= 0:
        raise ValidationError(f"{field} must be greater than zero")
    return n


def _text(value, field):
    value = (str(value) if value is not None else "").strip()
    if not value:
        raise ValidationError(f"{field} is required")
    return value


class ReliefSystem:
    """Holds Shelters, Warehouses, Inventory, Requests and the allocation log."""

    def __init__(self):
        self.shelters = {}    # shelter_id -> {shelter_id, name, priority(1-5), x, y}
        self.warehouses = {}  # warehouse_id -> {warehouse_id, name, x, y}
        self.inventory = {}   # (warehouse_id, item) -> quantity
        self.requests = []    # {request_id, shelter_id, item, quantity, fulfilled, urgency, seq}
        self.logs = []        # allocation log entries
        self._seq = 0

    # ---------- Shelters / warehouses ----------
    def add_shelter(self, shelter_id, name, priority, x, y):
        shelter_id = _text(shelter_id, "Shelter ID")
        if shelter_id in self.shelters:
            raise ValidationError(f"Shelter {shelter_id} already exists")
        priority = _pos_int(priority, "Priority")
        if priority > 5:
            raise ValidationError("Priority must be between 1 and 5")
        try:
            x, y = float(x), float(y)
        except (TypeError, ValueError):
            raise ValidationError("Location coordinates must be numbers")
        self.shelters[shelter_id] = {"shelter_id": shelter_id, "name": _text(name, "Name"),
                                     "priority": priority, "x": x, "y": y}
        return self.shelters[shelter_id]

    def add_warehouse(self, warehouse_id, name, x, y):
        warehouse_id = _text(warehouse_id, "Warehouse ID")
        self.warehouses[warehouse_id] = {"warehouse_id": warehouse_id, "name": _text(name, "Name"),
                                         "x": float(x), "y": float(y)}

    # ---------- Inventory tracking ----------
    def add_stock(self, warehouse_id, item, quantity):
        if warehouse_id not in self.warehouses:
            raise ValidationError(f"Unknown warehouse {warehouse_id}")
        key = (warehouse_id, _text(item, "Item"))
        self.inventory[key] = self.inventory.get(key, 0) + _pos_int(quantity, "Quantity")

    def remove_stock(self, warehouse_id, item, quantity):
        """Withdraw stock. Never lets a balance go negative."""
        quantity = _pos_int(quantity, "Quantity")
        key = (warehouse_id, _text(item, "Item"))
        available = self.inventory.get(key, 0)
        if quantity > available:
            raise InsufficientStockError(
                f"Cannot remove {quantity} {key[1]} from {warehouse_id}: only {available} in stock")
        self.inventory[key] = available - quantity

    def stock_rows(self):
        return [{"item": i, "quantity": q, "warehouse_id": w}
                for (w, i), q in sorted(self.inventory.items())]

    # ---------- Requests ----------
    def add_request(self, shelter_id, item, quantity, urgency):
        if shelter_id not in self.shelters:
            raise ValidationError(f"Unknown shelter {shelter_id}")
        urgency = _text(urgency, "Urgency").upper()
        if urgency not in URGENCY_RANK:
            raise ValidationError("Urgency must be Critical, High or Moderate")
        self._seq += 1
        req = {"request_id": f"REQ-{self._seq:03d}", "shelter_id": shelter_id,
               "item": _text(item, "Item"), "quantity": _pos_int(quantity, "Quantity"),
               "fulfilled": 0, "urgency": urgency, "seq": self._seq}
        self.requests.append(req)
        return req

    @staticmethod
    def status(req):
        if req["fulfilled"] >= req["quantity"]:
            return "FULFILLED"
        return "PARTIAL" if req["fulfilled"] > 0 else "UNFULFILLED"

    # ---------- Priority allocation engine ----------
    def _dist(self, shelter, wh):
        return math.hypot(shelter["x"] - wh["x"], shelter["y"] - wh["y"])

    def queue(self):
        """Open requests ordered Critical > High > Moderate, then shelter priority, then arrival."""
        open_reqs = [r for r in self.requests if r["fulfilled"] < r["quantity"]]
        return sorted(open_reqs, key=lambda r: (-URGENCY_RANK[r["urgency"]],
                                                -self.shelters[r["shelter_id"]]["priority"], r["seq"]))

    def allocate(self):
        """Serve the queue in priority order, drawing from the nearest warehouses first.
        Shortages give partial fulfilment; the request stays open for later stock."""
        made = []
        for req in self.queue():
            shelter = self.shelters[req["shelter_id"]]
            sources = sorted((w for w in self.warehouses.values()
                              if self.inventory.get((w["warehouse_id"], req["item"]), 0) > 0),
                             key=lambda w: self._dist(shelter, w))
            for wh in sources:
                need = req["quantity"] - req["fulfilled"]
                if need <= 0:
                    break
                take = min(need, self.inventory[(wh["warehouse_id"], req["item"])])
                self.remove_stock(wh["warehouse_id"], req["item"], take)
                req["fulfilled"] += take
                entry = {"time": datetime.now().strftime("%H:%M:%S"), "request_id": req["request_id"],
                         "shelter_id": shelter["shelter_id"], "shelter": shelter["name"],
                         "urgency": req["urgency"], "item": req["item"], "quantity": take,
                         "warehouse_id": wh["warehouse_id"],
                         "distance": round(self._dist(shelter, wh), 1),
                         "result": self.status(req)}
                self.logs.insert(0, entry)
                made.append(entry)
        return made

    # ---------- Export & reporting ----------
    def request_rows(self):
        return [{"request_id": r["request_id"], "shelter_id": r["shelter_id"],
                 "shelter": self.shelters[r["shelter_id"]]["name"], "item": r["item"],
                 "urgency": r["urgency"], "requested": r["quantity"], "fulfilled": r["fulfilled"],
                 "outstanding": r["quantity"] - r["fulfilled"], "status": self.status(r)}
                for r in self.requests]

    def report(self):
        rows = self.request_rows()
        done = [r for r in rows if r["status"] == "FULFILLED"]
        open_ = [r for r in rows if r["status"] != "FULFILLED"]
        req_total = sum(r["requested"] for r in rows)
        return {"generated": datetime.now().isoformat(timespec="seconds"),
                "summary": {"total_requests": len(rows), "fulfilled": len(done),
                            "unfulfilled": len(open_), "units_requested": req_total,
                            "units_delivered": sum(r["fulfilled"] for r in rows),
                            "fulfillment_rate": round(100 * sum(r["fulfilled"] for r in rows) / req_total, 1)
                            if req_total else 0.0},
                "fulfilled_requests": done, "unfulfilled_requests": open_}

    def report_json(self):
        return json.dumps(self.report(), indent=2)

    def report_csv(self):
        out = io.StringIO()
        rows = self.request_rows()
        w = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["request_id"])
        w.writeheader()
        w.writerows(rows)
        return out.getvalue()

    # ---------- Persistence ----------
    def to_dict(self):
        return {"shelters": list(self.shelters.values()), "warehouses": list(self.warehouses.values()),
                "inventory": self.stock_rows(), "requests": self.requests, "logs": self.logs, "seq": self._seq}

    @classmethod
    def from_dict(cls, d):
        s = cls()
        s.shelters = {x["shelter_id"]: x for x in d["shelters"]}
        s.warehouses = {x["warehouse_id"]: x for x in d["warehouses"]}
        s.inventory = {(r["warehouse_id"], r["item"]): r["quantity"] for r in d["inventory"]}
        s.requests, s.logs, s._seq = d["requests"], d["logs"], d["seq"]
        return s


def sample_system():
    s = ReliefSystem()
    for wid, name, x, y in [("WH-1", "Alpha Regional Base", 20, 30), ("WH-2", "Northern Coastal Point", 80, 25),
                            ("WH-3", "Southern Highway Depot", 65, 85)]:
        s.add_warehouse(wid, name, x, y)
    for wid, item, q in [("WH-1", "Water (L)", 12000), ("WH-1", "Food Kits", 4500), ("WH-1", "First Aid Kits", 850),
                         ("WH-2", "Water (L)", 8000), ("WH-2", "Food Kits", 2100), ("WH-2", "First Aid Kits", 1200),
                         ("WH-3", "Water (L)", 15000), ("WH-3", "Food Kits", 6000), ("WH-3", "First Aid Kits", 400)]:
        s.add_stock(wid, item, q)
    for sid, name, pr, x, y in [("SH-101", "St. Jude Community Center", 5, 35, 45),
                                ("SH-102", "Valley High Stadium Shelter", 4, 75, 40),
                                ("SH-103", "Westside Elementary Fieldhouse", 3, 25, 75),
                                ("SH-104", "Riverside Park Enclosure", 2, 55, 70)]:
        s.add_shelter(sid, name, pr, x, y)
    s.add_request("SH-101", "Water (L)", 3500, "Critical")
    s.add_request("SH-102", "Food Kits", 2800, "Critical")
    s.add_request("SH-103", "First Aid Kits", 350, "High")
    s.add_request("SH-104", "Food Kits", 900, "Moderate")
    return s
