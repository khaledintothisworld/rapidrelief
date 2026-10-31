"""RapidRelief - Emergency Relief Matcher (Flask backend)."""
import json
import os
from flask import Flask, Response, jsonify, render_template, request
from allocation import InsufficientStockError, ReliefSystem, ValidationError, sample_system

app = Flask(__name__)
STATE_FILE = os.path.join(os.path.dirname(__file__), "data", "state.json")


def load():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return ReliefSystem.from_dict(json.load(f))
        except (ValueError, KeyError):
            pass
    return sample_system()


system = load()


def save():
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(system.to_dict(), f, indent=2)


@app.errorhandler(ValidationError)
@app.errorhandler(InsufficientStockError)
def handle_error(err):
    return jsonify(error=str(err)), 400


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    return jsonify(shelters=list(system.shelters.values()), warehouses=list(system.warehouses.values()),
                   inventory=system.stock_rows(), requests=system.request_rows(),
                   queue=[r["request_id"] for r in system.queue()], logs=system.logs,
                   summary=system.report()["summary"])


@app.post("/api/shelters")
def add_shelter():
    d = request.get_json(force=True)
    system.add_shelter(d.get("shelter_id"), d.get("name"), d.get("priority"), d.get("x"), d.get("y"))
    save()
    return jsonify(ok=True)


@app.post("/api/requests")
def add_request():
    d = request.get_json(force=True)
    req = system.add_request(d.get("shelter_id"), d.get("item"), d.get("quantity"), d.get("urgency"))
    save()
    return jsonify(request_id=req["request_id"])


@app.post("/api/stock")
def change_stock():
    d = request.get_json(force=True)
    if d.get("action") == "remove":
        system.remove_stock(d.get("warehouse_id"), d.get("item"), d.get("quantity"))
    else:
        system.add_stock(d.get("warehouse_id"), d.get("item"), d.get("quantity"))
    save()
    return jsonify(ok=True)


@app.post("/api/allocate")
def allocate():
    made = system.allocate()
    save()
    return jsonify(allocations=len(made))


@app.post("/api/reset")
def reset():
    global system
    system = sample_system()
    save()
    return jsonify(ok=True)


@app.get("/api/export/report.json")
def export_json():
    return Response(system.report_json(), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=allocation_report.json"})


@app.get("/api/export/report.csv")
def export_csv():
    return Response(system.report_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=allocation_report.csv"})


if __name__ == "__main__":
    app.run(debug=False, port=5000)
