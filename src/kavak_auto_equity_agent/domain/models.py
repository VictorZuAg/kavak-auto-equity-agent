from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from kavak_auto_equity_agent.domain.states import INITIAL_STATE, State, assert_valid_transition


class EmploymentStatus(StrEnum):
    EMPLOYEE = "employee"
    SELF_EMPLOYED = "self_employed"


class Address(BaseModel):
    street: str
    postal_code: str = Field(pattern=r"^\d{5}$")
    city: str
    state: str


class Customer(BaseModel):
    name: str
    rfc: str
    address: Address
    employment_status: EmploymentStatus
    declared_monthly_income: Decimal = Field(ge=0, decimal_places=2)
    credit_bureau_authorization: bool = False


class Vehicle(BaseModel):
    make: str
    model: str
    year: int
    value: Decimal = Field(ge=0, decimal_places=2)
    declared_owner: str
    has_debt: bool
    has_second_key: bool


class KeyQuote(BaseModel):
    """Second key quote (arquitectura-v0.md, sections 1 and 4)."""

    cost: Decimal = Field(ge=0, decimal_places=2)
    provider: str
    # False = confirmed by the provider; True = reference price (fallback, section 2).
    estimated: bool = True


class Eligibility(BaseModel):
    result: bool | None = None
    reasons: list[str] = Field(default_factory=list)
    key_quote: KeyQuote | None = None


class ProfileTier(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    # Buro was consulted and the score is below the minimum (section 4: score < 500).
    # Distinct from `tier is None`, which means the buro has not been consulted yet.
    REJECTED = "rejected"


class Profile(BaseModel):
    """Risk profile assigned by the credit bureau (section 4: score-based profiles)."""

    score: int | None = Field(default=None, ge=0, le=1000)
    tier: ProfileTier | None = None
    annual_rate: Decimal | None = Field(default=None, ge=0)
    max_term_months: int | None = Field(default=None, ge=0)
    max_amount_pct: Decimal | None = Field(default=None, ge=0, le=1)


class Offer(BaseModel):
    """A financing offer (section 1 and section 4 'Calculo'). `amount` is the
    principal the customer receives; `financed_amount` also folds in the
    second key cost, since it is added to the financed amount and shown
    broken out rather than charged to the customer separately."""

    offer_id: str
    amount: Decimal = Field(ge=0, decimal_places=2)
    term_months: int = Field(ge=0)
    annual_rate: Decimal = Field(ge=0)
    installment: Decimal = Field(ge=0, decimal_places=2)
    key_cost: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    financed_amount: Decimal = Field(ge=0, decimal_places=2)

    @model_validator(mode="after")
    def _check_financed_amount(self) -> "Offer":
        if self.financed_amount != self.amount + self.key_cost:
            raise ValueError("financed_amount must equal amount + key_cost")
        return self


class Simulation(BaseModel):
    offers: list[Offer] = Field(default_factory=list)
    chosen_offer_id: str | None = None

    @model_validator(mode="after")
    def _check_chosen_offer_exists(self) -> "Simulation":
        if self.chosen_offer_id is not None:
            offer_ids = {offer.offer_id for offer in self.offers}
            if self.chosen_offer_id not in offer_ids:
                raise ValueError(f"chosen_offer_id {self.chosen_offer_id!r} is not among offers")
        return self


class DocumentType(StrEnum):
    PAYSTUB = "paystub"
    BANK_STATEMENT = "bank_statement"
    INE = "ine"
    PROOF_OF_ADDRESS = "proof_of_address"
    VEHICLE_REGISTRATION = "vehicle_registration"
    INVOICE = "invoice"


class ExtractedField(BaseModel):
    value: str
    confidence: float = Field(ge=0.0, le=1.0)


class Document(BaseModel):
    """Document attached by the customer (section 5). The content never lives
    here: only the hash and the fields already extracted by the extraction adapter."""

    document_id: str
    type: DocumentType
    hash: str
    extracted_fields: dict[str, ExtractedField] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    rule: str
    passed: bool
    evidence: str | None = None


class CorrectionAttempt(BaseModel):
    """Correction attempts per requirement (section 1: max 2 before escalating)."""

    requirement: str
    attempts: int = Field(default=0, ge=0)


class EscalationStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class Escalation(BaseModel):
    escalation_id: str
    reason: str
    status: EscalationStatus = EscalationStatus.OPEN
    resolution: str | None = None


class Case(BaseModel):
    """End-to-end case (arquitectura-v0.md, section 5). `status`/`version` are
    the fields that back the state machine and the optimistic lock."""

    case_id: str
    status: State = INITIAL_STATE
    # Only set while status is ESCALATED (section 1); holds the stage the
    # advisor can send the case back to.
    previous_status: State | None = None
    version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    customer: Customer
    vehicle: Vehicle
    eligibility: Eligibility = Field(default_factory=Eligibility)
    profile: Profile = Field(default_factory=Profile)
    simulation: Simulation = Field(default_factory=Simulation)
    documents: list[Document] = Field(default_factory=list)
    validations: list[ValidationResult] = Field(default_factory=list)
    correction_attempts: list[CorrectionAttempt] = Field(default_factory=list)
    escalations: list[Escalation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_previous_status(self) -> "Case":
        if self.status is State.ESCALATED and self.previous_status is None:
            raise ValueError("previous_status is required while status is ESCALATED")
        if self.status is not State.ESCALATED and self.previous_status is not None:
            raise ValueError("previous_status must be None outside ESCALATED")
        return self

    def transition_to(self, target: State) -> None:
        """Move the case to `target`, validated against the domain's transition
        table (states.py). Does not bump `version`: the repository does that on
        save, as part of the optimistic-lock write (section 10)."""
        assert_valid_transition(self.status, target, previous_status=self.previous_status)
        self.previous_status = self.status if target is State.ESCALATED else None
        self.status = target
        self.updated_at = datetime.now(UTC)
