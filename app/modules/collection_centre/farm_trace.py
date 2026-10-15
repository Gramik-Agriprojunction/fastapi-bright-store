"""Farmer traceability in the same shape the CRM farmer profile uses.

Rows come from the Gramik tables (plots, crop cycles, field activities,
harvest lots, lab tests, packhouse, shipments). When those tables are not
loaded, the collection-centre lot already in memory fills the same sections.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collection_centre.repository import CollectionStore, Lot

logger = logging.getLogger(__name__)

JOURNEY = (
    ("land", "Land & Plot"),
    ("crop", "Crop Cycle"),
    ("pop", "POP & Inputs"),
    ("field", "Field Activities"),
    ("harvest", "Harvest"),
    ("collection", "Collection Center"),
    ("qc", "Quality Check"),
    ("packhouse", "Packhouse"),
    ("shipment", "Shipment"),
    ("buyer", "Buyer"),
)

_STATUS_RANK = {
    "draft": 0,
    "receipt": 1,
    "harvest_saved": 1,
    "qc": 2,
    "qc_done": 2,
    "lot_created": 2,
    "packed": 3,
    "dispatched": 4,
    "shipped": 4,
    "delivered": 5,
    "received": 5,
}


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _day(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value)


def _num(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rank(status: str) -> int:
    return _STATUS_RANK.get(status.lower(), 0)


def _quality_rows(lot: Lot, extra: list[dict]) -> list[dict]:
    rows = []
    for label, key in (
        ("Moisture", "moisture"),
        ("Broken grains", "broken_grains"),
        ("Foreign matter", "foreign_matter"),
        ("Damaged grain", "damaged_grain"),
        ("Grain length", "grain_length"),
    ):
        value = (lot.qc_parameters or {}).get(key)
        rows.append(
            {
                "label": label,
                "value": value,
                "unit": "mm" if key == "grain_length" else "%",
                "status": None if value is None else "PASS",
            }
        )
    fixed = {"moisture", "broken grains", "foreign matter", "damaged grain", "grain length"}
    for row in extra:
        if str(row.get("label", "")).lower() not in fixed:
            rows.append(row)
    return rows


def build_farm_trace(store: CollectionStore, lot: Lot) -> dict[str, object]:
    shipment = store.shipments.get(lot.shipment_id) if lot.shipment_id else None
    rank = _rank(lot.status)
    if shipment and _rank(shipment.status) > rank:
        rank = _rank(shipment.status)
    plots = [
        {
            "id": lot.plot or lot.id,
            "label": lot.plot or "Plot",
            "area": None,
            "crop": lot.crop,
            "soil_type": None,
            "irrigation": None,
            "status": "Active",
        }
    ]
    cycles = [
        {
            "id": lot.id,
            "crop": lot.crop,
            "variety": None,
            "season": None,
            "sowing_area": None,
            "sowing_date": None,
            "is_current": True,
            "plot_label": lot.plot,
        }
    ]
    quality = [
        {"label": label.replace("_", " ").title(), "value": value, "unit": "%"}
        for label, value in (lot.qc_parameters or {}).items()
        if value is not None
    ]
    if lot.lab_result:
        quality.append(
            {
                "label": lot.lab_test_type or "Lab test",
                "value": lot.lab_result,
                "unit": "",
                "lab_name": lot.lab_name,
                "status": lot.lab_result,
            }
        )
    produce = _num(lot.net_kg) or _num(lot.expected_qty_kg) or 0
    journey = []
    for index, (key, label) in enumerate(JOURNEY):
        done = index <= 6 and rank >= max(index - 4, 0)
        if key == "land":
            done = bool(lot.plot or lot.farmer_name)
        elif key == "crop":
            done = bool(lot.crop)
        elif key in {"pop", "field"}:
            done = rank >= 1
        elif key == "harvest":
            done = rank >= 1
        elif key == "collection":
            done = bool(lot.centre) and rank >= 1
        elif key == "qc":
            done = rank >= 2 or bool(lot.qc_status)
        elif key == "packhouse":
            done = rank >= 3 or bool(lot.pack_lot_id)
        elif key == "shipment":
            done = rank >= 4 or shipment is not None
        elif key == "buyer":
            done = shipment is not None and bool(shipment.buyer_name)
        journey.append({"key": key, "label": label, "done": done})
    return {
        "farmer": {
            "id": lot.crm_farmer_id or None,
            "name": lot.farmer_name,
            "code": lot.farmer_id,
            "village": lot.village,
            "district": lot.district,
            "mobile": "",
        },
        "summary": {
            "coverage": 0,
            "total_land": None,
            "plots": len(plots),
            "active_crops": 1 if lot.crop else 0,
            "crop_cycles": len(cycles),
            "active_cycles": 1 if lot.crop else 0,
            "completed_cycles": 0,
            "upcoming_cycles": 0,
            "harvest_lots": 1,
            "in_stock_lots": 0 if rank >= 4 else 1,
            "sold_lots": 1 if rank >= 4 else 0,
            "total_produce_kg": produce,
        },
        "journey": journey,
        "plots": plots,
        "crop_cycles": cycles,
        "activities": [],
        "lots": [
            {
                "id": lot.id,
                "code": lot.harvest_lot or lot.id,
                "crop": lot.crop,
                "quantity_kg": produce,
                "grade": lot.grade,
                "status": lot.status,
                "qc_passed": rank >= 2,
                "harvest_date": lot.harvest_date,
                "plot_label": lot.plot,
            }
        ],
        "focus": {
            "code": lot.harvest_lot or lot.id,
            "crop": lot.crop,
            "grade": lot.grade,
            "quantity_kg": produce,
            "status": lot.status,
            "farmer": lot.farmer_name,
            "plot": lot.plot,
            "crop_cycle": None,
            "variety": None,
            "collection_center": lot.centre,
            "stages": [
                {"label": label, "done": rank >= index, "when": lot.harvest_date if rank >= index else None}
                for index, label in enumerate(
                    ("Harvested", "At Collection", "QC Passed", "Packed", "Dispatched", "Delivered")
                )
            ],
            "quality": _quality_rows(lot, quality),
            "packhouse": {
                "name": lot.centre if lot.pack_lot_id else None,
                "pack_lot": lot.pack_lot_id or None,
                "inward_kg": _num(lot.gross_kg),
                "packed_kg": lot.packed_qty_kg,
                "cleaned_kg": _num(lot.net_kg),
                "pack_count": lot.pack_count,
                "batch_code": lot.pack_lot_id or None,
            },
            "shipment": None
            if shipment is None
            else {
                "code": shipment.id,
                "buyer": shipment.buyer_name,
                "status": shipment.status,
                "quantity_kg": shipment.qty_kg,
                "pack_count": shipment.pack_count,
                "delivery_date": shipment.received_at or shipment.dispatched_at,
                "po_number": shipment.purchase_order,
            },
        },
    }


async def _query(session: AsyncSession, sql: str, params: dict) -> list[dict]:
    result = await session.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


async def enrich_farm_traces(session: AsyncSession, store: CollectionStore) -> None:
    for lot in store.lots.values():
        store.farm_traces[lot.id] = build_farm_trace(store, lot)
    farmer_ids = sorted({lot.crm_farmer_id for lot in store.lots.values() if lot.crm_farmer_id})
    if not farmer_ids:
        return
    try:
        async with session.begin_nested():
            await session.execute(text("SET LOCAL statement_timeout = '8000'"))
            await _fill_farmers(session, store, farmer_ids)
    except Exception:
        logger.exception("CRM farmer traceability could not be loaded")


async def _fill_farmers(session: AsyncSession, store: CollectionStore, farmer_ids: list[int]) -> None:
    plots: dict[int, list[dict]] = {farmer_id: [] for farmer_id in farmer_ids}
    cycles: dict[int, list[dict]] = {farmer_id: [] for farmer_id in farmer_ids}
    activities: dict[int, list[dict]] = {farmer_id: [] for farmer_id in farmer_ids}
    for farmer_id in farmer_ids:
        for row in await _query(
            session,
            """
            SELECT fsl.id, fsl.name, fsl.acres, c.name AS crop_name
            FROM farmer_store_lands fsl
            LEFT JOIN "Crop" c ON c.id = fsl.crop_id
            WHERE fsl.user_id = :farmer_id
            ORDER BY fsl.id
            """,
            {"farmer_id": farmer_id},
        ):
            plots[farmer_id].append(
                {
                    "id": row["id"],
                    "label": _text(row.get("name")) or f"Plot {row['id']}",
                    "area": _num(row.get("acres")),
                    "crop": _text(row.get("crop_name")) or None,
                    "soil_type": None,
                    "irrigation": None,
                    "status": "Active",
                }
            )
        for row in await _query(
            session,
            """
            SELECT uc.id, uc.sowing_date, uc.sowing_area, uc.is_current, uc.variety,
                   uc.land_id, c.name AS crop_name
            FROM "UserCrop" uc
            JOIN "Crop" c ON c.id = uc.crop_id
            WHERE uc.user_id = :farmer_id
            ORDER BY uc.id DESC
            """,
            {"farmer_id": farmer_id},
        ):
            cycles[farmer_id].append(
                {
                    "id": row["id"],
                    "crop": row.get("crop_name"),
                    "variety": row.get("variety"),
                    "season": None,
                    "sowing_area": _num(row.get("sowing_area")),
                    "sowing_date": _day(row.get("sowing_date")) or None,
                    "is_current": bool(row.get("is_current")),
                    "plot_label": f"P-{row['land_id']}" if row.get("land_id") else None,
                }
            )
        for row in await _query(
            session,
            """
            SELECT id, status, date_of_sowing, initial_land_values, created_at
            FROM land_treatments
            WHERE farmer_id = :farmer_id
            ORDER BY created_at DESC
            LIMIT 30
            """,
            {"farmer_id": farmer_id},
        ):
            activities[farmer_id].append(
                {
                    "id": row["id"],
                    "title": _text(row.get("initial_land_values")) or "Field activity",
                    "status": _text(row.get("status")),
                    "date": _day(row.get("date_of_sowing") or row.get("created_at")),
                }
            )
    for lot in store.lots.values():
        farmer_id = lot.crm_farmer_id
        if not farmer_id:
            continue
        trace = store.farm_traces[lot.id]
        farmer_plots = plots.get(farmer_id) or trace["plots"]
        farmer_cycles = cycles.get(farmer_id) or trace["crop_cycles"]
        farmer_activities = activities.get(farmer_id) or []
        area = sum(_num(plot.get("area")) or 0 for plot in farmer_plots)
        summary = trace["summary"]
        if isinstance(summary, dict):
            summary["total_land"] = area or None
            summary["plots"] = len(farmer_plots)
            summary["crop_cycles"] = len(farmer_cycles)
            summary["active_crops"] = sum(1 for cycle in farmer_cycles if cycle.get("is_current"))
            summary["harvest_lots"] = sum(1 for item in store.lots.values() if item.crm_farmer_id == farmer_id)
            summary["total_produce_kg"] = sum(
                _num(item.net_kg) or 0 for item in store.lots.values() if item.crm_farmer_id == farmer_id
            )
            summary["coverage"] = _coverage(farmer_plots, farmer_cycles, farmer_activities)
        trace["plots"] = farmer_plots
        trace["crop_cycles"] = farmer_cycles
        trace["activities"] = farmer_activities
        trace["lots"] = [
            {
                "id": item.id,
                "code": item.harvest_lot or item.id,
                "crop": item.crop,
                "quantity_kg": _num(item.net_kg),
                "grade": item.grade,
                "status": item.status,
                "qc_passed": _rank(item.status) >= 2,
                "harvest_date": item.harvest_date,
                "plot_label": item.plot,
            }
            for item in store.lots.values()
            if item.crm_farmer_id == farmer_id
        ]


def _coverage(plots: list[dict], cycles: list[dict], activities: list[dict]) -> int:
    checks = [bool(plots), bool(cycles), any(cycle.get("sowing_date") for cycle in cycles), bool(activities)]
    return round(100 * sum(1 for item in checks if item) / len(checks))
