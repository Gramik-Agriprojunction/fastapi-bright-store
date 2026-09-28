from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.buyer.persistence import get_buyer_service
from app.modules.buyer.schemas import ClaimIn, GrnIn, ScanIn
from app.modules.buyer.service import BuyerService

router = APIRouter(prefix="/buyer", tags=["buyer"])
ServiceDep = Annotated[BuyerService, Depends(get_buyer_service)]


def ok(data: object, message: str) -> dict[str, object]:
    return {"success": True, "message": message, "data": data}


@router.get("/dashboard")
async def dashboard(service: ServiceDep, q: str = Query(default="")) -> dict[str, object]:
    return ok(service.dashboard(q), "Buyer dashboard loaded")


@router.get("/purchase-orders")
async def purchase_orders(service: ServiceDep, q: str = Query(default="")) -> dict[str, object]:
    return ok(service.purchase_orders(q), "Purchase orders loaded")


@router.get("/receipts")
async def receipts(service: ServiceDep, q: str = Query(default="")) -> dict[str, object]:
    return ok(service.receipts(q), "Receipts loaded")


@router.get("/shipments/{shipment_id}")
async def shipment(shipment_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.shipment(shipment_id), "Shipment loaded")


@router.get("/shipments/{shipment_id}/tracking")
async def tracking(shipment_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.tracking(shipment_id), "Tracking loaded")


@router.get("/shipments/{shipment_id}/receive")
async def receive(shipment_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.receive(shipment_id), "Receive sheet loaded")


@router.post("/shipments/{shipment_id}/scan")
async def scan(shipment_id: str, payload: ScanIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.scan(shipment_id, payload.code), "Pack scanned")


@router.post("/shipments/{shipment_id}/grn")
async def submit_grn(shipment_id: str, payload: GrnIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.submit_grn(shipment_id, payload), "GRN created")


@router.get("/grn/{grn_id}")
async def grn(grn_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.grn(grn_id), "GRN loaded")


@router.get("/grn/{grn_id}/print")
async def grn_print(grn_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.grn_print(grn_id), "GRN print loaded")


@router.get("/claims")
async def claims(
    service: ServiceDep,
    tab: str = Query(default="all"),
    q: str = Query(default=""),
) -> dict[str, object]:
    return ok(service.claims(tab, q), "Claims loaded")


@router.post("/claims")
async def create_claim(payload: ClaimIn, service: ServiceDep) -> dict[str, object]:
    return ok(service.create_claim(payload), "Claim submitted")


@router.get("/lots/{code}/trace")
async def trace(code: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.trace(code), "Traceability loaded")


@router.get("/lots/{code}/genealogy")
async def genealogy(code: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.genealogy(code), "Genealogy loaded")


@router.get("/shipments/{shipment_id}/quality-documents")
async def quality_documents(shipment_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.quality_documents(shipment_id), "Quality documents loaded")


@router.get("/shipments/{shipment_id}/documents")
async def documents(shipment_id: str, service: ServiceDep) -> dict[str, object]:
    return ok(service.documents(shipment_id), "Shipment documents loaded")
