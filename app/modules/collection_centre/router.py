from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.collection_centre.persistence import get_collection_service
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
from app.modules.collection_centre.service import CollectionService

router = APIRouter(prefix="/collection-centre", tags=["collection-centre"])
ServiceDep = Annotated[CollectionService, Depends(get_collection_service)]


def ok(data: object, message: str) -> dict[str, object]:
    return {"success": True, "message": message, "data": data}


@router.get("/lens")
async def lens_board(service: ServiceDep) -> dict[str, object]:
    return ok(service.lens_board(), "Lens board loaded")


@router.get("/deliveries")
async def list_deliveries(
    service: ServiceDep,
    tab: str = Query(default="expected"),
    q: str = Query(default=""),
) -> dict[str, object]:
    return ok(service.list_deliveries(tab, q), "Deliveries loaded")


@router.get("/harvest-lots/{code}")
async def harvest_lot(code: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.get_harvest(code), "Harvest lot loaded")


@router.post("/gate-entries")
async def create_gate_entry(payload: GateEntryIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.create_gate_entry(payload), "Gate entry saved")


@router.get("/lots/{lot_id}/weighment")
async def weighment(lot_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.get_weighment(lot_id), "Weighment loaded")


@router.post("/lots/{lot_id}/weighment")
async def save_weighment(lot_id: str, payload: WeighmentIn, service: ServiceDep) -> dict[str, object]:
    message = "Weighment confirmed" if payload.confirm else "Draft saved"
    return ok(service.save_weighment(lot_id, payload), message)


@router.get("/lots/{lot_id}/receipt")
async def receipt(lot_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.receipt(lot_id), "Receipt loaded")


@router.get("/aggregations/candidates")
async def aggregation_candidates(
    service: ServiceDep,
    lot_id: str | None = None,
) -> dict[str, object]:
    return ok(service.aggregation_candidates(lot_id), "Compatible lots loaded")


@router.post("/aggregations")
async def create_aggregation(payload: AggregationIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.create_aggregation(payload), "Aggregation lot created")


@router.post("/lots/{lot_id}/send-to-qc")
async def send_to_qc(lot_id: str, payload: SendToQcIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.send_to_qc(lot_id, payload), "Lot sent to QC")


@router.get("/lots/{lot_id}/qc-dispatch")
async def qc_dispatch(lot_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.qc_dispatch(lot_id), "QC dispatch loaded")


@router.get("/lots/{lot_id}/qc")
async def qc_sheet(lot_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.qc_sheet(lot_id), "QC sheet loaded")


@router.get("/qc/queue")
async def qc_queue(
    service: ServiceDep,
    tab: str = Query(default="awaiting"),
    q: str = Query(default=""),
) -> dict[str, object]:
    return ok(service.list_qc_queue(tab, q), "QC queue loaded")


@router.get("/lots/{lot_id}/qc/case")
async def qc_case(lot_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.qc_case(lot_id), "QC case loaded")


@router.post("/lots/{lot_id}/qc/sample")
async def save_qc_sample(lot_id: str, payload: QcSampleIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.save_qc_sample(lot_id, payload), "Sample saved")


@router.post("/lots/{lot_id}/qc/inspection")
async def save_qc_inspection(
    lot_id: str,
    payload: QcInspectionIn,
    service: ServiceDep,
) -> dict[str, object]:
    return ok(service.save_qc_inspection(lot_id, payload), "Inspection saved")


@router.post("/lots/{lot_id}/qc/documents")
async def save_qc_documents(
    lot_id: str,
    payload: QcDocumentsIn,
    service: ServiceDep,
) -> dict[str, object]:
    return ok(service.save_qc_documents(lot_id, payload), "Documents saved")


@router.post("/lots/{lot_id}/qc/lab")
async def save_qc_lab(lot_id: str, payload: QcLabIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.save_qc_lab(lot_id, payload), "Lab test saved")


@router.post("/lots/{lot_id}/qc/reinspection")
async def reinspect_qc(lot_id: str, payload: QcReinspectIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.reinspect_qc(lot_id, payload), "Reinspection saved")


@router.post("/lots/{lot_id}/qc")
async def decide_qc(lot_id: str, payload: QcDecisionIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.decide_qc(lot_id, payload), "QC decision saved")


@router.get("/lots/{lot_id}/packhouse")
async def packhouse(lot_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.packhouse(lot_id), "Packhouse loaded")


@router.post("/lots/{lot_id}/packhouse")
async def complete_packhouse(
    lot_id: str,
    payload: PackhouseIn,
    service: ServiceDep,
) -> dict[str, object]:
    return ok(service.complete_packhouse(lot_id, payload), "Pack lot created")


@router.get("/packs/{pack_lot_id}/dispatch")
async def dispatch_sheet(pack_lot_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.dispatch_sheet(pack_lot_id), "Dispatch loaded")


@router.post("/packs/{pack_lot_id}/dispatch")
async def create_dispatch(
    pack_lot_id: str,
    payload: DispatchIn,
    service: ServiceDep,
) -> dict[str, object]:
    return ok(service.create_dispatch(pack_lot_id, payload), "Shipment dispatched")


@router.get("/shipments/{shipment_id}")
async def buyer_receipt(shipment_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.buyer_receipt(shipment_id), "Buyer receipt loaded")


@router.post("/shipments/{shipment_id}/grn")
async def confirm_grn(shipment_id: str, payload: GrnIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.confirm_grn(shipment_id, payload), "GRN confirmed")


@router.get("/lots/{lot_id}/traceability")
async def lot_360(lot_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.lot_360(lot_id), "Lot traceability loaded")


@router.get("/trace/{code}")
async def trace(code: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.trace(code), "QR trace loaded")
