"""Domain errors (arquitectura-v0.md, section 2 and spec 01). `tools/registry.py`
never lets any of these escape `ToolRegistry.execute`: it converts them into a
`ToolResult(ok=False, ...)`. `TransientError` is the only one worth retrying —
everything else is a validation or business outcome that a retry can't change."""


class DomainError(Exception):
    """Base class for every domain error."""


class CaseNotFoundError(DomainError):
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        super().__init__(f"Case {case_id!r} not found")


class ConcurrencyError(DomainError):
    """Raised by `CaseRepositoryPort.save` when `expected_version` no longer
    matches the stored version (section 10: optimistic locking)."""

    def __init__(self, case_id: str, expected_version: int) -> None:
        self.case_id = case_id
        self.expected_version = expected_version
        super().__init__(f"Case {case_id!r} was modified concurrently (expected version {expected_version})")


class PermissionDeniedError(DomainError):
    def __init__(self, role: str, tool: str) -> None:
        self.role = role
        self.tool = tool
        super().__init__(f"Role {role!r} is not allowed to call {tool!r}")


class OutOfScopeError(DomainError):
    """Raised when a tool call's `case_id` doesn't match the session's
    `session_case_id` (section 2: each agent session is scoped to one case)."""

    def __init__(self, session_case_id: str, requested_case_id: str) -> None:
        self.session_case_id = session_case_id
        self.requested_case_id = requested_case_id
        super().__init__(f"Session is scoped to case {session_case_id!r}, not {requested_case_id!r}")


class PreconditionFailedError(DomainError):
    def __init__(self, tool: str, state: str) -> None:
        self.tool = tool
        self.state = state
        super().__init__(f"{tool!r} cannot run while the case is in {state!r}")


class InvalidInputError(DomainError):
    def __init__(self, tool: str, detail: str) -> None:
        self.tool = tool
        self.detail = detail
        super().__init__(f"Invalid input for {tool!r}: {detail}")


class TransientError(DomainError):
    """The only retryable error (section 2): a timeout, a provider 5xx or a
    rate limit. Business and validation outcomes are never transient."""
