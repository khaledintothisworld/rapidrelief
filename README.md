# RapidRelief - Emergency Relief Matcher

A lightweight web app that matches warehouse supplies (water, food, first aid kits) to urgent shelter requests,
allocating by urgency (**Critical > High > Moderate**) and giving coordinators a live status dashboard.

**Stack:** Python 3, Flask, HTML/CSS/vanilla JavaScript. No CDN or external assets, so it works offline.

## Installation
Requires Python 3.9+.

```bash
git clone <your-github-repo-url>
cd rapidrelief
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. The app starts with sample data; use **Reset sample data** to restore it.

## Run the tests
```bash
python -m unittest discover -s tests -v
```

## Phase 1 modules
| # | Module | Where |
|---|--------|-------|
| 1 | Data models: Inventory (item, quantity, warehouse ID), Requests (request ID, shelter ID, item, quantity, urgency), Shelters (shelter ID, name, priority, location x/y) | `allocation.py` |
| 2 | Priority allocation engine: urgency first, then shelter priority, then arrival order; nearest warehouse first; partial fulfilment | `ReliefSystem.queue()` / `allocate()` |
| 3 | Inventory tracking: stock deducted on allocation, never negative, `InsufficientStockError` on over-withdrawal | `add_stock()` / `remove_stock()` |
| 4 | User interface: enter requests, inspect inventory, view allocation log | `templates/index.html`, `static/` |
| 5 | Export: JSON and CSV reports of fulfilled and unfulfilled requests | `/api/export/report.json`, `/api/export/report.csv` |
| 6 | Automated tests: 14 unit tests covering priority, edge cases and negative stock | `tests/test_allocation.py` |

## Project layout
```
app.py              Flask routes and JSON API
allocation.py       Models, allocation engine, inventory, reports
templates/ static/  Web interface
tests/              Unit tests
data/state.json     Saved state (auto-created)
```

## How allocation works
1. Open requests are sorted by urgency, then shelter priority (1-5), then submission order.
2. For each request, warehouses holding the item are tried nearest first (Euclidean distance).
3. Stock is deducted as it is allocated; a shortage gives partial fulfilment and the request stays open.
4. Run allocation again after restocking to finish partial requests.
