from dataclasses import asdict

from app.modules.buyer.errors import BuyerError
from app.modules.buyer.grn_print import build_grn_print
from app.modules.buyer.repository import BuyerClaim, BuyerGrn, BuyerShipment, BuyerStore
from app.modules.buyer.schemas import ClaimIn, GrnIn

_TRACE_CODE = "PL-260927-000124"
_CREATED = "28 Sep 2026, 11:20 AM"


def _matches(query: str, *parts: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    haystack = " ".join(parts).lower()
    return needle in haystack


class BuyerService:
    def __init__(self, store: BuyerStore) -> None:
        self.store = store

    def _shipment(self, shipment_id: str) -> BuyerShipment:
        ship = self.store.shipments.get(shipment_id)
        if ship is None:
            raise BuyerError("Shipment not found", 404)
        return ship

    def _card(self, ship: BuyerShipment) -> dict:
        return {
            "id": ship.id,
            "status": ship.status,
            "status_label": ship.status_label,
            "buyer_name": ship.buyer_name,
            "buyer_site": ship.buyer_site,
            "po_number": ship.po_number,
            "crop": ship.crop,
            "grade": ship.grade,
            "qty_kg": ship.qty_kg,
            "packs": ship.packs,
            "eta_label": ship.eta_label,
        }

    def dashboard(self, query: str) -> dict:
        today = [
            ship
            for ship in self.store.shipments.values()
            if ship.today
            and _matches(query, ship.id, ship.crop, ship.po_number, ship.status_label)
        ]
        today.sort(key=lambda ship: ship.display_order)
        incoming = sum(1 for ship in self.store.shipments.values() if ship.status != "received")
        to_receive = sum(
            1 for ship in self.store.shipments.values() if ship.today and ship.status != "received"
        )
        received = self.store.meta.received_history + sum(
            1 for ship in self.store.shipments.values() if ship.status == "received"
        )
        issues = sum(1 for claim in self.store.claims.values() if claim.status == "in_review")
        return {
            "buyer_name": "Reliance Fresh",
            "buyer_site": "RC Lucknow (DC-01)",
            "welcome": "Welcome",
            "section": "Purchase & Receiving",
            "stats": {
                "incoming": incoming,
                "to_receive": to_receive,
                "received": received,
                "issues": issues,
            },
            "shipments": [self._card(ship) for ship in today],
        }

    def shipment(self, shipment_id: str) -> dict:
        ship = self._shipment(shipment_id)
        data = asdict(ship)
        data.pop("pack_lines", None)
        data.pop("events", None)
        return data

    def tracking(self, shipment_id: str) -> dict:
        ship = self._shipment(shipment_id)
        return {
            "id": ship.id,
            "status": ship.status,
            "status_label": ship.status_label,
            "route_from": ship.route_from,
            "route_to": ship.route_to,
            "map_from": "Kanpur",
            "map_to": "Lucknow",
            "events": ship.events,
        }

    def receive(self, shipment_id: str) -> dict:
        ship = self._shipment(shipment_id)
        scanned = [line for line in ship.pack_lines if line["scanned"]]
        scanned_kg = sum(line["qty_kg"] for line in scanned)
        scanned_packs = sum(line["packs"] for line in scanned)
        return {
            "id": ship.id,
            "crop": ship.crop,
            "po_number": ship.po_number,
            "grade": ship.grade,
            "expected_kg": ship.qty_kg,
            "expected_packs": ship.packs,
            "scanned_kg": scanned_kg,
            "scanned_packs": scanned_packs,
            "lines": ship.pack_lines,
            "form": {
                "received_kg": ship.form_received_kg,
                "received_packs": ship.form_received_packs,
                "damaged_kg": ship.form_damaged_kg,
                "damaged_packs": ship.form_damaged_packs,
                "shortage_reason": ship.form_reason,
            },
        }

    def scan(self, shipment_id: str, code: str) -> dict:
        ship = self._shipment(shipment_id)
        token = code.strip().upper()
        match = next((line for line in ship.pack_lines if line["code"].upper() == token), None)
        if match is None:
            raise BuyerError("Pack is not on this shipment")
        match["scanned"] = True
        return self.receive(shipment_id)

    def submit_grn(self, shipment_id: str, payload: GrnIn) -> dict:
        ship = self._shipment(shipment_id)
        if ship.grn_id:
            return self.grn(ship.grn_id)
        shortage_kg = round(ship.qty_kg - payload.received_kg, 2)
        shortage_packs = ship.packs - payload.received_packs
        if shortage_kg < 0 or shortage_packs < 0:
            raise BuyerError("Received quantity cannot exceed the shipment")
        grn_id = self.store.next_grn_id()
        grn = BuyerGrn(
            id=grn_id,
            shipment_id=ship.id,
            po_number=ship.po_number,
            crop=ship.crop,
            grade=ship.grade,
            created_label=_CREATED,
            expected_kg=ship.qty_kg,
            expected_packs=ship.packs,
            received_kg=payload.received_kg,
            received_packs=payload.received_packs,
            damaged_kg=payload.damaged_kg,
            damaged_packs=payload.damaged_packs,
            shortage_kg=shortage_kg,
            shortage_packs=shortage_packs,
            shortage_reason=payload.shortage_reason.strip(),
            photos=payload.photos,
        )
        self.store.grns[grn_id] = grn
        ship.grn_id = grn_id
        ship.status = "received"
        ship.status_label = "Received"
        return asdict(grn)

    def grn(self, grn_id: str) -> dict:
        grn = self.store.grns.get(grn_id)
        if grn is None:
            raise BuyerError("GRN not found", 404)
        return asdict(grn)

    def grn_print(self, grn_id: str) -> dict:
        grn = self.store.grns.get(grn_id)
        if grn is None:
            raise BuyerError("GRN not found", 404)
        return build_grn_print(grn, self._shipment(grn.shipment_id))

    def receipts(self, query: str) -> dict:
        rows = [
            self.grn(grn.id)
            for grn in self.store.grns.values()
            if _matches(query, grn.id, grn.shipment_id, grn.po_number, grn.crop)
        ]
        rows.sort(key=lambda item: item["id"], reverse=True)
        return {"items": rows}

    def purchase_orders(self, query: str) -> dict:
        rows = []
        for ship in sorted(self.store.shipments.values(), key=lambda item: item.display_order):
            if not _matches(query, ship.po_number, ship.crop, ship.id):
                continue
            rows.append(
                {
                    "po_number": ship.po_number,
                    "shipment_id": ship.id,
                    "crop": ship.crop,
                    "grade": ship.grade,
                    "qty_kg": ship.qty_kg,
                    "packs": ship.packs,
                    "status": ship.status,
                    "status_label": ship.status_label,
                }
            )
        return {"items": rows}

    def create_claim(self, payload: ClaimIn) -> dict:
        grn = self.store.grns.get(payload.grn_id)
        ship = self.store.shipments.get(grn.shipment_id) if grn else None
        if grn is None and payload.grn_id != "GRN-2026-000567":
            raise BuyerError("GRN not found", 404)
        claim_id = self.store.next_claim_id()
        claim = BuyerClaim(
            id=claim_id,
            grn_id=payload.grn_id,
            shipment_id=ship.id if ship else "SHIP-2026-00089",
            po_number=ship.po_number if ship else "PO-12345",
            crop=ship.crop if ship else "Paddy (PR-126)",
            claim_type=payload.claim_type,
            claim_qty_kg=payload.claim_qty_kg,
            description=payload.description.strip(),
            status="in_review",
            status_label="In Review",
            opened_label="28 Sep 2026",
            photos=payload.photos,
        )
        self.store.claims[claim_id] = claim
        return asdict(claim)

    def claims(self, tab: str, query: str) -> dict:
        def visible(claim: BuyerClaim) -> bool:
            if tab == "open":
                return claim.status in {"in_review", "received"}
            if tab == "in_review":
                return claim.status == "in_review"
            if tab == "closed":
                return claim.status == "closed"
            return True

        items = [
            asdict(claim)
            for claim in self.store.claims.values()
            if visible(claim)
            and _matches(query, claim.id, claim.grn_id, claim.crop, claim.claim_type, claim.po_number)
        ]
        items.sort(key=lambda item: item["id"], reverse=True)
        counts = {
            "all": len(self.store.claims),
            "open": sum(1 for claim in self.store.claims.values() if claim.status in {"in_review", "received"}),
            "in_review": sum(1 for claim in self.store.claims.values() if claim.status == "in_review"),
            "closed": sum(1 for claim in self.store.claims.values() if claim.status == "closed"),
        }
        return {"counts": counts, "items": items}

    def trace(self, code: str) -> dict:
        if code.strip().upper() != _TRACE_CODE:
            raise BuyerError("Lot not found", 404)
        return {
            "code": _TRACE_CODE,
            "crop": "Paddy (PR-126)",
            "grade": "Grade A",
            "status": "received",
            "status_label": "Received",
            "qty_label": "500 Kg · 100 Packs",
            "steps": [
                {"title": "Farm", "detail": "Ram Lakhan · Hardoi, UP", "when": "Harvest 26 Sep 2026"},
                {"title": "Collection Centre", "detail": "GCC-HAR-001", "when": "Received 26 Sep 2026"},
                {"title": "QC & Grading", "detail": "Grade A · 100 packs", "when": "26 Sep 2026"},
                {"title": "Aggregation", "detail": "AGG-260926-000045", "when": "26 Sep 2026"},
                {"title": "Packhouse", "detail": "PL-260927-000124", "when": "Harvested 26 Sep 2026"},
                {"title": "Dispatch", "detail": "SHIP-2026-00089", "when": "27 Sep 2026"},
                {"title": "Buyer (You)", "detail": "Reliance Fresh · RC Lucknow", "when": "28 Sep 2026"},
            ],
        }

    def genealogy(self, code: str) -> dict:
        if code.strip().upper() != _TRACE_CODE:
            raise BuyerError("Lot not found", 404)
        return {
            "code": _TRACE_CODE,
            "aggregation": {
                "code": "AGG-260926-000045",
                "crop": "Paddy (PR-126)",
                "qty_kg": 7400,
                "grade": "Grade A",
            },
            "parents": [
                {"code": "PL-260926-000140", "qty_kg": 2000, "packs": 400},
                {"code": "PL-260926-000141", "qty_kg": 2400, "packs": 480},
                {"code": "PL-260926-000142", "qty_kg": 3000, "packs": 600},
            ],
            "children": [
                {"code": "PL-260927-000124", "qty_kg": 500, "packs": 100},
                {"code": "PL-260927-000125", "qty_kg": 1000, "packs": 200},
                {"code": "PL-260927-000126", "qty_kg": 250, "packs": 50},
            ],
        }

    def quality_documents(self, shipment_id: str) -> dict:
        self._shipment(shipment_id)
        return {
            "shipment_id": shipment_id,
            "items": [
                {"id": "qc", "title": "QC Report", "code": "QC-260926-001124", "date": "26 Sep 2026", "size": "186 KB"},
                {"id": "lab", "title": "Lab Test Report", "code": "LAB-260926-001124", "date": "26 Sep 2026", "size": "240 KB"},
                {"id": "certificate", "title": "Quality Certificate", "code": "CERT-260926-001124", "date": "26 Sep 2026", "size": "128 KB"},
            ],
        }

    def documents(self, shipment_id: str) -> dict:
        ship = self._shipment(shipment_id)
        return {
            "shipment_id": ship.id,
            "items": [
                {"id": "invoice", "title": "Invoice", "code": "INV-2026-00089", "size": "320 KB"},
                {"id": "eway", "title": "E-Way Bill", "code": "EWB-2026-00089", "size": "280 KB"},
                {"id": "challan", "title": "Transporter Challan", "code": "CH-2026-00089", "size": "190 KB"},
                {"id": "certificate", "title": "Quality Certificate", "code": "CERT-260926-00124", "size": "128 KB"},
                {"id": "grn", "title": "GRN", "code": ship.grn_id or "GRN-2026-000567", "size": "210 KB"},
                {"id": "pod", "title": "POD Photo", "code": "POD-2026-00089", "size": "240 KB"},
            ],
        }
