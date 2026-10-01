"""Tool-layer contracts (arquitectura-v0.md, section 2). `ToolRegistry`
(`tools/registry.py`) is the only thing that calls a `ToolSpec.handler`
directly — the agent and the advisor backoffice both go through it, so both
get the same permission, idempotency and audit guarantees."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from kavak_auto_equity_agent.domain.models import Case
from kavak_auto_equity_agent.domain.ports import AuditLogPort, CaseRepositoryPort
from kavak_auto_equity_agent.domain.states import State
from kavak_auto_equity_agent.rules.policies import Policies


class Role(StrEnum):
    AGENT = "agent"
    ADVISOR = "advisor"
    APPROVER = "approver"


class ToolContext(BaseModel):
    actor_id: str
    role: Role
    # The agent always has one; the advisor may act without being scoped to a case.
    session_case_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDeps:
    """What a handler needs besides the case and its validated input: the
    ports it may call and the policies that decide the business rules."""

    case_repository: CaseRepositoryPort
    audit_log: AuditLogPort
    policies: Policies


class ToolSpec(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    input_model: type[BaseModel]  # must include case_id
    output_model: type[BaseModel]
    allowed_roles: frozenset[Role]
    allowed_states: frozenset[State]
    handler: Callable[[Case, BaseModel, ToolDeps], BaseModel]
    retryable: bool = True


class ToolResult(BaseModel):
    ok: bool
    output: dict | None = None
    error: str | None = None
    error_type: str | None = None
