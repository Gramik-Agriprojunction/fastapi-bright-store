from fastapi import APIRouter

from app.api.v1.endpoints import system
from app.modules.buyer.router import router as buyer_router
from app.modules.collection_centre.router import router as collection_centre_router
from app.modules.webtech.router import router as webtech_router
from app.modules.webtechAIAgent.reconciliation.router import router as reconciliation_router
from app.modules.webtechAIAgent.router import router as webtech_ai_agent_router

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(collection_centre_router)
api_router.include_router(buyer_router)
api_router.include_router(webtech_router)
api_router.include_router(webtech_ai_agent_router)
api_router.include_router(reconciliation_router)
