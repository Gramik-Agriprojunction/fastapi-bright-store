import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.collection_centre.repository import reset_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_store() -> None:
    reset_store()


def test_expected_deliveries_include_ram_lakhan() -> None:
    response = client.get("/api/v1/collection-centre/deliveries", params={"tab": "expected"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    names = [item["farmer_name"] for item in body["data"]["items"]]
    assert names[0] == "Ram Lakhan"
    assert "Harish Chandra" not in names


def test_gate_weighment_and_receipt() -> None:
    created = client.post(
        "/api/v1/collection-centre/gate-entries",
        json={
            "delivery_id": "del-ram",
            "harvest_lot": "HL-260927-0001",
            "vehicle_number": "UP32AB1234",
            "driver_name": "Ram Lakhan",
        },
    )
    assert created.status_code == 200
    lot_id = created.json()["data"]["lot_id"]

    rejected = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/weighment",
        json={"gross_kg": 300, "tare_kg": 300, "confirm": True},
    )
    assert rejected.status_code == 400

    confirmed = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/weighment",
        json={"gross_kg": 4280, "tare_kg": 380, "confirm": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["net_kg"] == 3900

    received = client.get("/api/v1/collection-centre/deliveries", params={"tab": "received"})
    names = [item["farmer_name"] for item in received.json()["data"]["items"]]
    assert "Ram Lakhan" in names


def test_aggregation_rejects_mixed_crops_and_sums_paddy() -> None:
    tomato = client.post(
        "/api/v1/collection-centre/gate-entries",
        json={
            "delivery_id": "del-sita",
            "harvest_lot": "HL-260927-0008",
            "vehicle_number": "UP32CD7788",
            "driver_name": "Sita Devi",
        },
    )
    tomato_lot = tomato.json()["data"]["lot_id"]
    mixed = client.post(
        "/api/v1/collection-centre/aggregations",
        json={"lot_ids": ["LOT-260927-000101", tomato_lot]},
    )
    assert mixed.status_code == 400

    merged = client.post(
        "/api/v1/collection-centre/aggregations",
        json={"lot_ids": ["LOT-260927-000101", "LOT-260927-000118"]},
    )
    assert merged.status_code == 200
    assert merged.json()["data"]["net_kg"] == 3500


def test_qc_pack_dispatch_grn_and_trace() -> None:
    lot_id = "LOT-260927-000124"
    sent = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/send-to-qc",
        json={"sent_by": "Manoj Verma"},
    )
    assert sent.status_code == 200
    assert sent.json()["data"]["qc_status"] == "Awaiting QC"

    decision = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/qc",
        json={
            "decision": "accept",
            "grade": "A",
            "remarks": "Good quality, clean grains.",
            "parameters": {
                "moisture": 13.2,
                "broken_grains": 2.5,
                "foreign_matter": 1.0,
                "damaged_grain": 1.2,
                "insect_damage": "Not Found",
            },
        },
    )
    assert decision.status_code == 200
    assert decision.json()["data"]["qc_status"] == "Accepted"

    packed = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/packhouse",
        json={"pack_size_kg": 5},
    )
    assert packed.status_code == 200
    pack_lot = packed.json()["data"]["pack_lot_id"]
    assert packed.json()["data"]["pack_count"] == 760

    dispatched = client.post(
        f"/api/v1/collection-centre/packs/{pack_lot}/dispatch",
        json={
            "buyer_name": "Reliance Fresh",
            "buyer_location": "Lucknow",
            "purchase_order": "PO-12345",
            "vehicle_number": "UP78BT1234",
            "driver_name": "Ramesh Yadav",
            "driver_contact": "9876543210",
        },
    )
    assert dispatched.status_code == 200
    shipment_id = dispatched.json()["data"]["shipment_id"]

    grn = client.post(
        f"/api/v1/collection-centre/shipments/{shipment_id}/grn",
        json={
            "received_qty_kg": 3750,
            "accepted_qty_kg": 3750,
            "shortage_kg": 50,
            "damage_kg": 0,
            "condition": "Good",
            "remarks": "Received in good condition. 50 kg shortage.",
        },
    )
    assert grn.status_code == 200
    assert grn.json()["data"]["status"] == "Received"

    trace = client.get(f"/api/v1/collection-centre/trace/{pack_lot}")
    assert trace.status_code == 200
    assert trace.json()["data"]["parent_lot_id"] == lot_id

    journey = client.get(f"/api/v1/collection-centre/lots/{lot_id}/traceability")
    titles = [step["title"] for step in journey.json()["data"]["journey"]]
    assert "QC Accepted" in titles
    assert "Buyer receipt" in titles


