"""Configurable business policies (arquitectura-v0.md, section 4). Frozen so a
handler can never mutate a shared instance by accident; a policy *change* is a
new `Policies` instance with a new `POLICY_VERSION`, picked up by `bootstrap.py`.
Every audit entry records which version decided the case (section 10)."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from kavak_auto_equity_agent.domain.models import ProfileTier

POLICY_VERSION = "2026-09-30.1"


class ScoreTier(BaseModel):
    """One row of the score-to-profile table (section 4). `min_score` is the
    lower bound (inclusive) of the bucket."""

    model_config = ConfigDict(frozen=True)

    tier: ProfileTier
    min_score: int
    annual_rate: Decimal
    max_term_months: int
    max_amount_pct: Decimal


class Policies(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str = POLICY_VERSION

    # Ingresos (section 4).
    income_tolerance: Decimal = Decimal("0.85")
    max_proof_age_days: int = 90

    # Identidad y domicilio (section 4).
    name_similarity_threshold: int = 90
    street_similarity_threshold: int = 80

    # Extraccion (section 4).
    min_extraction_confidence: Decimal = Decimal("0.80")

    # Perfiles por score (section 4). Below the lowest tier's min_score, the
    # case is rejected — see `tier_for_score`.
    score_tiers: tuple[ScoreTier, ...] = (
        ScoreTier(tier=ProfileTier.A, min_score=700, annual_rate=Decimal("0.36"), max_term_months=48, max_amount_pct=Decimal("0.70")),
        ScoreTier(tier=ProfileTier.B, min_score=600, annual_rate=Decimal("0.48"), max_term_months=36, max_amount_pct=Decimal("0.60")),
        ScoreTier(tier=ProfileTier.C, min_score=500, annual_rate=Decimal("0.60"), max_term_months=24, max_amount_pct=Decimal("0.50")),
    )

    # Calculo (section 4).
    max_installment_to_income_ratio: Decimal = Decimal("0.30")
    vat_rate: Decimal = Decimal("0.16")
    offered_terms_months: tuple[int, ...] = (12, 24, 36, 48)

    # Correcciones y agente (section 1 and section 2).
    max_correction_attempts: int = 2
    max_tool_retries: int = 3
    max_agent_steps: int = 10

    def tier_for_score(self, score: int) -> ScoreTier | None:
        """The tier whose bucket `score` falls into, or `None` if it's below
        every tier's `min_score` (section 4: score < 500 -> rejected)."""
        applicable = [tier for tier in self.score_tiers if score >= tier.min_score]
        if not applicable:
            return None
        return max(applicable, key=lambda tier: tier.min_score)


DEFAULT_POLICIES = Policies()
