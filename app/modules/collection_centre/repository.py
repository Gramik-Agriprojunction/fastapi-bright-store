"""In-memory collection centre store.

Seeded with the Collection Centre reference flow so every screen has data
before a live intake is recorded. Swap this repository for SQLAlchemy when
the Lens database schema is ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def format_when(value: datetime) -> str:
    day = value.strftime("%d").lstrip("0")
    clock = value.strftime("%I:%M %p").lstrip("0")
    return f"{day} {value.strftime('%b %Y')}, {clock}"


def now_label() -> str:
    return format_when(datetime.now(IST))


@dataclass
class Delivery:
    id: str
    farmer_name: str
    crop: str
    expected_qty_kg: float
    arrival_label: str
    status: str
    centre: str = "GCC-HAR-001"
    farmer_id: str = ""
    village: str = ""
    district: str = ""
    plot: str = ""
    harvest_date: str = ""
    harvest_lot: str = ""
    received_qty_kg: float | None = None
    mobile: str = ""


@dataclass
class JourneyEvent:
    title: str
    detail: str
    at: str
    state: str = "done"


@dataclass
class Lot:
    id: str
    harvest_lot: str
    farmer_name: str
    farmer_id: str
    village: str
    district: str
    crop: str
    plot: str
    harvest_date: str
    expected_qty_kg: float
    centre: str
    status: str
    grade: str = "A"
    gross_kg: float | None = None
    tare_kg: float | None = None
    net_kg: float | None = None
    vehicle_number: str = ""
    driver_name: str = ""
    created_at: str = ""
    delivery_id: str | None = None
    source_lot_ids: list[str] = field(default_factory=list)
    qc_status: str = ""
    sent_by: str = ""
    sent_at: str = ""
    qc_parameters: dict[str, object] = field(default_factory=dict)
    qc_remarks: str = ""
    qc_decided_at: str = ""
    sample_id: str = ""
    sample_type: str = "Primary Sample"
    sample_location: str = ""
    sample_date: str = ""
    inspector: str = "Manoj Verma"
    sample_remarks: str = ""
    qc_photos: list[str] = field(default_factory=list)
    qc_documents: list[dict[str, str]] = field(default_factory=list)
    hold_reason: str = ""
    follow_up: str = ""
    reinspection_date: str = ""
    reject_reason: str = ""
    lab_name: str = ""
    lab_test_type: str = ""
    lab_sample_id: str = ""
    lab_expected_date: str = ""
    lab_result: str = ""
    lab_report_name: str = ""
    pack_lot_id: str = ""
    pack_size_kg: float | None = None
    packed_qty_kg: float | None = None
    pack_count: int | None = None
    shipment_id: str = ""
    journey: list[JourneyEvent] = field(default_factory=list)


@dataclass
class Shipment:
    id: str
    pack_lot_id: str
    lot_id: str
    buyer_name: str
    buyer_location: str
    purchase_order: str
    vehicle_number: str
    driver_name: str
    driver_contact: str
    qty_kg: float
    pack_count: int
    crop: str
    grade: str
    status: str
    dispatched_at: str
    from_centre: str
    received_qty_kg: float | None = None
    accepted_qty_kg: float | None = None
    shortage_kg: float | None = None
    damage_kg: float | None = None
    condition: str = ""
    remarks: str = ""
    received_at: str = ""


def _showcase() -> tuple[dict[str, Delivery], dict[str, Lot], dict[str, Shipment]]:
    deliveries = {
        "del-ram": Delivery(
            id="del-ram",
            farmer_name="Ram Lakhan",
            crop="Paddy (PR-126)",
            expected_qty_kg=4000,
            arrival_label="Today, 10:00 AM",
            status="arriving",
            farmer_id="FA643895",
            village="Lakhan Pandey",
            district="Hardoi, UP",
            plot="P-001",
            harvest_date="24 Sep 2026",
            harvest_lot="HL-260927-0001",
        ),
        "del-sita": Delivery(
            id="del-sita",
            farmer_name="Sita Devi",
            crop="Tomato",
            expected_qty_kg=1200,
            arrival_label="Today, 11:30 AM",
            status="upcoming",
            farmer_id="FA220184",
            village="Sandila",
            district="Hardoi, UP",
            plot="P-014",
            harvest_date="27 Sep 2026",
            harvest_lot="HL-260927-0008",
        ),
        "del-ramesh": Delivery(
            id="del-ramesh",
            farmer_name="Ramesh Yadav",
            crop="Chilli",
            expected_qty_kg=800,
            arrival_label="Today, 02:00 PM",
            status="upcoming",
            farmer_id="FA118902",
            village="Baghauli",
            district="Hardoi, UP",
            plot="P-022",
            harvest_date="26 Sep 2026",
            harvest_lot="HL-260927-0014",
        ),
        "del-mohan": Delivery(
            id="del-mohan",
            farmer_name="Mohan Singh",
            crop="Paddy (PR-126)",
            expected_qty_kg=3200,
            arrival_label="Today, 04:30 PM",
            status="upcoming",
            farmer_id="FA552010",
            village="Pali",
            district="Hardoi, UP",
            plot="P-009",
            harvest_date="25 Sep 2026",
            harvest_lot="HL-260927-0019",
        ),
        "del-harish": Delivery(
            id="del-harish",
            farmer_name="Harish Chandra",
            crop="Wheat",
            expected_qty_kg=2400,
            arrival_label="Yesterday, 04:10 PM",
            status="received",
            farmer_id="FA100221",
            village="Mallawan",
            district="Hardoi, UP",
            plot="P-003",
            harvest_date="20 Sep 2026",
            harvest_lot="HL-260926-0004",
            received_qty_kg=2360,
        ),
    }

    def paddy_lot(
        lot_id: str,
        qty: float,
        *,
        status: str,
        farmer: str = "Ram Lakhan",
    ) -> Lot:
        return Lot(
            id=lot_id,
            harvest_lot="HL-260927-0001",
            farmer_name=farmer,
            farmer_id="FA643895",
            village="Lakhan Pandey",
            district="Hardoi, UP",
            crop="Paddy (PR-126)",
            plot="P-001",
            harvest_date="24 Sep 2026",
            expected_qty_kg=qty,
            centre="GCC-HAR-001",
            status=status,
            grade="A",
            gross_kg=qty + 380,
            tare_kg=380,
            net_kg=qty,
            created_at="28 Sep 2026, 10:30 AM",
        )

    journey = [
        JourneyEvent("Harvest", "Plot P-001 · Ram Lakhan", "24 Sep 2026", "done"),
        JourneyEvent(
            "Received at Collection Centre",
            "GCC-HAR-001 · 3,900 Kg",
            "27 Sep 2026",
            "done",
        ),
        JourneyEvent("QC Accepted", "Grade A", "27 Sep 2026", "done"),
        JourneyEvent(
            "Dispatched",
            "SHP-2026-000089 · Reliance Fresh",
            "28 Sep 2026",
            "done",
        ),
        JourneyEvent("In Transit", "Vehicle UP78BT1234", "28 Sep 2026", "current"),
        JourneyEvent(
            "Delivered (Expected)",
            "Reliance Fresh, Lucknow",
            "28 Sep 2026",
            "upcoming",
        ),
    ]
    showcase = paddy_lot("LOT-260927-000124", 3900, status="dispatched")
    showcase.gross_kg = 4280
    showcase.tare_kg = 380
    showcase.net_kg = 3900
    showcase.qc_status = "Accepted"
    showcase.sent_by = "Manoj Verma"
    showcase.sent_at = "28 Sep 2026, 10:40 AM"
    showcase.qc_decided_at = "27 Sep 2026"
    showcase.qc_parameters = {
        "moisture": 13.2,
        "broken_grains": 2.5,
        "foreign_matter": 1.0,
        "damaged_grain": 1.2,
        "insect_damage": "Not Found",
    }
    showcase.qc_remarks = "Good quality, clean grains."
    showcase.pack_lot_id = "PL-260927-000124"
    showcase.pack_size_kg = 5
    showcase.packed_qty_kg = 3800
    showcase.pack_count = 760
    showcase.shipment_id = "SHP-2026-000089"
    showcase.journey = journey

    lots = {
        "LOT-260927-000101": paddy_lot("LOT-260927-000101", 1500, status="receipt", farmer="Sita Devi"),
        "LOT-260927-000118": paddy_lot("LOT-260927-000118", 2000, status="receipt"),
        "LOT-260927-000134": paddy_lot("LOT-260927-000134", 3900, status="receipt"),
        "LOT-260927-000150": paddy_lot(
            "LOT-260927-000150",
            1800,
            status="receipt",
            farmer="Mohan Singh",
        ),
        showcase.id: showcase,
        "LOT-260927-000210": Lot(
            id="LOT-260927-000210",
            harvest_lot="HL-260927-0001",
            farmer_name="Ram Lakhan",
            farmer_id="FA643895",
            village="Lakhan Pandey",
            district="Hardoi, UP",
            crop="Paddy (PR-126)",
            plot="P-001",
            harvest_date="24 Sep 2026",
            expected_qty_kg=3900,
            centre="GCC-HAR-001",
            status="qc_queue",
            grade="A",
            net_kg=3900,
            created_at="26 Sep 2026, 11:00 AM",
            qc_status="Awaiting QC",
            inspector="Manoj Verma",
            sample_location="GCC-HAR-001",
        ),
        "LOT-260927-000211": Lot(
            id="LOT-260927-000211",
            harvest_lot="HL-260927-0008",
            farmer_name="Sita Devi",
            farmer_id="FA220184",
            village="Sandila",
            district="Hardoi, UP",
            crop="Tomato",
            plot="P-014",
            harvest_date="26 Sep 2026",
            expected_qty_kg=2500,
            centre="GCC-HAR-001",
            status="qc_queue",
            grade="A",
            net_kg=2500,
            created_at="26 Sep 2026, 11:00 AM",
            qc_status="Awaiting QC",
            inspector="Manoj Verma",
        ),
        "LOT-260927-000119": Lot(
            id="LOT-260927-000119",
            harvest_lot="HL-260927-0014",
            farmer_name="Ramesh Yadav",
            farmer_id="FA118902",
            village="Baghauli",
            district="Hardoi, UP",
            crop="Chilli",
            plot="P-022",
            harvest_date="26 Sep 2026",
            expected_qty_kg=1800,
            centre="GCC-HAR-001",
            status="qc_progress",
            grade="A",
            net_kg=1800,
            created_at="26 Sep 2026, 08:45 AM",
            qc_status="In Progress",
            sample_id="SMP-260927-000119",
            sample_type="Primary Sample",
            sample_location="GCC-HAR-001",
            sample_date="26 Sep 2026, 09:10 AM",
            inspector="Manoj Verma",
            qc_photos=["Sample Photo", "Grain Closeup"],
        ),
        "LOT-260927-000120": Lot(
            id="LOT-260927-000120",
            harvest_lot="HL-260927-0019",
            farmer_name="Mohan Singh",
            farmer_id="FA552010",
            village="Pali",
            district="Hardoi, UP",
            crop="Paddy (PR-126)",
            plot="P-009",
            harvest_date="25 Sep 2026",
            expected_qty_kg=2200,
            centre="GCC-HAR-001",
            status="qc_hold",
            grade="B",
            net_kg=2200,
            created_at="26 Sep 2026, 04:20 PM",
            qc_status="On Hold",
            sample_id="SMP-260927-000018",
            sample_date="26 Sep 2026",
            inspector="Manoj Verma",
            hold_reason="Waiting for Lab Test",
            follow_up="Re-test after 24 hours",
            reinspection_date="27 Sep 2026",
            qc_remarks="Sample sent for pesticide residue test.",
            lab_name="Agri Testing Lab",
            lab_test_type="Pesticide Residue",
            lab_result="",
        ),
    }
    lots["LOT-260927-000101"].farmer_id = "FA220184"
    shipment = Shipment(
        id="SHP-2026-000089",
        pack_lot_id="PL-260927-000124",
        lot_id=showcase.id,
        buyer_name="Reliance Fresh",
        buyer_location="Lucknow",
        purchase_order="PO-12345",
        vehicle_number="UP78BT1234",
        driver_name="Ramesh Yadav",
        driver_contact="9876543210",
        qty_kg=3800,
        pack_count=760,
        crop="Paddy (PR-126)",
        grade="A",
        status="in_transit",
        dispatched_at="28 Sep 2026, 02:40 PM",
        from_centre="GCC-HAR-001",
        received_qty_kg=3750,
        accepted_qty_kg=3750,
        shortage_kg=50,
        damage_kg=0,
        condition="Good",
        remarks="Received in good condition. 50 kg shortage.",
    )
    return deliveries, lots, {"SHP-2026-000089": shipment}


class CollectionStore:
    def __init__(self, *, seed: bool = True) -> None:
        if seed:
            self.reset()
        else:
            self.deliveries = {}
            self.lots = {}
            self.shipments = {}
            self._lot_seq = 200
            self._pack_seq = 200
            self._ship_seq = 90
            self._sample_seq = 18

    def reset(self) -> None:
        deliveries, lots, shipments = _showcase()
        self.deliveries = deliveries
        self.lots = lots
        self.shipments = shipments
        self._lot_seq = 200
        self._pack_seq = 200
        self._ship_seq = 90
        self._sample_seq = 18

    def next_lot_id(self) -> str:
        self._lot_seq += 1
        return f"LOT-260928-{self._lot_seq:06d}"

    def next_pack_id(self) -> str:
        self._pack_seq += 1
        return f"PL-260928-{self._pack_seq:06d}"

    def next_shipment_id(self) -> str:
        self._ship_seq += 1
        return f"SHP-2026-{self._ship_seq:06d}"

    def next_sample_id(self) -> str:
        self._sample_seq += 1
        return f"SMP-260927-{self._sample_seq:06d}"

    def sync_sequences(self) -> None:
        for lot_id in self.lots:
            if lot_id.startswith("LOT-260928-"):
                self._lot_seq = max(self._lot_seq, int(lot_id.rsplit("-", 1)[-1]))
            lot = self.lots[lot_id]
            pack_id = lot.pack_lot_id
            if pack_id.startswith("PL-260928-"):
                self._pack_seq = max(self._pack_seq, int(pack_id.rsplit("-", 1)[-1]))
        for shipment_id in self.shipments:
            if shipment_id.startswith("SHP-2026-"):
                self._ship_seq = max(self._ship_seq, int(shipment_id.rsplit("-", 1)[-1]))


_store = CollectionStore()


def get_store() -> CollectionStore:
    return _store


def reset_store() -> None:
    _store.reset()


