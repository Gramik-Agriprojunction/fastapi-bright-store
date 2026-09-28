"""Read Gramik traceability rows into the collection centre store.

The Bright Store screens look up a harvest lot and open farmer details from
this store. Local CRM harvests live in trace_* tables, so they are copied in
on each database load.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collection_centre.repository import (
    CollectionStore,
    Delivery,
    JourneyEvent,
    Lot,
    Shipment,
    format_when,
)

logger = logging.getLogger(__name__)

_TRACE_SQL = """
SELECT
  h.id AS harvest_id,
  h.status,
  h.harvest_date,
  h.expected_yield_kg,
  h.net_weight_kg,
  h.gross_weight_kg,
  h.tare_weight_kg,
  h.grade,
  h.moisture,
  h.broken_grains,
  h.foreign_matter,
  h.damaged_grain,
  h.qc_remarks,
  h.vehicle_number,
  h.driver_name,
  u.name AS farmer_name,
  u.mobile,
  u.unique_code,
  c.name AS crop_name,
  uc.land_id,
  cc.name AS centre_name,
  addr.village,
  addr.district,
  addr.state_name,
  l.code AS lot_code,
  l.quantity_kg,
  s.code AS shipment_code,
  s.status AS shipment_status,
  s.quantity_kg AS shipment_qty,
  s.pack_count AS shipment_packs,
  s.po_number,
  b.name AS buyer_name
FROM trace_harvests h
JOIN users u ON u.id = h.farmer_id
LEFT JOIN "UserCrop" uc ON uc.id = h.user_crop_id
LEFT JOIN "Crop" c ON c.id = uc.crop_id
LEFT JOIN trace_collection_centers cc ON cc.id = h.collection_center_id
LEFT JOIN LATERAL (
  SELECT village, district, state_name
  FROM addresses
  WHERE user_id = h.farmer_id AND is_default = true
  LIMIT 1
) addr ON true
LEFT JOIN trace_harvest_lots l ON l.harvest_id = h.id
LEFT JOIN trace_shipments s ON s.lot_id = l.id
LEFT JOIN trace_buyers b ON b.id = COALESCE(s.buyer_id, l.buyer_id)
ORDER BY h.id DESC
LIMIT 30
"""


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _when(value: object) -> str:
    if isinstance(value, datetime):
        return format_when(value)
    return _text(value)


def _qty(row: dict) -> float:
    for key in ("quantity_kg", "net_weight_kg", "expected_yield_kg"):
        value = row.get(key)
        if value is not None:
            return float(value)
    return 0


def apply_trace_row(store: CollectionStore, row: dict) -> None:
    lot_code = _text(row.get("lot_code")) or f"TRACE-{row['harvest_id']}"
    farmer_name = _text(row.get("farmer_name")) or "Farmer"
    district = _text(row.get("district"))
    state = _text(row.get("state_name"))
    if state and state not in district:
        district = f"{district}, {state}".strip(", ")
    centre = _text(row.get("centre_name")) or "Collection Centre"
    crop = _text(row.get("crop_name")) or "Crop"
    qty = _qty(row)
    harvest_on = _when(row.get("harvest_date"))
    status = _text(row.get("status")).lower()
    received = status in {"delivered", "shipped"}
    delivery_id = f"trace-{row['harvest_id']}"
    grade = _text(row.get("grade")) or "A"
    store.deliveries[delivery_id] = Delivery(
        id=delivery_id,
        farmer_name=farmer_name,
        crop=crop,
        expected_qty_kg=float(row.get("expected_yield_kg") or qty),
        arrival_label=harvest_on or "Harvest recorded",
        status="received" if received else "arriving",
        centre=centre,
        farmer_id=_text(row.get("unique_code")),
        village=_text(row.get("village")),
        district=district,
        plot=f"P-{row['land_id']}" if row.get("land_id") else "",
        harvest_date=harvest_on,
        harvest_lot=lot_code,
        received_qty_kg=qty if received else None,
        mobile=_text(row.get("mobile")),
    )
    journey = [
        JourneyEvent("Harvest", f"{store.deliveries[delivery_id].plot} · {farmer_name}".strip(" ·"), harvest_on, "done"),
        JourneyEvent("Quality Check", grade, harvest_on, "done" if grade else "upcoming"),
    ]
    if received:
        journey.append(
            JourneyEvent(
                "Delivered" if status == "delivered" else "Dispatched",
                _text(row.get("buyer_name")) or centre,
                harvest_on,
                "done",
            )
        )
    lot = Lot(
        id=lot_code,
        harvest_lot=lot_code,
        farmer_name=farmer_name,
        farmer_id=_text(row.get("unique_code")),
        village=_text(row.get("village")),
        district=district,
        crop=crop,
        plot=store.deliveries[delivery_id].plot,
        harvest_date=harvest_on,
        expected_qty_kg=float(row.get("expected_yield_kg") or qty),
        centre=centre,
        status="dispatched" if received else "receipt",
        grade=grade,
        gross_kg=row.get("gross_weight_kg"),
        tare_kg=row.get("tare_weight_kg"),
        net_kg=row.get("net_weight_kg") or qty,
        vehicle_number=_text(row.get("vehicle_number")),
        driver_name=_text(row.get("driver_name")),
        created_at=harvest_on,
        delivery_id=delivery_id,
        qc_status="Accepted" if grade else "",
        qc_remarks=_text(row.get("qc_remarks")),
        qc_parameters={
            "moisture": row.get("moisture"),
            "broken_grains": row.get("broken_grains"),
            "foreign_matter": row.get("foreign_matter"),
            "damaged_grain": row.get("damaged_grain"),
        },
        journey=journey,
    )
    shipment_code = _text(row.get("shipment_code"))
    if shipment_code:
        lot.shipment_id = shipment_code
        store.shipments[shipment_code] = Shipment(
            id=shipment_code,
            pack_lot_id="",
            lot_id=lot_code,
            buyer_name=_text(row.get("buyer_name")),
            buyer_location=district,
            purchase_order=_text(row.get("po_number")),
            vehicle_number=_text(row.get("vehicle_number")),
            driver_name=_text(row.get("driver_name")),
            driver_contact=_text(row.get("mobile")),
            qty_kg=float(row.get("shipment_qty") or qty),
            pack_count=int(row.get("shipment_packs") or 0),
            crop=crop,
            grade=grade,
            status=_text(row.get("shipment_status")) or status,
            dispatched_at=harvest_on,
            from_centre=centre,
            received_qty_kg=qty if status == "delivered" else None,
        )
    store.lots[lot_code] = lot


async def merge_crm_trace(session: AsyncSession, store: CollectionStore) -> None:
    try:
        async with session.begin_nested():
            await session.execute(text("SET LOCAL statement_timeout = '8000'"))
            result = await session.execute(text(_TRACE_SQL))
            rows = result.mappings().all()
    except Exception:
        logger.exception("CRM traceability farmers could not be loaded")
        return
    for row in rows:
        apply_trace_row(store, dict(row))
