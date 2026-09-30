from enum import StrEnum


class State(StrEnum):
    ELIGIBILITY = "eligibility"
    PROFILING = "profiling"
    SIMULATION = "simulation"
    DOCUMENTS = "documents"
    VALIDATION = "validation"
    PENDING_CORRECTION = "pending_correction"
    ESCALATED = "escalated"
    READY_FOR_LENDER = "ready_for_lender"
    REJECTED = "rejected"


# A case starts in ELIGIBILITY (arquitectura-v0.md, section 1); there is no "new" state.
INITIAL_STATE = State.ELIGIBILITY

# Terminal states: never reopened, a retry is a new case.
TERMINAL_STATES: frozenset[State] = frozenset({State.READY_FOR_LENDER, State.REJECTED})

# Valid transition table (arquitectura-v0.md, section 1). A transition not
# listed here raises InvalidTransitionError in the domain; the LLM never decides it.
VALID_TRANSITIONS: dict[State, frozenset[State]] = {
    State.ELIGIBILITY: frozenset({State.PROFILING, State.REJECTED, State.ESCALATED}),
    State.PROFILING: frozenset({State.SIMULATION, State.REJECTED, State.ESCALATED}),
    State.SIMULATION: frozenset({State.DOCUMENTS, State.ESCALATED}),
    State.DOCUMENTS: frozenset({State.VALIDATION, State.PENDING_CORRECTION, State.ESCALATED}),
    State.VALIDATION: frozenset({State.READY_FOR_LENDER, State.PENDING_CORRECTION, State.ESCALATED}),
    State.PENDING_CORRECTION: frozenset({State.DOCUMENTS, State.ESCALATED}),
    # From ESCALATED the advisor sends the case back to previous_status (any
    # non-terminal state) or rejects it; the agent cannot resolve escalations.
    # This table only says the target state is reachable in principle: a
    # return to a non-terminal state must also match previous_status, which
    # is_valid_transition/assert_valid_transition validate below.
    State.ESCALATED: frozenset(
        {
            State.ELIGIBILITY,
            State.PROFILING,
            State.SIMULATION,
            State.DOCUMENTS,
            State.VALIDATION,
            State.PENDING_CORRECTION,
            State.REJECTED,
        }
    ),
    State.READY_FOR_LENDER: frozenset(),
    State.REJECTED: frozenset(),
}


class InvalidTransitionError(Exception):
    def __init__(self, current: State, target: State, *, previous_status: State | None = None) -> None:
        self.current = current
        self.target = target
        self.previous_status = previous_status
        message = f"Invalid transition: {current} -> {target}"
        if current is State.ESCALATED:
            message += f" (previous_status={previous_status})"
        super().__init__(message)


def is_terminal(state: State) -> bool:
    return state in TERMINAL_STATES


def is_valid_transition(current: State, target: State, *, previous_status: State | None = None) -> bool:
    if target not in VALID_TRANSITIONS[current]:
        return False
    if current is State.ESCALATED and target is not State.REJECTED:
        # A return from ESCALATED is only valid to the stage the case was at.
        return target == previous_status
    return True


def assert_valid_transition(current: State, target: State, *, previous_status: State | None = None) -> None:
    if not is_valid_transition(current, target, previous_status=previous_status):
        raise InvalidTransitionError(current, target, previous_status=previous_status)
