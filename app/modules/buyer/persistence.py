from collections.abc import AsyncIterator
from dataclasses import asdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import engine, session_factory
from app.modules.buyer.models import BuyerRecord
from app.modules.buyer.repository import (
    BuyerClaim,
    BuyerGrn,
    BuyerMeta,
    BuyerShipment,
    BuyerStore,
    get_store,
)
from app.modules.buyer.service import BuyerService
from app.modules.collection_centre.persistence import use_crm_database


async def init_buyer_tables() -> None:
    if not use_crm_database():
        return
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _shipment_from_payload(payload: dict) -> BuyerShipment:
    data = dict(payload)
    data["events"] = list(data.get("events") or [])
    data["pack_lines"] = list(data.get("pack_lines") or [])
    return BuyerShipment(**data)


async def load_store(session: AsyncSession, store: BuyerStore) -> None:
    rows = (await session.scalars(select(BuyerRecord))).all()
    if not rows:
        store.reset()
        await save_store(session, store)
        return
    store.shipments.clear()
    store.grns.clear()
    store.claims.clear()
    store.meta = BuyerMeta()
    for row in rows:
        if row.kind == "meta":
            store.meta = BuyerMeta(**row.payload)
        elif row.kind == "shipment":
            store.shipments[row.record_id] = _shipment_from_payload(row.payload)
        elif row.kind == "grn":
            store.grns[row.record_id] = BuyerGrn(**row.payload)
        elif row.kind == "claim":
            store.claims[row.record_id] = BuyerClaim(**row.payload)


async def save_store(session: AsyncSession, store: BuyerStore) -> None:
    wanted: dict[tuple[str, str], dict] = {("meta", "meta"): asdict(store.meta)}
    wanted.update({("shipment", ship.id): asdict(ship) for ship in store.shipments.values()})
    wanted.update({("grn", grn.id): asdict(grn) for grn in store.grns.values()})
    wanted.update({("claim", claim.id): asdict(claim) for claim in store.claims.values()})
    existing = {
        (row.kind, row.record_id): row
        for row in (await session.scalars(select(BuyerRecord))).all()
    }
    for kind, record_id in existing:
        if (kind, record_id) not in wanted:
            await session.execute(
                delete(BuyerRecord).where(
                    BuyerRecord.kind == kind,
                    BuyerRecord.record_id == record_id,
                )
            )
    for (kind, record_id), payload in wanted.items():
        row = existing.get((kind, record_id))
        if row is None:
            session.add(BuyerRecord(kind=kind, record_id=record_id, payload=payload))
        else:
            row.payload = payload
    await session.commit()


async def get_buyer_service() -> AsyncIterator[BuyerService]:
    if not use_crm_database():
        yield BuyerService(get_store())
        return
    store = BuyerStore(seed=False)
    async with session_factory() as session:
        await load_store(session, store)
        service = BuyerService(store)
        try:
            yield service
        except Exception:
            await session.rollback()
            raise
        else:
            await save_store(session, store)
