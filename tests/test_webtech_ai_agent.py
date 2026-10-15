from fastapi.testclient import TestClient

from app.main import app
from app.modules.webtechAIAgent import service

client = TestClient(app)

LAVKUSH = {
    "id": 7,
    "name": "Lavkush Dark Store",
    "code": "LAVK",
    "lot_stock_id": [11, "LAVK/Stock"],
    "active": True,
}
RAJNI = {
    "id": 8,
    "name": "Rajni Krishi Seva Kendra Dark Store",
    "code": "RAJNI",
    "lot_stock_id": [12, "RAJNI/Stock"],
    "active": True,
}


def _warehouses() -> list[dict]:
    return [LAVKUSH, RAJNI]


def _fake_odoo(model: str, method: str, payload: dict):
    assert method == "search_read"
    if model == "stock.warehouse":
        return _warehouses()
    if model == "stock.location" and payload["fields"] == ["id", "complete_name", "usage"]:
        return [
            {
                "id": 22,
                "complete_name": "Virtual Locations/Lavkush Dark Store",
                "usage": "transit",
            }
        ]
    if model == "product.product" and ["name", "ilike", "urea"] in payload["domain"]:
        return [
            {"id": 101, "default_code": "501", "name": "Urea 45kg", "display_name": "Urea 45kg"},
            {"id": 102, "default_code": "502", "name": "Urea 50kg", "display_name": "Urea 50kg"},
        ]
    if model == "product.product":
        return [
            {"id": 101, "default_code": "501", "name": "Urea 45kg", "display_name": "Urea 45kg"}
        ]
    if model == "stock.move":
        return [
            {
                "id": 1,
                "reference": "WH/OUT/1",
                "origin": "AGRI1001 customer",
                "state": "done",
                "date": "2026-10-02 04:30:00",
                "product_uom_qty": 4,
                "quantity": 4,
                "location_id": [11, "LAVK/Stock"],
                "location_dest_id": [90, "Customers"],
                "picking_id": [5, "WH/OUT/1"],
                "sale_line_id": False,
                "origin_returned_move_id": False,
            }
        ]
    if model == "stock.picking":
        return [
            {
                "id": 5,
                "name": "WH/OUT/1",
                "origin": "AGRI1001",
                "state": "done",
                "partner_id": [3, "Ram, Village"],
                "scheduled_date": "2026-10-02 04:00:00",
                "date_done": "2026-10-02 05:00:00",
                "return_id": False,
            }
        ]
    if model == "stock.quant":
        return [{"quantity": 12, "reserved_quantity": 2}]
    return [{"id": 11, "usage": "internal"}, {"id": 90, "usage": "customer"}]


def setup_function() -> None:
    service.warehouse_cache = None


def test_empty_message_is_rejected() -> None:
    response = client.post("/api/v1/webtech-ai-agent", json={"message": "  ", "context": None})

    assert response.status_code == 400
    assert response.json()["msg"] == "Message likho"


def test_missing_store_asks_which_dark_store(monkeypatch) -> None:
    monkeypatch.setattr(service, "odoo", _fake_odoo)

    response = client.post("/api/v1/webtech-ai-agent", json={"message": "delivered kitna hai"})

    body = response.json()
    assert response.status_code == 200
    assert body["status"] is True
    assert body["data"]["reply"] == "Kaun sa dark store? Naam likho."
    assert "Rajni" not in body["data"]["reply"]
    assert body["data"]["context"]["candidates"] == []
    assert body["data"]["context"]["pending"] == "store"


def test_two_stores_are_listed(monkeypatch) -> None:
    monkeypatch.setattr(service, "odoo", _fake_odoo)

    response = client.post(
        "/api/v1/webtech-ai-agent",
        json={"message": "lavkush rajni delivered october"},
    )

    data = response.json()["data"]
    labels = [row["label"] for row in data["context"]["candidates"]]
    assert data["reply"] == "Kaun sa dark store?"
    assert "Lavkush" not in data["reply"]
    assert any("Lavkush" in label for label in labels)
    assert any("Rajni" in label for label in labels)


def test_delivered_total_for_one_store(monkeypatch) -> None:
    monkeypatch.setattr(service, "odoo", _fake_odoo)

    response = client.post(
        "/api/v1/webtech-ai-agent",
        json={"message": "lavkush delivered october 2026"},
    )

    data = response.json()["data"]
    assert response.status_code == 200
    assert "Lavkush Dark Store" in data["reply"]
    assert "Delivered · 1 Oct 2026 se 31 Oct 2026" in data["reply"]
    assert "Total 4 · 1 documents" in data["reply"]
    assert data["context"]["storeId"] == 7
    assert data["rows"] == []


def test_on_hand_needs_a_product_then_answers(monkeypatch) -> None:
    monkeypatch.setattr(service, "odoo", _fake_odoo)

    first = client.post(
        "/api/v1/webtech-ai-agent",
        json={"message": "lavkush live stock"},
    )
    pending = first.json()["data"]
    assert pending["reply"] == "Kaun sa product? Naam ya SKU likho."

    second = client.post(
        "/api/v1/webtech-ai-agent",
        json={"message": "501", "context": pending["context"]},
    )
    reply = second.json()["data"]["reply"]
    assert "On Hand\n12" in reply
    assert "Reserved\n2" in reply
    assert "Free\n10" in reply
    assert "Incoming\n0" in reply
    assert "Source:" not in reply
    assert "Hona chahiye" not in reply


def test_stock_moves_keep_paging_past_the_old_cutoff(monkeypatch) -> None:
    def fake_odoo(model: str, method: str, payload: dict):
        assert model == "stock.move"
        assert method == "search_read"
        offset = int(payload["offset"])
        limit = int(payload["limit"])
        if offset >= 4000:
            return [{"id": 4001, "date": "2026-10-15 04:30:00"}]
        return [{"id": offset + index} for index in range(limit)]

    monkeypatch.setattr(service, "odoo", fake_odoo)
    rows = service.search_read_all("stock.move", [], ["id", "date"])
    assert rows[-1]["id"] == 4001
    assert rows[-1]["date"].startswith("2026-10-15")


def test_odoo_refuses_create_drop_and_update(monkeypatch) -> None:
    def fail_open(*_args, **_kwargs):
        raise AssertionError("write method must not reach Odoo")

    monkeypatch.setattr(service.urllib.request, "urlopen", fail_open)

    for method in ("create", "write", "unlink", "copy", "drop", "update", "delete"):
        try:
            service.odoo("stock.move", method, {})
        except RuntimeError as exc:
            assert method in str(exc)
        else:
            raise AssertionError(f"{method} was allowed")


def test_parse_bucket_and_october_range() -> None:
    assert service.parse_bucket("rto in transit kitna") == "RTO in transit"
    assert service.parse_bucket("october me deliver hua") == "Delivered"
    assert service.parse_bucket("stock pada hai") == "On hand"
    assert service.parse_range("october 2026") == {"from": "2026-10-01", "to": "2026-10-31"}


def test_customer_delivery_is_classified_delivered() -> None:
    move = {
        "state": "done",
        "location_id": [11, "stock"],
        "location_dest_id": [90, "customers"],
        "origin_returned_move_id": False,
        "origin": "AGRI1",
    }
    bucket = service.classify(move, None, {11: "internal", 90: "customer"}, 11, None)
    assert bucket == "Delivered"
