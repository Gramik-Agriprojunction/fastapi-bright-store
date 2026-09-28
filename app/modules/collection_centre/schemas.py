from pydantic import BaseModel, Field


class GateEntryIn(BaseModel):
    delivery_id: str | None = None
    harvest_lot: str = Field(min_length=3)
    vehicle_number: str = Field(min_length=4)
    driver_name: str = Field(min_length=2)


class WeighmentIn(BaseModel):
    gross_kg: float = Field(gt=0)
    tare_kg: float = Field(ge=0)
    confirm: bool = False


class AggregationIn(BaseModel):
    lot_ids: list[str] = Field(min_length=2)


class SendToQcIn(BaseModel):
    sent_by: str = "Manoj Verma"


class QcParametersIn(BaseModel):
    moisture: float = 13.2
    broken_grains: float = 2.5
    foreign_matter: float = 1.0
    damaged_grain: float = 1.2
    insect_damage: str = "Not Found"
    maturity: str = "Good"
    odour: str = "Pass"
    colour: str = "Pass"
    grain_size: str = "Pass"


class QcDecisionIn(BaseModel):
    decision: str = Field(pattern="^(accept|hold|reject)$")
    grade: str = "A"
    remarks: str = ""
    parameters: QcParametersIn = Field(default_factory=QcParametersIn)
    hold_reason: str = ""
    follow_up: str = ""
    reinspection_date: str = ""
    reject_reason: str = ""


class QcSampleIn(BaseModel):
    sample_type: str = "Primary Sample"
    sample_location: str = ""
    inspector: str = "Manoj Verma"
    remarks: str = ""
    photos: list[str] = Field(default_factory=list)


class QcInspectionIn(BaseModel):
    parameters: QcParametersIn = Field(default_factory=QcParametersIn)
    remarks: str = ""


class QcDocumentIn(BaseModel):
    name: str = Field(min_length=1)
    size_label: str = ""


class QcDocumentsIn(BaseModel):
    photos: list[str] = Field(default_factory=list)
    documents: list[QcDocumentIn] = Field(default_factory=list)
    remarks: str = ""


class QcLabIn(BaseModel):
    lab_name: str = "Agri Testing Lab"
    test_type: str = "Pesticide Residue"
    sample_id: str = ""
    expected_date: str = ""
    result: str = "Pass"
    report_name: str = ""


class QcReinspectIn(BaseModel):
    result: str = Field(pattern="^(accept|hold|reject)$")
    inspector: str = "Manoj Verma"
    remarks: str = ""


class PackhouseIn(BaseModel):
    pack_size_kg: float = Field(default=5, gt=0)


class DispatchIn(BaseModel):
    buyer_name: str = "Reliance Fresh"
    buyer_location: str = "Lucknow"
    purchase_order: str = "PO-12345"
    vehicle_number: str = "UP78BT1234"
    driver_name: str = "Ramesh Yadav"
    driver_contact: str = "9876543210"


class GrnIn(BaseModel):
    received_qty_kg: float = Field(ge=0)
    accepted_qty_kg: float = Field(ge=0)
    shortage_kg: float = Field(ge=0)
    damage_kg: float = Field(ge=0)
    condition: str = "Good"
    remarks: str = ""
