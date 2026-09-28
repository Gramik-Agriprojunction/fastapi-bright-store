from pydantic import BaseModel, Field


class ScanIn(BaseModel):
    code: str = Field(min_length=3)


class GrnIn(BaseModel):
    received_kg: float = Field(ge=0)
    received_packs: int = Field(ge=0)
    damaged_kg: float = Field(ge=0, default=0)
    damaged_packs: int = Field(ge=0, default=0)
    shortage_reason: str = ""
    photos: int = Field(ge=0, default=0)


class ClaimIn(BaseModel):
    grn_id: str = Field(min_length=3)
    claim_type: str = Field(min_length=3)
    claim_qty_kg: float = Field(gt=0)
    description: str = ""
    photos: int = Field(ge=0, default=0)
