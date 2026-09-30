import pytest

from kavak_auto_equity_agent.domain.states import InvalidTransitionError, State, assert_valid_transition


class TestAssertValidTransition:
    def test_invalid_transition_raises(self) -> None:
        with pytest.raises(InvalidTransitionError):
            assert_valid_transition(State.ELIGIBILITY, State.VALIDATION)
