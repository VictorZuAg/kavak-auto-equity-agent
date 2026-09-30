from decimal import Decimal

import pytest
from pydantic import ValidationError

from kavak_auto_equity_agent.domain.models import (
    Address,
    Case,
    Customer,
    EmploymentStatus,
    Offer,
    Simulation,
    Vehicle,
)
from kavak_auto_equity_agent.domain.states import InvalidTransitionError, State


def make_address(**overrides: object) -> Address:
    defaults: dict[str, object] = dict(
        street="Av. Reforma 1", postal_code="06600", city="CDMX", state="CDMX"
    )
    defaults.update(overrides)
    return Address(**defaults)


def make_customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = dict(
        name="Juan Perez",
        rfc="PEGJ800101AB1",
        address=make_address(),
        employment_status=EmploymentStatus.EMPLOYEE,
        declared_monthly_income=Decimal("20000.00"),
    )
    defaults.update(overrides)
    return Customer(**defaults)


def make_vehicle(**overrides: object) -> Vehicle:
    defaults: dict[str, object] = dict(
        make="Nissan",
        model="Versa",
        year=2020,
        value=Decimal("250000.00"),
        declared_owner="Juan Perez",
        has_debt=False,
        has_second_key=True,
    )
    defaults.update(overrides)
    return Vehicle(**defaults)


def make_case(*, status: State = State.ELIGIBILITY, previous_status: State | None = None) -> Case:
    return Case(
        case_id="c1",
        status=status,
        previous_status=previous_status,
        customer=make_customer(),
        vehicle=make_vehicle(),
    )


def make_offer(**overrides: object) -> Offer:
    defaults: dict[str, object] = dict(
        offer_id="o1",
        amount=Decimal("100000.00"),
        term_months=36,
        annual_rate=Decimal("0.48"),
        installment=Decimal("5000.00"),
        key_cost=Decimal("0.00"),
        financed_amount=Decimal("100000.00"),
    )
    defaults.update(overrides)
    return Offer(**defaults)


class TestTransitionTo:
    def test_invalid_target_raises(self) -> None:
        case = make_case(status=State.ELIGIBILITY)
        with pytest.raises(InvalidTransitionError):
            case.transition_to(State.VALIDATION)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (State.ELIGIBILITY, State.VALIDATION),
            (State.PROFILING, State.DOCUMENTS),
            (State.SIMULATION, State.READY_FOR_LENDER),
            (State.DOCUMENTS, State.SIMULATION),
            (State.VALIDATION, State.SIMULATION),
        ],
    )
    def test_invalid_transitions_are_rejected(self, current: State, target: State) -> None:
        case = make_case(status=current)
        with pytest.raises(InvalidTransitionError):
            case.transition_to(target)

    def test_escalating_stores_previous_status(self) -> None:
        case = make_case(status=State.PROFILING)
        case.transition_to(State.ESCALATED)
        assert case.status is State.ESCALATED
        assert case.previous_status is State.PROFILING

    def test_returning_from_escalated_clears_previous_status(self) -> None:
        case = make_case(status=State.PROFILING)
        case.transition_to(State.ESCALATED)
        case.transition_to(State.PROFILING)
        assert case.status is State.PROFILING
        assert case.previous_status is None

    def test_escalated_can_only_return_to_previous_status(self) -> None:
        case = make_case(status=State.ESCALATED, previous_status=State.DOCUMENTS)
        with pytest.raises(InvalidTransitionError):
            case.transition_to(State.VALIDATION)

    def test_escalated_can_always_reject(self) -> None:
        case = make_case(status=State.ESCALATED, previous_status=State.DOCUMENTS)
        case.transition_to(State.REJECTED)
        assert case.status is State.REJECTED
        assert case.previous_status is None

    def test_transition_to_does_not_bump_version(self) -> None:
        case = make_case(status=State.ELIGIBILITY)
        case.transition_to(State.PROFILING)
        assert case.version == 0


class TestPreviousStatusInvariant:
    def test_escalated_without_previous_status_fails(self) -> None:
        with pytest.raises(ValidationError):
            make_case(status=State.ESCALATED, previous_status=None)

    def test_non_escalated_with_previous_status_fails(self) -> None:
        with pytest.raises(ValidationError):
            make_case(status=State.PROFILING, previous_status=State.ELIGIBILITY)


class TestSimulation:
    def test_chosen_offer_must_exist(self) -> None:
        with pytest.raises(ValidationError):
            Simulation(offers=[make_offer()], chosen_offer_id="does-not-exist")

    def test_chosen_offer_matching_an_offer_is_valid(self) -> None:
        simulation = Simulation(offers=[make_offer(offer_id="o1")], chosen_offer_id="o1")
        assert simulation.chosen_offer_id == "o1"


class TestOffer:
    def test_financed_amount_must_equal_amount_plus_key_cost(self) -> None:
        with pytest.raises(ValidationError):
            make_offer(key_cost=Decimal("3000.00"), financed_amount=Decimal("100000.00"))

    def test_financed_amount_matching_amount_plus_key_cost_is_valid(self) -> None:
        offer = make_offer(key_cost=Decimal("3000.00"), financed_amount=Decimal("103000.00"))
        assert offer.financed_amount == Decimal("103000.00")


class TestAddress:
    @pytest.mark.parametrize("postal_code", ["123", "123456", "abcde", "1234a"])
    def test_invalid_postal_code_is_rejected(self, postal_code: str) -> None:
        with pytest.raises(ValidationError):
            make_address(postal_code=postal_code)

    def test_valid_postal_code_is_accepted(self) -> None:
        assert make_address(postal_code="06600").postal_code == "06600"
