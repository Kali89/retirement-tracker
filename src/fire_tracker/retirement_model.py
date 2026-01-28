"""Advanced retirement modeling with multiple pots and access ages."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from .currency import format_currency
from .models import Currency


class PotType(Enum):
    """Types of retirement pots with different access rules."""
    ISA = "isa"  # Accessible anytime
    UK_PENSION = "uk_pension"  # Accessible from 57
    SWEDISH_PRIVATE_PENSION = "swedish_private_pension"  # Accessible from 55
    SWEDISH_STATE_PENSION = "swedish_state_pension"  # Accessible from 66-69
    CASH = "cash"  # Accessible anytime
    STATE_PENSION = "state_pension"  # UK state pension (67+)


@dataclass
class RetirementPot:
    """A retirement pot with access rules and growth assumptions."""
    name: str
    pot_type: PotType
    balance: float
    currency: Currency
    annual_contribution: float = 0.0
    growth_rate: float = 0.04  # Real return above inflation
    accessible_age: int = 0  # Age when accessible
    payout_years: Optional[int] = None  # For Swedish pension, years over which to draw

    def project_balance(self, years: int, contributing: bool = True) -> float:
        """Project balance after n years of growth and contributions."""
        balance = self.balance
        annual_contrib = self.annual_contribution if contributing else 0
        for _ in range(years):
            balance = balance * (1 + self.growth_rate) + annual_contrib
        return balance


@dataclass
class RetirementScenario:
    """A complete retirement scenario with all pots and assumptions."""
    current_age: int
    retirement_age: int
    annual_expenses: float  # In base currency
    base_currency: Currency = Currency.GBP
    exchange_rate_sek_gbp: float = 0.073
    pots: list[RetirementPot] = field(default_factory=list)

    # State pension assumptions
    uk_state_pension_age: int = 67
    uk_state_pension_annual: float = 11500  # Current full new state pension

    def _to_gbp(self, amount: float, currency: Currency) -> float:
        """Convert amount to GBP."""
        if currency == Currency.GBP:
            return amount
        elif currency == Currency.SEK:
            return amount * self.exchange_rate_sek_gbp
        return amount

    def _to_currency(self, amount_gbp: float, currency: Currency) -> float:
        """Convert GBP to target currency."""
        if currency == Currency.GBP:
            return amount_gbp
        elif currency == Currency.SEK:
            return amount_gbp / self.exchange_rate_sek_gbp
        return amount_gbp


@dataclass
class YearProjection:
    """Projection for a single year."""
    age: int
    year: int

    # Pot balances at start of year (before withdrawals)
    isa_balance: float = 0
    uk_pension_balance: float = 0
    swedish_private_balance: float = 0  # In SEK
    swedish_state_balance: float = 0  # In SEK (notional)
    cash_balance: float = 0

    # Withdrawals by source
    isa_withdrawal: float = 0
    uk_pension_withdrawal: float = 0
    swedish_private_withdrawal: float = 0  # In GBP
    swedish_state_withdrawal: float = 0  # In GBP
    uk_state_pension: float = 0
    cash_withdrawal: float = 0

    # Income and expenses
    total_income: float = 0
    expenses_needed: float = 0
    shortfall: float = 0

    # Totals
    total_portfolio_gbp: float = 0

    # Milestones
    milestone: str = ""


def run_retirement_projection(
    scenario: RetirementScenario,
    projection_years: int = 60,
) -> list[YearProjection]:
    """Run a full retirement projection showing withdrawals from each pot."""

    projections = []
    current_year = date.today().year

    # Initialize pot balances
    isa_balance = sum(
        scenario._to_gbp(p.balance, p.currency)
        for p in scenario.pots if p.pot_type == PotType.ISA
    )
    uk_pension_balance = sum(
        scenario._to_gbp(p.balance, p.currency)
        for p in scenario.pots if p.pot_type == PotType.UK_PENSION
    )
    swedish_private_balance = sum(
        p.balance for p in scenario.pots
        if p.pot_type == PotType.SWEDISH_PRIVATE_PENSION
    )  # Keep in SEK
    swedish_state_balance = sum(
        p.balance for p in scenario.pots
        if p.pot_type == PotType.SWEDISH_STATE_PENSION
    )  # Keep in SEK (notional)
    cash_balance = sum(
        scenario._to_gbp(p.balance, p.currency)
        for p in scenario.pots if p.pot_type == PotType.CASH
    )

    # Get contribution rates
    isa_contribution = sum(
        scenario._to_gbp(p.annual_contribution, p.currency)
        for p in scenario.pots if p.pot_type == PotType.ISA
    )
    pension_contribution = sum(
        scenario._to_gbp(p.annual_contribution, p.currency)
        for p in scenario.pots if p.pot_type == PotType.UK_PENSION
    )

    # Get growth rates (use first of each type or default)
    isa_growth = next(
        (p.growth_rate for p in scenario.pots if p.pot_type == PotType.ISA),
        0.04
    )
    pension_growth = next(
        (p.growth_rate for p in scenario.pots if p.pot_type == PotType.UK_PENSION),
        0.04
    )
    swedish_private_growth = next(
        (p.growth_rate for p in scenario.pots if p.pot_type == PotType.SWEDISH_PRIVATE_PENSION),
        0.04
    )
    swedish_state_growth = next(
        (p.growth_rate for p in scenario.pots if p.pot_type == PotType.SWEDISH_STATE_PENSION),
        0.04
    )

    # Swedish pension payout config
    swedish_private_payout_years = next(
        (p.payout_years for p in scenario.pots if p.pot_type == PotType.SWEDISH_PRIVATE_PENSION),
        20  # Default 20 year payout
    )
    swedish_private_access_age = next(
        (p.accessible_age for p in scenario.pots if p.pot_type == PotType.SWEDISH_PRIVATE_PENSION),
        55
    )
    swedish_state_access_age = next(
        (p.accessible_age for p in scenario.pots if p.pot_type == PotType.SWEDISH_STATE_PENSION),
        66
    )

    # Track Swedish pension payout
    swedish_private_annual_payout = 0  # Calculated when accessed
    swedish_private_started = False
    swedish_state_annual_payout = 0
    swedish_state_started = False

    for year_offset in range(projection_years):
        age = scenario.current_age + year_offset
        year = current_year + year_offset
        is_retired = age >= scenario.retirement_age

        proj = YearProjection(age=age, year=year)

        # Record balances at start of year
        proj.isa_balance = isa_balance
        proj.uk_pension_balance = uk_pension_balance
        proj.swedish_private_balance = swedish_private_balance
        proj.swedish_state_balance = swedish_state_balance
        proj.cash_balance = cash_balance

        # Calculate total portfolio in GBP
        proj.total_portfolio_gbp = (
            isa_balance +
            uk_pension_balance +
            cash_balance +
            swedish_private_balance * scenario.exchange_rate_sek_gbp +
            swedish_state_balance * scenario.exchange_rate_sek_gbp
        )

        # Determine what's accessible
        isa_accessible = True  # Always accessible
        uk_pension_accessible = age >= 57
        swedish_private_accessible = age >= swedish_private_access_age
        swedish_state_accessible = age >= swedish_state_access_age
        uk_state_pension_active = age >= scenario.uk_state_pension_age

        # Initialize Swedish pension payouts when first accessed
        if swedish_private_accessible and not swedish_private_started and swedish_private_balance > 0:
            swedish_private_started = True
            # Calculate annual payout based on remaining balance and payout years
            payout_years = swedish_private_payout_years or 20
            swedish_private_annual_payout = swedish_private_balance / payout_years

        if swedish_state_accessible and not swedish_state_started and swedish_state_balance > 0:
            swedish_state_started = True
            # Swedish state pension typically paid over ~20 years
            swedish_state_annual_payout = swedish_state_balance / 20

        if is_retired:
            # Need to cover expenses
            expenses_needed = scenario.annual_expenses
            proj.expenses_needed = expenses_needed
            remaining_need = expenses_needed

            # UK State pension (if eligible)
            if uk_state_pension_active:
                state_pension = scenario.uk_state_pension_annual
                proj.uk_state_pension = state_pension
                remaining_need -= state_pension

            # Swedish state pension payout (if active)
            if swedish_state_started and swedish_state_balance > 0:
                payout_sek = min(swedish_state_annual_payout, swedish_state_balance)
                payout_gbp = payout_sek * scenario.exchange_rate_sek_gbp
                proj.swedish_state_withdrawal = payout_gbp
                swedish_state_balance -= payout_sek
                remaining_need -= payout_gbp

            # Swedish private pension payout (if active)
            if swedish_private_started and swedish_private_balance > 0:
                payout_sek = min(swedish_private_annual_payout, swedish_private_balance)
                payout_gbp = payout_sek * scenario.exchange_rate_sek_gbp
                proj.swedish_private_withdrawal = payout_gbp
                swedish_private_balance -= payout_sek
                remaining_need -= payout_gbp

            # Withdrawal priority: ISA first (tax-free), then UK pension
            if remaining_need > 0 and isa_balance > 0:
                withdrawal = min(remaining_need, isa_balance)
                proj.isa_withdrawal = withdrawal
                isa_balance -= withdrawal
                remaining_need -= withdrawal

            if remaining_need > 0 and uk_pension_accessible and uk_pension_balance > 0:
                withdrawal = min(remaining_need, uk_pension_balance)
                proj.uk_pension_withdrawal = withdrawal
                uk_pension_balance -= withdrawal
                remaining_need -= withdrawal

            # Cash as last resort
            if remaining_need > 0 and cash_balance > 0:
                withdrawal = min(remaining_need, cash_balance)
                proj.cash_withdrawal = withdrawal
                cash_balance -= withdrawal
                remaining_need -= withdrawal

            proj.shortfall = max(0, remaining_need)
            proj.total_income = (
                proj.isa_withdrawal +
                proj.uk_pension_withdrawal +
                proj.swedish_private_withdrawal +
                proj.swedish_state_withdrawal +
                proj.uk_state_pension +
                proj.cash_withdrawal
            )
        else:
            # Still working - add contributions
            isa_balance += isa_contribution
            uk_pension_balance += pension_contribution

        # Apply growth to remaining balances
        isa_balance *= (1 + isa_growth)
        uk_pension_balance *= (1 + pension_growth)
        if swedish_private_balance > 0:
            swedish_private_balance *= (1 + swedish_private_growth)
        if swedish_state_balance > 0:
            swedish_state_balance *= (1 + swedish_state_growth)

        projections.append(proj)

        # Stop if all funds depleted
        if is_retired and proj.total_portfolio_gbp < 100:
            break

    return projections


def format_projection_table(
    projections: list[YearProjection],
    show_all: bool = False,
) -> str:
    """Format projections as a readable table."""
    lines = []

    # Header
    lines.append(
        f"{'Age':<4} {'Year':<5} {'ISA':>12} {'UK Pension':>12} "
        f"{'Swe Priv':>10} {'Total':>12} {'Income':>10} {'Short':>8}"
    )
    lines.append("-" * 85)

    for proj in projections:
        if not show_all and proj.age < projections[0].age + 5:
            # Show first 5 years
            pass
        elif not show_all and proj.age > 45 and (proj.age - 45) % 5 != 0:
            # After retirement, show every 5 years
            continue

        swe_priv_gbp = proj.swedish_private_balance * 0.073

        shortfall_str = f"£{proj.shortfall:,.0f}" if proj.shortfall > 0 else "-"
        income_str = f"£{proj.total_income:,.0f}" if proj.total_income > 0 else "-"

        lines.append(
            f"{proj.age:<4} {proj.year:<5} "
            f"£{proj.isa_balance:>10,.0f} £{proj.uk_pension_balance:>10,.0f} "
            f"£{swe_priv_gbp:>8,.0f} £{proj.total_portfolio_gbp:>10,.0f} "
            f"{income_str:>10} {shortfall_str:>8}"
        )

    return "\n".join(lines)
