import os
from collections.abc import AsyncIterator
from dataclasses import asdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import engine, session_factory
from app.modules.collection_centre.crm_trace import merge_crm_trace
from app.modules.collection_centre.models import CcRecord
from app.modules.collection_centre.repository import (
    CollectionStore,
    Delivery,
    JourneyEvent,
    Lot,
    Shipment,
    get_store,
)
from app.modules.collection_centre.service import CollectionService


def use_crm_database() -> bool:
    return os.getenv("COLLECTION_BACKEND", "database") != "memory"


async def init_collection_tables() -> None:
    if not use_crm_database():
        return
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _lot_from_payload(payload: dict) -> Lot:
    data = dict(payload)
    journey = [JourneyEvent(**event) for event in data.pop("journey", [])]
    return Lot(**data, journey=journey)


async def load_store(session: AsyncSession, store: CollectionStore) -> None:
    rows = (await session.scalars(select(CcRecord))).all()
    if not rows:
        store.reset()
    else:
        store.deliveries.clear()
        store.lots.clear()
        store.shipments.clear()
        for row in rows:
            if row.kind == "delivery":
                store.deliveries[row.record_id] = Delivery(**row.payload)
            elif row.kind == "lot":
                store.lots[row.record_id] = _lot_from_payload(row.payload)
            elif row.kind == "shipment":
                store.shipments[row.record_id] = Shipment(**row.payload)
        store.sync_sequences()
    await merge_crm_trace(session, store)


async def save_store(session: AsyncSession, store: CollectionStore) -> None:
    wanted = {
        ("delivery", delivery.id): asdict(delivery) for delivery in store.deliveries.values()
    }
    wanted.update({("lot", lot.id): asdict(lot) for lot in store.lots.values()})
    wanted.update(
        {("shipment", shipment.id): asdict(shipment) for shipment in store.shipments.values()}
    )
    existing = {
        (row.kind, row.record_id): row
        for row in (await session.scalars(select(CcRecord))).all()
    }
    for kind, record_id in existing:
        if (kind, record_id) not in wanted:
            await session.execute(
                delete(CcRecord).where(
                    CcRecord.kind == kind,
                    CcRecord.record_id == record_id,
                )
            )
    for (kind, record_id), payload in wanted.items():
        row = existing.get((kind, record_id))
        if row is None:
            session.add(CcRecord(kind=kind, record_id=record_id, payload=payload))
        else:
            row.payload = payload
    await session.commit()


async def get_collection_service() -> AsyncIterator[CollectionService]:
    if not use_crm_database():
        yield CollectionService(get_store())
        return
    store = CollectionStore(seed=False)
    async with session_factory() as session:
        await load_store(session, store)
        service = CollectionService(store)
        try:
            yield service
        except Exception:
            await session.rollback()
            raise
        else:
            await save_store(session, store)
