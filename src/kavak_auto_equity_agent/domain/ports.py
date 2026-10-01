"""Ports of the hexagonal architecture (arquitectura-v0.md, section 7): the
domain depends on these `Protocol`s, never on a concrete provider, database or
LLM SDK. Adapters (mocks for the demo, real providers in production) implement
them; `bootstrap.py` wires the adapters and composes fallbacks (section 2)."""

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from kavak_auto_equity_agent.domain.models import Case, DocumentType, ExtractedField, KeyQuote
from kavak_auto_equity_agent.domain.states import State


class CreditBureauResult(BaseModel):
    """Raw bureau response. Turning `score` into a tier, rate, term and max
    amount is a rules decision (section 3), not the bureau's — the port only
    reports what the provider actually said."""

    score: int = Field(ge=0, le=1000)


@runtime_checkable
class CreditBureauPort(Protocol):
    def query(self, rfc: str) -> CreditBureauResult: ...


@runtime_checkable
class KeyQuotePort(Protocol):
    """Backs `quote_second_key`. The reference-price fallback (section 2) is
    just another implementation of this Protocol that always returns
    `KeyQuote(estimated=True)`."""

    def quote(self, make: str, model: str, year: int) -> KeyQuote: ...


@runtime_checkable
class DocumentExtractorPort(Protocol):
    """Backs `extract_document`. Per section 9, the extractor has no tools and
    no side effects: it only turns document content into typed fields with a
    confidence per field, never an action."""

    def extract(self, document_type: DocumentType, content: bytes) -> dict[str, ExtractedField]: ...


@runtime_checkable
class CaseRepositoryPort(Protocol):
    """Case persistence with optimistic locking (section 10). `save` writes
    conditioned on `expected_version`, bumps it and refreshes `updated_at` on
    success, and raises `ConcurrencyError` on a stale write instead of
    retrying blindly — the caller must reload and re-check preconditions."""

    def create(self, case: Case) -> Case: ...

    def get(self, case_id: str) -> Case: ...  # raises CaseNotFoundError if missing

    def save(self, case: Case, expected_version: int) -> Case: ...  # raises ConcurrencyError on mismatch


class AuditEntry(BaseModel):
    """One row of the append-only audit log (section 5). Every tool call,
    successful or rejected, produces exactly one of these. `status_before`/
    `status_after` can be unknown (`None`) when the call is rejected before
    the case is even loaded, e.g. a permission check on step 2 of the
    registry pipeline, which runs before step 4 loads the case."""

    timestamp: datetime
    case_id: str
    actor_id: str
    role: str
    tool: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None
    idempotency_key: str | None = None
    status_before: State | None = None
    status_after: State | None = None
    policy_version: str
    prompt_version: str | None = None
    model: str | None = None


@runtime_checkable
class AuditLogPort(Protocol):
    """Append-only by contract (section 5): no update or delete method is
    exposed. `list_for_case` backs the traceability described in section 8.3
    (reconstruct any case step by step) and the advisor's case history (section 6);
    `list_all` backs the metrics computed in `metrics.py` (section 8)."""

    def record(self, entry: AuditEntry) -> None: ...

    def list_for_case(self, case_id: str) -> list[AuditEntry]: ...

    def list_all(self) -> list[AuditEntry]: ...


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)


@runtime_checkable
class LLMPort(Protocol):
    """Conversation and decision LLM (section 2). Provider-agnostic on
    purpose: `FallbackLLM` holds a list of `LLMPort` implementations and tries
    them in order, and the rest of the system never knows a fallback exists."""

    def complete(self, messages: list[LLMMessage], tools: list[dict[str, Any]]) -> LLMResponse: ...
