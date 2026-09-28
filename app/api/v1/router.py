from fastapi import APIRouter

from app.api.v1.endpoints import system
from app.modules.buyer.router import router as buyer_router
from app.modules.collection_centre.router import router as collection_centre_router

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(collection_centre_router)
api_router.include_router(buyer_router)
