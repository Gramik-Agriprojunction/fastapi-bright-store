from dataclasses import dataclass, field


def _pack(code: str, qty_kg: float, packs: int, scanned: bool = True) -> dict:
    return {"code": code, "qty_kg": qty_kg, "packs": packs, "scanned": scanned}


def _event(title: str, time: str, place: str, state: str) -> dict:
    return {"title": title, "time": time, "place": place, "state": state}


@dataclass
class BuyerMeta:
    grn_seq: int = 566
    claim_seq: int = 12
    received_history: int = 28


@dataclass
class BuyerShipment:
    id: str
    status: str
    status_label: str
    buyer_name: str
    buyer_site: str
    po_number: str
    crop: str
    grade: str
    qty_kg: float
    packs: int
    eta_label: str
    dispatched_label: str
    expected_label: str
    vehicle_number: str
    driver_name: str
    route_from: str
    route_to: str
    today: bool = True
    display_order: int = 0
    grn_id: str = ""
    form_received_kg: float = 0
    form_received_packs: int = 0
    form_damaged_kg: float = 0
    form_damaged_packs: int = 0
    form_reason: str = ""
    events: list = field(default_factory=list)
    pack_lines: list = field(default_factory=list)


@dataclass
class BuyerGrn:
    id: str
    shipment_id: str
    po_number: str
    crop: str
    grade: str
    created_label: str
    expected_kg: float
    expected_packs: int
    received_kg: float
    received_packs: int
    damaged_kg: float
    damaged_packs: int
    shortage_kg: float
    shortage_packs: int
    shortage_reason: str
    photos: int = 0


@dataclass
class BuyerClaim:
    id: str
    grn_id: str
    shipment_id: str
    po_number: str
    crop: str
    claim_type: str
    claim_qty_kg: float
    description: str
    status: str
    status_label: str
    opened_label: str
    photos: int = 0


