from __future__ import annotations

from app.modules.collection_centre.errors import CollectionError
from app.modules.collection_centre.repository import (
    CollectionStore,
    Delivery,
    JourneyEvent,
    Lot,
    Shipment,
    get_store,
    now_label,
)
from app.modules.collection_centre.schemas import (
    AggregationIn,
    DispatchIn,
    GateEntryIn,
    GrnIn,
    PackhouseIn,
    QcDecisionIn,
    QcDocumentsIn,
    QcInspectionIn,
    QcLabIn,
    QcReinspectIn,
    QcSampleIn,
    SendToQcIn,
    WeighmentIn,
)


def _kg(value: float | None) -> float:
    return float(value or 0)


def _variety(crop: str) -> str:
    if "(" in crop and ")" in crop:
        return crop.split("(", 1)[1].split(")", 1)[0]
    return crop


class CollectionService:
    def __init__(self, store: CollectionStore | None = None) -> None:
        self.store = store or get_store()

    def list_deliveries(self, tab: str = "expected", q: str = "") -> dict[str, object]:
        tab = tab if tab in {"expected", "received", "all"} else "expected"
        query = q.strip().lower()
        items = []
        for delivery in self.store.deliveries.values():
            if query and query not in f"{delivery.farmer_name} {delivery.crop}".lower():
                continue
            if tab == "expected" and delivery.status == "received":
                continue
            if tab == "received" and delivery.status != "received":
                continue
            items.append(self._delivery_card(delivery))
        counts = {"expected": 0, "received": 0, "all": len(self.store.deliveries)}
        for delivery in self.store.deliveries.values():
            if delivery.status == "received":
                counts["received"] += 1
            else:
                counts["expected"] += 1
        return {
            "centre_name": "Collection Centre",
            "tab": tab,
            "counts": counts,
            "items": items,
        }

    def get_harvest(self, code: str) -> dict[str, object]:
        delivery = self._delivery_by_harvest(code)
        if delivery is None:
            raise CollectionError("Harvest lot not found")
        return self._delivery_detail(delivery)

    def create_gate_entry(self, payload: GateEntryIn) -> dict[str, object]:
        delivery = None
        if payload.delivery_id:
            delivery = self.store.deliveries.get(payload.delivery_id)
            if delivery is None:
                raise CollectionError("Delivery not found", 404)
        else:
            delivery = self._delivery_by_harvest(payload.harvest_lot)
        if delivery is None:
            raise CollectionError("Harvest lot not found")
        if delivery.harvest_lot and delivery.harvest_lot != payload.harvest_lot.strip():
            raise CollectionError("Harvest lot does not match this delivery")
        now = now_label()
        lot = Lot(
            id=self.store.next_lot_id(),
            harvest_lot=payload.harvest_lot.strip(),
            farmer_name=delivery.farmer_name,
            farmer_id=delivery.farmer_id,
            village=delivery.village,
            district=delivery.district,
            crop=delivery.crop,
            plot=delivery.plot,
            harvest_date=delivery.harvest_date,
            expected_qty_kg=delivery.expected_qty_kg,
            centre=delivery.centre,
            status="gate",
            vehicle_number=payload.vehicle_number.strip(),
            driver_name=payload.driver_name.strip(),
            created_at=now,
            delivery_id=delivery.id,
            journey=[
                JourneyEvent(
                    "Harvest",
                    f"Plot {delivery.plot} · {delivery.farmer_name}",
                    delivery.harvest_date,
                ),
                JourneyEvent("Gate entry", payload.vehicle_number.strip(), now, "current"),
            ],
        )
        self.store.lots[lot.id] = lot
        return self._lot_brief(lot)

    def get_weighment(self, lot_id: str) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        return {
            **self._lot_brief(lot),
            "gross_kg": lot.gross_kg if lot.gross_kg is not None else 4280,
            "tare_kg": lot.tare_kg if lot.tare_kg is not None else 380,
            "net_kg": lot.net_kg,
        }

    def save_weighment(self, lot_id: str, payload: WeighmentIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        if payload.tare_kg >= payload.gross_kg:
            raise CollectionError("Tare weight must be less than gross weight")
        lot.gross_kg = payload.gross_kg
        lot.tare_kg = payload.tare_kg
        lot.net_kg = round(payload.gross_kg - payload.tare_kg, 2)
        if payload.confirm:
            lot.status = "receipt"
            lot.created_at = now_label()
            self._mark_delivery_received(lot)
            self._push_journey(lot, "Weighment", f"Net {lot.net_kg:g} Kg", "done")
            self._push_journey(lot, "Receipt created", lot.id, "current")
        return self.receipt(lot.id)

    def receipt(self, lot_id: str) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        return {
            **self._lot_brief(lot),
            "gross_kg": lot.gross_kg,
            "tare_kg": lot.tare_kg,
            "net_kg": lot.net_kg,
            "received_at": lot.created_at,
        }

    def aggregation_candidates(self, focus_lot_id: str | None = None) -> dict[str, object]:
        focus = self.store.lots.get(focus_lot_id) if focus_lot_id else None
        items = []
        for lot in self.store.lots.values():
            if lot.pack_lot_id:
                continue
            if lot.status not in {"receipt", "gate", "weighed"} and lot.id != focus_lot_id:
                continue
            selected = lot.id in {"LOT-260927-000101", "LOT-260927-000118"}
            if focus and lot.id == focus.id:
                selected = True
            items.append(
                {
                    "lot_id": lot.id,
                    "qty_kg": _kg(lot.net_kg or lot.expected_qty_kg),
                    "grade": lot.grade,
                    "crop": lot.crop,
                    "selected": selected,
                }
            )
        return {
            "items": items,
            "checks": [
                "Same crop (Paddy)",
                "Same variety (PR-126)",
                "Same grade (A)",
                "All lots are not already packed",
            ],
        }

    def create_aggregation(self, payload: AggregationIn) -> dict[str, object]:
        lots = [self._require_lot(lot_id) for lot_id in payload.lot_ids]
        crop = lots[0].crop
        grade = lots[0].grade
        for lot in lots:
            if lot.crop != crop or _variety(lot.crop) != _variety(crop):
                raise CollectionError("Lots must be the same crop and variety")
            if lot.grade != grade:
                raise CollectionError("Lots must be the same grade")
            if lot.pack_lot_id:
                raise CollectionError(f"{lot.id} is already packed")
        total = round(sum(_kg(lot.net_kg or lot.expected_qty_kg) for lot in lots), 2)
        now = now_label()
        merged = Lot(
            id=self.store.next_lot_id(),
            harvest_lot=lots[0].harvest_lot,
            farmer_name="Multiple farmers",
            farmer_id="",
            village=lots[0].village,
            district=lots[0].district,
            crop=crop,
            plot="",
            harvest_date=lots[0].harvest_date,
            expected_qty_kg=total,
            centre=lots[0].centre,
            status="receipt",
            grade=grade,
            net_kg=total,
            gross_kg=total,
            tare_kg=0,
            created_at=now,
            source_lot_ids=[lot.id for lot in lots],
            journey=[
                JourneyEvent(
                    "Aggregation",
                    ", ".join(lot.id for lot in lots),
                    now,
                    "current",
                )
            ],
        )
        self.store.lots[merged.id] = merged
        for lot in lots:
            lot.status = "aggregated"
        return self._lot_brief(merged)

    def send_to_qc(self, lot_id: str, payload: SendToQcIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        if lot.status in {"qc_rejected"}:
            raise CollectionError("Rejected lots cannot be sent to QC again")
        now = now_label()
        lot.status = "qc_queue"
        lot.qc_status = "Awaiting QC"
        lot.sent_by = payload.sent_by
        lot.sent_at = now
        self._push_journey(lot, "Sent to QC", payload.sent_by, "current")
        return self.qc_dispatch(lot.id)

    def qc_dispatch(self, lot_id: str) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        return {
            **self._lot_brief(lot),
            "qc_status": lot.qc_status or "Awaiting QC",
            "sent_by": lot.sent_by or "Manoj Verma",
            "sent_at": lot.sent_at,
            "next_steps": [
                "Initial QC at Collection Centre",
                "Accept / Hold / Reject",
                "Eligible lots for aggregation",
                "Send to Packhouse",
            ],
        }

    def qc_sheet(self, lot_id: str) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        params = lot.qc_parameters or {
            "moisture": 13.2,
            "broken_grains": 2.5,
            "foreign_matter": 1.0,
            "damaged_grain": 1.2,
            "insect_damage": "Not Found",
        }
        status = "Under QC"
        if lot.qc_status == "Accepted":
            status = "Accepted"
        elif lot.qc_status == "On Hold":
            status = "On Hold"
        elif lot.qc_status == "Rejected":
            status = "Rejected"
        return {
            **self._lot_brief(lot),
            "received_qty_kg": _kg(lot.net_kg or lot.expected_qty_kg),
            "qc_status": status,
            "parameters": params,
            "remarks": lot.qc_remarks,
            "grade": lot.grade,
        }

    def decide_qc(self, lot_id: str, payload: QcDecisionIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        if payload.decision == "hold" and not (payload.hold_reason or payload.remarks).strip():
            raise CollectionError("Hold reason is required")
        if payload.decision == "reject" and not (payload.reject_reason or payload.remarks).strip():
            raise CollectionError("Reject reason is required")
        lot.qc_parameters = payload.parameters.model_dump()
        lot.qc_remarks = payload.remarks
        lot.grade = payload.grade or self._suggest_grade(lot.qc_parameters)
        lot.qc_decided_at = now_label()
        lot.hold_reason = payload.hold_reason
        lot.follow_up = payload.follow_up
        lot.reinspection_date = payload.reinspection_date
        lot.reject_reason = payload.reject_reason
        if payload.decision == "accept":
            lot.qc_status = "Accepted"
            lot.status = "qc_accepted"
            self._push_journey(lot, "QC Accepted", f"Grade {lot.grade}", "done")
        elif payload.decision == "hold":
            lot.qc_status = "On Hold"
            lot.status = "qc_hold"
            self._push_journey(lot, "QC On Hold", payload.hold_reason or payload.remarks, "current")
        else:
            lot.qc_status = "Rejected"
            lot.status = "qc_rejected"
            self._push_journey(lot, "QC Rejected", payload.reject_reason or payload.remarks, "done")
        return self.qc_case(lot.id)

    def lens_board(self) -> dict[str, object]:
        """Same records the Bright Store app writes, grouped like the app flow."""
        lots = [self._lens_lot(lot) for lot in self.store.lots.values()]
        lots.sort(key=lambda item: str(item["lot_id"]))
        shipments = [self._lens_shipment(item) for item in self.store.shipments.values()]
        shipments.sort(key=lambda item: str(item["shipment_id"]))
        return {
            "incoming": self.list_deliveries("all"),
            "qc": self.list_qc_queue("all"),
            "lots": lots,
            "shipments": shipments,
        }

    def _lens_lot(self, lot: Lot) -> dict[str, object]:
        return {
            **self._lot_brief(lot),
            "qc_status": lot.qc_status or "",
            "created_at": lot.created_at,
            "sample_id": lot.sample_id,
            "pack_lot_id": lot.pack_lot_id,
            "shipment_id": lot.shipment_id,
            "received_qty_kg": _kg(lot.net_kg or lot.expected_qty_kg),
            "gross_kg": lot.gross_kg,
            "tare_kg": lot.tare_kg,
            "hold_reason": lot.hold_reason,
            "reject_reason": lot.reject_reason,
            "source_lot_ids": list(lot.source_lot_ids),
        }

    def _lens_shipment(self, shipment: Shipment) -> dict[str, object]:
        return {
            "shipment_id": shipment.id,
            "pack_lot_id": shipment.pack_lot_id,
            "lot_id": shipment.lot_id,
            "crop": shipment.crop,
            "grade": shipment.grade,
            "qty_kg": shipment.qty_kg,
            "pack_count": shipment.pack_count,
            "buyer_name": shipment.buyer_name,
            "buyer_location": shipment.buyer_location,
            "purchase_order": shipment.purchase_order,
            "vehicle_number": shipment.vehicle_number,
            "driver_name": shipment.driver_name,
            "status": shipment.status,
            "dispatched_at": shipment.dispatched_at,
            "received_qty_kg": shipment.received_qty_kg,
            "accepted_qty_kg": shipment.accepted_qty_kg,
            "condition": shipment.condition,
            "remarks": shipment.remarks,
        }

    def list_qc_queue(self, tab: str = "awaiting", q: str = "") -> dict[str, object]:
        tab = tab if tab in {"awaiting", "progress", "hold", "all"} else "awaiting"
        query = q.strip().lower()
        buckets = {"awaiting": [], "progress": [], "hold": []}
        for lot in self.store.lots.values():
            bucket = self._qc_bucket(lot)
            if bucket is None:
                continue
            if query and query not in f"{lot.id} {lot.farmer_name} {lot.crop}".lower():
                continue
            buckets[bucket].append(self._qc_queue_card(lot))
        for items in buckets.values():
            items.sort(key=lambda item: str(item["lot_id"]))
        selected = [] if tab == "all" else buckets[tab]
        if tab == "all":
            selected = [*buckets["awaiting"], *buckets["progress"], *buckets["hold"]]
        return {
            "tab": tab,
            "counts": {key: len(value) for key, value in buckets.items()},
            "items": selected,
        }

    def qc_case(self, lot_id: str) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        params = self._qc_params(lot)
        return {
            **self._lot_brief(lot),
            "received_qty_kg": _kg(lot.net_kg or lot.expected_qty_kg),
            "collection_time": lot.created_at,
            "qc_status": lot.qc_status or "Awaiting QC",
            "sample_id": lot.sample_id,
            "sample_type": lot.sample_type or "Primary Sample",
            "sample_location": lot.sample_location or lot.centre,
            "sample_date": lot.sample_date,
            "inspector": lot.inspector or "Manoj Verma",
            "sample_remarks": lot.sample_remarks,
            "parameters": params,
            "photos": list(lot.qc_photos),
            "documents": list(lot.qc_documents),
            "remarks": lot.qc_remarks,
            "grade": self._suggest_grade(params),
            "hold_reason": lot.hold_reason,
            "follow_up": lot.follow_up,
            "reinspection_date": lot.reinspection_date,
            "reject_reason": lot.reject_reason,
            "qc_date": lot.qc_decided_at or lot.sample_date or lot.created_at,
            "lab_name": lot.lab_name,
            "lab_test_type": lot.lab_test_type,
            "lab_sample_id": lot.lab_sample_id,
            "lab_expected_date": lot.lab_expected_date,
            "lab_result": lot.lab_result,
            "lab_report_name": lot.lab_report_name,
            "plot_cycle": f"CC-{lot.plot}-2026-KH",
        }

    def save_qc_sample(self, lot_id: str, payload: QcSampleIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        if not lot.sample_id:
            lot.sample_id = self.store.next_sample_id()
        lot.sample_type = payload.sample_type or "Primary Sample"
        lot.sample_location = payload.sample_location or lot.centre
        lot.inspector = payload.inspector or "Manoj Verma"
        lot.sample_remarks = payload.remarks
        lot.sample_date = lot.sample_date or now_label()
        if payload.photos:
            lot.qc_photos = list(payload.photos)
        if lot.qc_status in {"", "Awaiting QC"}:
            lot.qc_status = "In Progress"
            lot.status = "qc_progress"
        self._push_journey(lot, "QC Sample", lot.sample_id, "current")
        return self.qc_case(lot.id)

    def save_qc_inspection(self, lot_id: str, payload: QcInspectionIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        lot.qc_parameters = payload.parameters.model_dump()
        lot.qc_remarks = payload.remarks
        lot.grade = self._suggest_grade(lot.qc_parameters)
        if lot.qc_status in {"", "Awaiting QC"}:
            lot.qc_status = "In Progress"
            lot.status = "qc_progress"
        return self.qc_case(lot.id)

    def save_qc_documents(self, lot_id: str, payload: QcDocumentsIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        lot.qc_photos = list(payload.photos)
        lot.qc_documents = [item.model_dump() for item in payload.documents]
        if payload.remarks:
            lot.qc_remarks = payload.remarks
        return self.qc_case(lot.id)

    def save_qc_lab(self, lot_id: str, payload: QcLabIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        lot.lab_name = payload.lab_name
        lot.lab_test_type = payload.test_type
        lot.lab_sample_id = payload.sample_id or lot.sample_id
        lot.lab_expected_date = payload.expected_date
        lot.lab_result = payload.result
        lot.lab_report_name = payload.report_name
        self._push_journey(lot, "Lab Test", payload.result or payload.test_type, "done")
        return self.qc_case(lot.id)

    def reinspect_qc(self, lot_id: str, payload: QcReinspectIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        if lot.qc_status != "On Hold":
            raise CollectionError("Only held lots can be reinspected")
        lot.inspector = payload.inspector or lot.inspector
        lot.qc_remarks = payload.remarks
        decision = QcDecisionIn(
            decision=payload.result,
            grade=lot.grade or "A",
            remarks=payload.remarks,
            parameters=self._parameters_model(lot),
            hold_reason=lot.hold_reason or "Reinspection",
            follow_up=lot.follow_up,
            reinspection_date=lot.reinspection_date,
            reject_reason=payload.remarks or "Failed reinspection",
        )
        return self.decide_qc(lot.id, decision)

    def packhouse(self, lot_id: str) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        input_qty = _kg(lot.net_kg or lot.expected_qty_kg)
        packed = lot.packed_qty_kg if lot.packed_qty_kg is not None else max(input_qty - 100, 0)
        size = lot.pack_size_kg or 5
        count = lot.pack_count if lot.pack_count is not None else int(packed // size)
        return {
            "input_lot_id": lot.id,
            "crop": lot.crop,
            "input_qty_kg": input_qty,
            "centre": lot.centre,
            "qc_status": lot.qc_status or "Accepted",
            "steps": [
                {"name": "Cleaning", "state": "done", "note": "Water · 3,800 · Waste 50"},
                {"name": "Sorting", "state": "done", "note": "Foreign matter removed"},
                {"name": "Grading", "state": "done", "note": f"Grade {lot.grade}"},
                {
                    "name": "Packing",
                    "state": "done" if lot.pack_lot_id else "current",
                    "note": "In progress" if not lot.pack_lot_id else lot.pack_lot_id,
                },
            ],
            "pack_size_kg": size,
            "packed_qty_kg": packed,
            "pack_count": count,
            "pack_lot_id": lot.pack_lot_id,
        }

    def complete_packhouse(self, lot_id: str, payload: PackhouseIn) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        if lot.status == "qc_rejected":
            raise CollectionError("Rejected lots cannot be packed")
        input_qty = _kg(lot.net_kg or lot.expected_qty_kg)
        waste = 100 if input_qty > 100 else 0
        packed = round(max(input_qty - waste, 0), 2)
        count = int(packed // payload.pack_size_kg) if payload.pack_size_kg else 0
        if not lot.pack_lot_id:
            lot.pack_lot_id = self.store.next_pack_id()
        lot.pack_size_kg = payload.pack_size_kg
        lot.packed_qty_kg = packed
        lot.pack_count = count
        lot.status = "packed"
        lot.qc_status = lot.qc_status or "Accepted"
        self._push_journey(lot, "Packed", lot.pack_lot_id, "current")
        return self.packhouse(lot.id)

    def dispatch_sheet(self, pack_lot_id: str) -> dict[str, object]:
        lot = self._lot_by_pack(pack_lot_id)
        shipment = self.store.shipments.get(lot.shipment_id) if lot.shipment_id else None
        return {
            "pack_lot_id": lot.pack_lot_id,
            "lot_id": lot.id,
            "crop": lot.crop,
            "grade": lot.grade,
            "pack_count": lot.pack_count,
            "qty_kg": lot.packed_qty_kg,
            "buyer_name": shipment.buyer_name if shipment else "Reliance Fresh",
            "buyer_location": shipment.buyer_location if shipment else "Lucknow",
            "purchase_order": shipment.purchase_order if shipment else "PO-12345",
            "po_status": "Confirmed",
            "vehicle_number": shipment.vehicle_number if shipment else "UP78BT1234",
            "driver_name": shipment.driver_name if shipment else "Ramesh Yadav",
            "driver_contact": shipment.driver_contact if shipment else "9876543210",
            "documents": ["e-Way Bill", "Quality Certificate"],
            "shipment_id": shipment.id if shipment else "",
        }

    def create_dispatch(self, pack_lot_id: str, payload: DispatchIn) -> dict[str, object]:
        lot = self._lot_by_pack(pack_lot_id)
        if not lot.pack_lot_id:
            raise CollectionError("Create a pack lot before dispatch")
        now = now_label()
        shipment = Shipment(
            id=self.store.next_shipment_id(),
            pack_lot_id=lot.pack_lot_id,
            lot_id=lot.id,
            buyer_name=payload.buyer_name,
            buyer_location=payload.buyer_location,
            purchase_order=payload.purchase_order,
            vehicle_number=payload.vehicle_number,
            driver_name=payload.driver_name,
            driver_contact=payload.driver_contact,
            qty_kg=_kg(lot.packed_qty_kg),
            pack_count=lot.pack_count or 0,
            crop=lot.crop,
            grade=lot.grade,
            status="in_transit",
            dispatched_at=now,
            from_centre=lot.centre,
        )
        self.store.shipments[shipment.id] = shipment
        lot.shipment_id = shipment.id
        lot.status = "dispatched"
        self._push_journey(
            lot,
            "Dispatched",
            f"{shipment.id} · {shipment.buyer_name}",
            "current",
        )
        return self.buyer_receipt(shipment.id)

    def buyer_receipt(self, shipment_id: str) -> dict[str, object]:
        shipment = self.store.shipments.get(shipment_id)
        if shipment is None:
            raise CollectionError("Shipment not found", 404)
        return {
            "shipment_id": shipment.id,
            "status": "In Transit" if shipment.status == "in_transit" else "Received",
            "from_centre": shipment.from_centre,
            "buyer_name": shipment.buyer_name,
            "buyer_location": shipment.buyer_location,
            "dispatched_at": shipment.dispatched_at,
            "purchase_order": shipment.purchase_order,
            "crop": shipment.crop,
            "grade": shipment.grade,
            "qty_kg": shipment.qty_kg,
            "pack_count": shipment.pack_count,
            "pack_lot_id": shipment.pack_lot_id,
            "lot_id": shipment.lot_id,
            "received_qty_kg": shipment.received_qty_kg
            if shipment.received_qty_kg is not None
            else shipment.qty_kg,
            "accepted_qty_kg": shipment.accepted_qty_kg
            if shipment.accepted_qty_kg is not None
            else shipment.qty_kg,
            "shortage_kg": shipment.shortage_kg if shipment.shortage_kg is not None else 0,
            "damage_kg": shipment.damage_kg if shipment.damage_kg is not None else 0,
            "condition": shipment.condition or "Good",
            "remarks": shipment.remarks,
        }

    def confirm_grn(self, shipment_id: str, payload: GrnIn) -> dict[str, object]:
        shipment = self.store.shipments.get(shipment_id)
        if shipment is None:
            raise CollectionError("Shipment not found", 404)
        shipment.received_qty_kg = payload.received_qty_kg
        shipment.accepted_qty_kg = payload.accepted_qty_kg
        shipment.shortage_kg = payload.shortage_kg
        shipment.damage_kg = payload.damage_kg
        shipment.condition = payload.condition
        shipment.remarks = payload.remarks
        shipment.status = "received"
        shipment.received_at = now_label()
        lot = self._require_lot(shipment.lot_id)
        lot.status = "received"
        self._push_journey(lot, "Buyer receipt", shipment.buyer_name, "done")
        return self.buyer_receipt(shipment.id)

    def lot_360(self, lot_id: str) -> dict[str, object]:
        lot = self._require_lot(lot_id)
        shipment = self.store.shipments.get(lot.shipment_id) if lot.shipment_id else None
        return {
            **self._lot_brief(lot),
            "active": lot.status not in {"qc_rejected"},
            "journey": [
                {"title": event.title, "detail": event.detail, "at": event.at, "state": event.state}
                for event in lot.journey
            ],
            "details": {
                "farmer_name": lot.farmer_name,
                "farmer_id": lot.farmer_id,
                "village": lot.village,
                "district": lot.district,
                "plot": lot.plot,
                "harvest_date": lot.harvest_date,
                "harvest_lot": lot.harvest_lot,
                "gross_kg": lot.gross_kg,
                "tare_kg": lot.tare_kg,
                "net_kg": lot.net_kg,
                "centre": lot.centre,
            },
            "genealogy": {
                "harvest_lot": lot.harvest_lot,
                "lot_id": lot.id,
                "source_lot_ids": lot.source_lot_ids,
                "pack_lot_id": lot.pack_lot_id,
                "shipment_id": shipment.id if shipment else "",
                "buyer_name": shipment.buyer_name if shipment else "",
            },
        }

    def trace(self, code: str) -> dict[str, object]:
        token = code.strip()
        lot = self.store.lots.get(token) or self._lot_by_pack_optional(token)
        if lot is None:
            for item in self.store.lots.values():
                if item.harvest_lot == token:
                    lot = item
                    break
        if lot is None:
            raise CollectionError("QR code not found", 404)
        return {
            "code": token,
            "pack_lot_id": lot.pack_lot_id or token,
            "crop": lot.crop,
            "pack_size_kg": lot.pack_size_kg,
            "packed_on": lot.qc_decided_at or lot.created_at,
            "parent_lot_id": lot.id,
            "qty_kg": lot.packed_qty_kg or lot.net_kg,
            "grade": lot.grade,
            "farmer_name": lot.farmer_name,
        }

    def _delivery_by_harvest(self, code: str) -> Delivery | None:
        token = code.strip()
        for delivery in self.store.deliveries.values():
            if delivery.harvest_lot == token:
                return delivery
        return None

    def _require_lot(self, lot_id: str) -> Lot:
        lot = self.store.lots.get(lot_id)
        if lot is None:
            raise CollectionError("Lot not found", 404)
        return lot

    def _lot_by_pack(self, pack_lot_id: str) -> Lot:
        lot = self._lot_by_pack_optional(pack_lot_id)
        if lot is None:
            raise CollectionError("Pack lot not found", 404)
        return lot

    def _lot_by_pack_optional(self, pack_lot_id: str) -> Lot | None:
        for lot in self.store.lots.values():
            if lot.pack_lot_id == pack_lot_id:
                return lot
        return None

    def _mark_delivery_received(self, lot: Lot) -> None:
        if not lot.delivery_id:
            return
        delivery = self.store.deliveries.get(lot.delivery_id)
        if delivery is None:
            return
        delivery.status = "received"
        delivery.received_qty_kg = lot.net_kg
        delivery.arrival_label = lot.created_at

    def _push_journey(self, lot: Lot, title: str, detail: str, state: str) -> None:
        for event in lot.journey:
            if event.state == "current":
                event.state = "done"
        lot.journey.append(JourneyEvent(title, detail, now_label(), state))

    def _delivery_card(self, delivery: Delivery) -> dict[str, object]:
        qty = delivery.received_qty_kg if delivery.status == "received" else delivery.expected_qty_kg
        label = "Received" if delivery.status == "received" else "Expected"
        return {
            "id": delivery.id,
            "farmer_name": delivery.farmer_name,
            "crop": delivery.crop,
            "qty_kg": qty,
            "qty_label": label,
            "arrival_label": delivery.arrival_label,
            "status": delivery.status,
            "harvest_lot": delivery.harvest_lot,
            "mobile": delivery.mobile,
            "farmer_id": delivery.farmer_id,
            "village": delivery.village,
            "district": delivery.district,
        }

    def _delivery_detail(self, delivery: Delivery) -> dict[str, object]:
        return {
            "delivery_id": delivery.id,
            "harvest_lot": delivery.harvest_lot,
            "farmer_name": delivery.farmer_name,
            "farmer_id": delivery.farmer_id,
            "village": delivery.village,
            "district": delivery.district,
            "crop": delivery.crop,
            "plot": delivery.plot,
            "harvest_date": delivery.harvest_date,
            "expected_qty_kg": delivery.expected_qty_kg,
            "centre": delivery.centre,
            "status": delivery.status,
            "mobile": delivery.mobile,
        }

    def _qc_bucket(self, lot: Lot) -> str | None:
        status = (lot.qc_status or "").lower()
        if lot.status == "qc_queue" or status == "awaiting qc":
            return "awaiting"
        if lot.status == "qc_progress" or status == "in progress":
            return "progress"
        if lot.status == "qc_hold" or status == "on hold":
            return "hold"
        return None

    def _qc_queue_card(self, lot: Lot) -> dict[str, object]:
        return {
            "lot_id": lot.id,
            "crop": lot.crop,
            "farmer_name": lot.farmer_name,
            "qty_kg": _kg(lot.net_kg or lot.expected_qty_kg),
            "arrival_label": lot.created_at,
            "qc_status": lot.qc_status,
        }

    def _qc_params(self, lot: Lot) -> dict[str, object]:
        params = {
            "moisture": 13.2,
            "broken_grains": 2.5,
            "foreign_matter": 1.0,
            "damaged_grain": 1.2,
            "insect_damage": "Not Found",
            "maturity": "Good",
            "odour": "Pass",
            "colour": "Pass",
            "grain_size": "Pass",
        }
        params.update(lot.qc_parameters)
        return params

    def _parameters_model(self, lot: Lot):
        from app.modules.collection_centre.schemas import QcParametersIn

        raw = self._qc_params(lot)
        return QcParametersIn(
            moisture=float(raw["moisture"]),
            broken_grains=float(raw["broken_grains"]),
            foreign_matter=float(raw["foreign_matter"]),
            damaged_grain=float(raw["damaged_grain"]),
            insect_damage=str(raw["insect_damage"]),
            maturity=str(raw["maturity"]),
            odour=str(raw["odour"]),
            colour=str(raw["colour"]),
            grain_size=str(raw["grain_size"]),
        )

    def _suggest_grade(self, params: dict[str, object]) -> str:
        try:
            moisture = float(params.get("moisture", 99))
            broken = float(params.get("broken_grains", 99))
            foreign = float(params.get("foreign_matter", 99))
            damaged = float(params.get("damaged_grain", 99))
        except (TypeError, ValueError):
            return "B"
        insect = str(params.get("insect_damage", ""))
        checks = [str(params.get("odour", "Pass")), str(params.get("colour", "Pass")), str(params.get("grain_size", "Pass"))]
        if (
            moisture <= 14
            and broken <= 5
            and foreign <= 2
            and damaged <= 3
            and insect == "Not Found"
            and all(item in {"Pass", "Good"} for item in checks)
        ):
            return "A"
        return "B"

    def _lot_brief(self, lot: Lot) -> dict[str, object]:
        return {
            "lot_id": lot.id,
            "harvest_lot": lot.harvest_lot,
            "farmer_name": lot.farmer_name,
            "farmer_id": lot.farmer_id,
            "village": lot.village,
            "district": lot.district,
            "crop": lot.crop,
            "plot": lot.plot,
            "harvest_date": lot.harvest_date,
            "expected_qty_kg": lot.expected_qty_kg,
            "centre": lot.centre,
            "grade": lot.grade,
            "status": lot.status,
            "net_kg": lot.net_kg,
            "vehicle_number": lot.vehicle_number,
            "driver_name": lot.driver_name,
        }
