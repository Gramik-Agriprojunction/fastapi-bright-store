import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.buyer.repository import reset_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_store() -> None:
    reset_store()


def test_dashboard_matches_reliance_fresh() -> None:
    response = client.get("/api/v1/buyer/dashboard")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["buyer_name"] == "Reliance Fresh"
    assert data["stats"] == {
        "incoming": 5,
        "to_receive": 3,
        "received": 28,
        "issues": 1,
    }
    assert [item["id"] for item in data["shipments"]] == [
        "SHIP-2026-00089",
        "SHIP-2026-00090",
        "SHIP-2026-00091",
    ]
    assert data["shipments"][0]["crop"] == "Paddy (PR-126)"


def test_grn_records_shortage_and_claim() -> None:
    created = client.post(
        "/api/v1/buyer/shipments/SHIP-2026-00089/grn",
        json={
            "received_kg": 1720,
            "received_packs": 344,
            "damaged_kg": 30,
            "damaged_packs": 6,
            "shortage_reason": "Moisture damage during transit.",
            "photos": 2,
        },
    )
    assert created.status_code == 200
    grn = created.json()["data"]
    assert grn["id"] == "GRN-2026-000567"
    assert grn["shortage_kg"] == 30
    assert grn["shortage_packs"] == 6

    claim = client.post(
        "/api/v1/buyer/claims",
        json={
            "grn_id": grn["id"],
            "claim_type": "Shortage",
            "claim_qty_kg": 30,
            "description": "Moisture damage during transit.",
            "photos": 1,
        },
    )
    assert claim.status_code == 200
    assert claim.json()["data"]["status"] == "in_review"

    listed = client.get("/api/v1/buyer/claims", params={"tab": "in_review"})
    ids = [item["id"] for item in listed.json()["data"]["items"]]
    assert claim.json()["data"]["id"] in ids


def test_grn_print_matches_odoo_goods_receipt() -> None:
    created = client.post(
        "/api/v1/buyer/shipments/SHIP-2026-00089/grn",
        json={
            "received_kg": 1720,
            "received_packs": 344,
            "damaged_kg": 30,
            "damaged_packs": 6,
            "shortage_reason": "Moisture damage during transit.",
            "photos": 1,
        },
    )
    grn_id = created.json()["data"]["id"]
    response = client.get(f"/api/v1/buyer/grn/{grn_id}/print")

    assert response.status_code == 200
    document = response.json()["data"]
    html = document["html"]
    for label in (
        "Goods Receipt Note",
        "CIN:",
        "Registered Address:",
        "1.Transaction Details",
        "Supply Type Code",
        "Incoming Receipt",
        "Source Document",
        "Reference No",
        "Place of Supply",
        "Document Type",
        "2.Party Details",
        "Location (From):",
        "Location (To):",
        "Shipping Address:",
        "4.Details of Goods / Services",
        "HSN / SAC Code",
        "CGST",
        "SGST",
        "IGST",
        "Shipping Charges",
        "Grand Total",
        "5. HSN/SAC Summary",
        "Printed On",
        "MSME No",
        "Digitally Signed by Gramik",
    ):
        assert label in html
    assert document["transaction"]["document_type"] == "GRN"
    assert document["transaction"]["reference_no"] == grn_id
    assert document["lines"][0]["hsn"]
    assert document["hsn_summary"][0]["total_tax"] > 0
    assert document["shipping_charges"] == 0


def test_trace_pack_from_farm_to_buyer() -> None:
    response = client.get("/api/v1/buyer/lots/PL-260927-000124/trace")

    assert response.status_code == 200
    steps = response.json()["data"]["steps"]
    assert steps[0]["detail"].startswith("Ram Lakhan")
    assert steps[-1]["title"] == "Buyer (You)"

    unknown = client.post(
        "/api/v1/buyer/shipments/SHIP-2026-00089/scan",
        json={"code": "PL-NOT-ON-SHIPMENT"},
    )
    assert unknown.status_code == 400