def _showcase() -> tuple[BuyerMeta, dict[str, BuyerShipment], dict[str, BuyerGrn], dict[str, BuyerClaim]]:
    shipments = {
        "SHIP-2026-00089": BuyerShipment(
            id="SHIP-2026-00089",
            status="in_transit",
            status_label="In Transit",
            buyer_name="Reliance Fresh",
            buyer_site="RC Lucknow (DC-01)",
            po_number="PO-12345",
            crop="Paddy (PR-126)",
            grade="Grade A",
            qty_kg=1750,
            packs=350,
            eta_label="ETA 11:30 AM",
            dispatched_label="27 Sep 2026, 10:30 AM",
            expected_label="27 Sep 2026, 11:30 AM",
            vehicle_number="UP78BT1234",
            driver_name="Ramesh Yadav",
            route_from="GCC-HAR-001",
            route_to="RDC Lucknow",
            display_order=1,
            form_received_kg=1720,
            form_received_packs=344,
            form_damaged_kg=30,
            form_damaged_packs=6,
            form_reason="Moisture damage during transit.",
            events=[
                _event("Dispatched", "27 Sep 2026, 02:30 PM", "GCC-HAR-001", "done"),
                _event("In Transit", "27 Sep 2026, 06:15 PM", "Kanpur, UP", "current"),
                _event("Arriving Soon", "28 Sep 2026, 09:10 AM", "Unnao, UP", "upcoming"),
                _event("Delivered", "", "", "pending"),
            ],
            pack_lines=[
                _pack("PL-260927-000124", 500, 100),
                _pack("PL-260927-000125", 500, 100),
                _pack("PL-260927-000126", 750, 150),
            ],
        ),
        "SHIP-2026-00090": BuyerShipment(
            id="SHIP-2026-00090",
            status="arriving",
            status_label="Arriving",
            buyer_name="Reliance Fresh",
            buyer_site="RC Lucknow (DC-01)",
            po_number="PO-12346",
            crop="Tomato",
            grade="Grade A",
            qty_kg=800,
            packs=160,
            eta_label="ETA 02:00 PM",
            dispatched_label="28 Sep 2026, 08:10 AM",
            expected_label="28 Sep 2026, 02:00 PM",
            vehicle_number="UP32CD4410",
            driver_name="Suresh Kumar",
            route_from="GCC-HAR-001",
            route_to="RDC Lucknow",
            display_order=2,
            form_received_kg=800,
            form_received_packs=160,
            events=[
                _event("Dispatched", "28 Sep 2026, 08:10 AM", "GCC-HAR-001", "done"),
                _event("Arriving Soon", "28 Sep 2026, 01:10 PM", "Lucknow outskirts", "current"),
                _event("Delivered", "", "", "pending"),
            ],
            pack_lines=[_pack("PL-260928-000201", 800, 160, scanned=False)],
        ),
        "SHIP-2026-00091": BuyerShipment(
            id="SHIP-2026-00091",
            status="planned",
            status_label="Planned",
            buyer_name="Reliance Fresh",
            buyer_site="RC Lucknow (DC-01)",
            po_number="PO-12347",
            crop="Chilli",
            grade="Grade A",
            qty_kg=500,
            packs=100,
            eta_label="28 Sep 2026",
            dispatched_label="Not dispatched",
            expected_label="28 Sep 2026",
            vehicle_number="—",
            driver_name="—",
            route_from="GCC-HAR-001",
            route_to="RDC Lucknow",
            display_order=3,
            form_received_kg=500,
            form_received_packs=100,
            events=[
                _event("Planned", "28 Sep 2026", "GCC-HAR-001", "current"),
                _event("Dispatched", "", "", "pending"),
                _event("Delivered", "", "", "pending"),
            ],
            pack_lines=[_pack("PL-260928-000210", 500, 100, scanned=False)],
        ),
        "SHIP-2026-00092": BuyerShipment(
            id="SHIP-2026-00092",
            status="in_transit",
            status_label="In Transit",
            buyer_name="Reliance Fresh",
            buyer_site="RC Lucknow (DC-01)",
            po_number="PO-12348",
            crop="Onion",
            grade="Grade A",
            qty_kg=1200,
            packs=240,
            eta_label="29 Sep 2026",
            dispatched_label="28 Sep 2026, 06:00 AM",
            expected_label="29 Sep 2026, 09:00 AM",
            vehicle_number="UP78EF9091",
            driver_name="Manoj Pal",
            route_from="GCC-HAR-001",
            route_to="RDC Lucknow",
            today=False,
            display_order=4,
            form_received_kg=1200,
            form_received_packs=240,
            events=[_event("In Transit", "28 Sep 2026, 06:40 AM", "Kanpur, UP", "current")],
            pack_lines=[_pack("PL-260928-000220", 1200, 240, scanned=False)],
        ),
        "SHIP-2026-00093": BuyerShipment(
            id="SHIP-2026-00093",
            status="planned",
            status_label="Planned",
            buyer_name="Reliance Fresh",
            buyer_site="RC Lucknow (DC-01)",
            po_number="PO-12349",
            crop="Potato",
            grade="Grade B",
            qty_kg=900,
            packs=180,
            eta_label="30 Sep 2026",
            dispatched_label="Not dispatched",
            expected_label="30 Sep 2026",
            vehicle_number="—",
            driver_name="—",
            route_from="GCC-HAR-001",
            route_to="RDC Lucknow",
            today=False,
            display_order=5,
            form_received_kg=900,
            form_received_packs=180,
            events=[_event("Planned", "30 Sep 2026", "GCC-HAR-001", "current")],
            pack_lines=[_pack("PL-260930-000230", 900, 180, scanned=False)],
        ),
    }
    claims = {
        "CLM-2026-00012": BuyerClaim(
            id="CLM-2026-00012",
            grn_id="GRN-2026-000567",
            shipment_id="SHIP-2026-00089",
            po_number="PO-12345",
            crop="Paddy (PR-126)",
            claim_type="Shortage",
            claim_qty_kg=20,
            description="Shortage against expected packs.",
            status="in_review",
            status_label="In Review",
            opened_label="28 Sep 2026",
        ),
        "CLM-2026-00011": BuyerClaim(
            id="CLM-2026-00011",
            grn_id="GRN-2026-000552",
            shipment_id="SHIP-2026-00080",
            po_number="PO-12340",
            crop="Tomato",
            claim_type="Damage",
            claim_qty_kg=20,
            description="Packs damaged in transit.",
            status="received",
            status_label="Received",
            opened_label="27 Sep 2026",
        ),
        "CLM-2026-00010": BuyerClaim(
            id="CLM-2026-00010",
            grn_id="GRN-2026-000540",
            shipment_id="SHIP-2026-00071",
            po_number="PO-12331",
            crop="Paddy (PR-126)",
            claim_type="Quality Issue",
            claim_qty_kg=15,
            description="Quality issue on received lot.",
            status="closed",
            status_label="Closed",
            opened_label="26 Sep 2026",
        ),
        "CLM-2026-00009": BuyerClaim(
            id="CLM-2026-00009",
            grn_id="GRN-2026-000530",
            shipment_id="SHIP-2026-00066",
            po_number="PO-12322",
            crop="Chilli",
            claim_type="Shortage",
            claim_qty_kg=15,
            description="Short receipt closed.",
            status="closed",
            status_label="Closed",
            opened_label="25 Sep 2026",
        ),
    }
    return BuyerMeta(), shipments, {}, claims


class BuyerStore:
    def __init__(self, seed: bool = True) -> None:
        self.meta = BuyerMeta()
        self.shipments: dict[str, BuyerShipment] = {}
        self.grns: dict[str, BuyerGrn] = {}
        self.claims: dict[str, BuyerClaim] = {}
        if seed:
            self.reset()

    def reset(self) -> None:
        meta, shipments, grns, claims = _showcase()
        self.meta = meta
        self.shipments = shipments
        self.grns = grns
        self.claims = claims

    def next_grn_id(self) -> str:
        self.meta.grn_seq += 1
        return f"GRN-2026-{self.meta.grn_seq:06d}"

    def next_claim_id(self) -> str:
        self.meta.claim_seq += 1
        return f"CLM-2026-{self.meta.claim_seq:05d}"


_store = BuyerStore()


def get_store() -> BuyerStore:
    return _store


def reset_store() -> None:
    _store.reset()