def test_lens_board_shows_app_lots() -> None:
    created = client.post(
        "/api/v1/collection-centre/gate-entries",
        json={
            "delivery_id": "del-ram",
            "harvest_lot": "HL-260927-0001",
            "vehicle_number": "UP32AB1234",
            "driver_name": "Ram Lakhan",
        },
    )
    lot_id = created.json()["data"]["lot_id"]
    board = client.get("/api/v1/collection-centre/lens")
    assert board.status_code == 200
    ids = [item["lot_id"] for item in board.json()["data"]["lots"]]
    assert lot_id in ids
    assert board.json()["data"]["qc"]["counts"]["awaiting"] >= 1


def test_qc_queue_sample_hold_reject_and_reinspection() -> None:
    queue = client.get("/api/v1/collection-centre/qc/queue", params={"tab": "awaiting"})
    assert queue.status_code == 200
    ids = [item["lot_id"] for item in queue.json()["data"]["items"]]
    assert "LOT-260927-000210" in ids
    assert queue.json()["data"]["counts"]["hold"] == 1

    lot_id = "LOT-260927-000210"
    sample = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/qc/sample",
        json={
            "sample_type": "Primary Sample",
            "sample_location": "GCC-HAR-001",
            "inspector": "Manoj Verma",
            "remarks": "Representative sample for QC.",
            "photos": ["Sample Photo"],
        },
    )
    assert sample.status_code == 200
    assert sample.json()["data"]["sample_id"].startswith("SMP-")
    assert sample.json()["data"]["qc_status"] == "In Progress"

    missing = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/qc",
        json={"decision": "hold", "remarks": "", "hold_reason": ""},
    )
    assert missing.status_code == 400

    held = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/qc",
        json={
            "decision": "hold",
            "grade": "A",
            "remarks": "Sample sent for pesticide residue test.",
            "hold_reason": "Waiting for Lab Test",
            "follow_up": "Re-test after 24 hours",
            "reinspection_date": "27 Sep 2026",
        },
    )
    assert held.status_code == 200
    assert held.json()["data"]["qc_status"] == "On Hold"

    updated = client.post(
        f"/api/v1/collection-centre/lots/{lot_id}/qc/reinspection",
        json={"result": "accept", "inspector": "Manoj Verma", "remarks": "Within limit."},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["qc_status"] == "Accepted"

    rejected = client.post(
        "/api/v1/collection-centre/lots/LOT-260927-000211/qc",
        json={
            "decision": "reject",
            "reject_reason": "High-damaged fruit (8%). Not meeting grade specification.",
            "remarks": "Blocked",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["qc_status"] == "Rejected"
    assert "grade specification" in rejected.json()["data"]["reject_reason"]


def test_crm_trace_row_opens_farmer_details() -> None:
    from app.modules.collection_centre.crm_trace import apply_trace_row
    from app.modules.collection_centre.repository import CollectionStore
    from app.modules.collection_centre.service import CollectionService

    store = CollectionStore(seed=False)
    apply_trace_row(
        store,
        {
            "harvest_id": 1,
            "status": "delivered",
            "harvest_date": None,
            "expected_yield_kg": 4500,
            "net_weight_kg": 4280,
            "gross_weight_kg": 4280,
            "tare_weight_kg": None,
            "grade": "Grade A",
            "moisture": 13,
            "broken_grains": None,
            "foreign_matter": None,
            "damaged_grain": None,
            "qc_remarks": "",
            "vehicle_number": "",
            "driver_name": "",
            "farmer_name": "VINAY KUMAR",
            "mobile": "9936528145",
            "unique_code": "FA897673",
            "crop_name": "Paddy",
            "land_id": 1945397,
            "centre_name": "Hardoi",
            "village": "Bilgram SO",
            "district": "Hardoi",
            "state_name": "Uttar Pradesh",
            "lot_code": "LOT-261025-000001",
            "quantity_kg": 4280,
            "shipment_code": "",
            "shipment_status": "",
            "shipment_qty": None,
            "shipment_packs": None,
            "po_number": "",
            "buyer_name": "",
        },
    )
    detail = CollectionService(store).get_harvest("LOT-261025-000001")
    assert detail["farmer_name"] == "VINAY KUMAR"
    assert detail["farmer_id"] == "FA897673"
    assert detail["mobile"] == "9936528145"
    assert detail["village"] == "Bilgram SO"
    assert detail["plot"] == "P-1945397"
