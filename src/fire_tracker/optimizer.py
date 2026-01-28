"""Optimize two-phase withdrawal strategy for retirement."""

from dataclasses import dataclass
from typing import Optional

from .models import AccountType, Currency, Portfolio


@dataclass
class EarliestRetirementResult:
    """Result of earliest retirement calculation."""
    earliest_age: int
    isa_at_retirement: float
    isa_needed: float
    surplus: float
    bridge_years: int
    pension_at_57: float
    max_bridge_spend: float  # Max spending during bridge given ISA


@dataclass
class OptimizationResult:
    """Result of a two-phase optimization."""
    bridge_spend: float
    pension_spend: float
    bridge_years: int
    pension_years: int
    total_lifetime_spending: float
    remaining_at_end: float
    monthly_bridge: float
    monthly_pension: float
    jump_percent: float


@dataclass
class OptimizationParams:
    """Parameters for retirement optimization."""
    current_age: int
    retirement_age: int
    death_age: int
    pension_access_age: int = 57
    swedish_private_access_age: int = 55
    swedish_state_access_age: int = 66
    uk_state_pension_age: int = 67
    uk_state_pension_annual: float = 11500
    growth_rate: float = 0.04
    sek_to_gbp: float = 0.073
    pension_contribution_stop_age: Optional[int] = None
    pension_contribution_full: float = 60000
    pension_contribution_min: float = 24960
    isa_contribution: float = 40000
    swedish_payout_years: int = 20


def run_simulation(
    bridge_spend: float,
    pension_spend: float,
    isa_start: float,
    uk_pension_start: float,
    swedish_private_sek: float,
    swedish_state_sek: float,
    cash_start: float,
    params: OptimizationParams,
) -> tuple[float, int]:
    """
    Simulate retirement with two-phase spending.

    Returns (final_balance, end_age) where end_age < death_age means failure.
    """
    growth = params.growth_rate
    sek_to_gbp = params.sek_to_gbp

    isa = isa_start
    uk_pen = uk_pension_start
    swe_priv = swedish_private_sek
    swe_state = swedish_state_sek
    cash = cash_start

    swe_priv_started = False
    swe_priv_annual = 0
    swe_state_started = False
    swe_state_annual = 0

    for age in range(params.current_age, params.death_age + 1):
        # Pre-retirement: accumulation phase
        if age < params.retirement_age:
            # Add contributions
            isa += params.isa_contribution

            if params.pension_contribution_stop_age and age >= params.pension_contribution_stop_age:
                uk_pen += params.pension_contribution_min
            else:
                uk_pen += params.pension_contribution_full

            # Apply growth
            isa *= (1 + growth)
            uk_pen *= (1 + growth)
            swe_priv *= (1 + growth)
            swe_state *= (1 + growth)
            continue

        # Retirement: withdrawal phase
        if age < params.pension_access_age:
            target_spend = bridge_spend
        else:
            target_spend = pension_spend

        # Start Swedish private pension payout
        if age == params.swedish_private_access_age and not swe_priv_started:
            swe_priv_started = True
            swe_priv_annual = swe_priv / params.swedish_payout_years

        # Start Swedish state pension payout
        if age == params.swedish_state_access_age and not swe_state_started:
            swe_state_started = True
            swe_state_annual = swe_state / 20  # Typically 20 year payout

        # Calculate income from pensions
        income = 0

        # Swedish private pension
        if swe_priv_started and swe_priv > 0:
            payout = min(swe_priv_annual, swe_priv)
            income += payout * sek_to_gbp
            swe_priv -= payout

        # Swedish state pension
        if swe_state_started and swe_state > 0:
            payout = min(swe_state_annual, swe_state)
            income += payout * sek_to_gbp
            swe_state -= payout

        # UK state pension
        if age >= params.uk_state_pension_age:
            income += params.uk_state_pension_annual

        # Calculate remaining need after pension income
        remaining_need = target_spend - income

        # Draw from cash first
        if remaining_need > 0 and cash > 0:
            withdrawal = min(remaining_need, cash)
            cash -= withdrawal
            remaining_need -= withdrawal

        # Draw from ISA
        if remaining_need > 0 and isa > 0:
            withdrawal = min(remaining_need, isa)
            isa -= withdrawal
            remaining_need -= withdrawal

        # Draw from UK pension (if accessible)
        if remaining_need > 0 and age >= params.pension_access_age:
            uk_pen -= remaining_need
            remaining_need = 0

        # Check for failure
        if uk_pen < 0:
            return -999999, age
        if remaining_need > 0 and age < params.pension_access_age:
            return -999999, age

        # Apply growth to remaining balances
        isa *= (1 + growth)
        uk_pen *= (1 + growth)
        if swe_priv > 0:
            swe_priv *= (1 + growth)
        if swe_state > 0:
            swe_state *= (1 + growth)
        cash *= (1 + growth * 0.5)  # Lower growth for cash

    total = isa + uk_pen + swe_priv * sek_to_gbp + swe_state * sek_to_gbp + cash
    return total, params.death_age


def find_optimal_pension_spend(
    bridge_spend: float,
    isa_start: float,
    uk_pension_start: float,
    swedish_private_sek: float,
    swedish_state_sek: float,
    cash_start: float,
    params: OptimizationParams,
) -> float:
    """Find the maximum sustainable pension phase spending for a given bridge spend."""
    low, high = 50000, 200000

    while high - low > 500:
        mid = (low + high) / 2
        final, end_age = run_simulation(
            bridge_spend, mid,
            isa_start, uk_pension_start, swedish_private_sek, swedish_state_sek, cash_start,
            params
        )
        if final >= 0 and end_age >= params.death_age:
            low = mid
        else:
            high = mid

    return low


def optimize_withdrawal_strategy(
    portfolio: Portfolio,
    params: OptimizationParams,
) -> list[OptimizationResult]:
    """
    Find all viable two-phase withdrawal strategies.

    Returns a list of OptimizationResult sorted by total lifetime spending.
    """
    # Extract balances from portfolio
    isa_balance = sum(
        a.balance for a in portfolio.accounts
        if a.type in (AccountType.SS_ISA, AccountType.CASH_ISA) and a.currency == Currency.GBP
    )

    uk_pension_balance = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.UK_PENSION and a.currency == Currency.GBP
    )

    swedish_private_sek = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.SWEDISH_PENSION and "state" not in a.name.lower()
    )

    swedish_state_sek = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.SWEDISH_PENSION and "state" in a.name.lower()
    )

    cash_balance = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.CASH and a.currency == Currency.GBP
    )

    # Update params with contribution info from portfolio
    if portfolio.income:
        params.pension_contribution_min = portfolio.income.gross_salary * 0.12

    isa_contribution = sum(
        a.monthly_contribution * 12 for a in portfolio.accounts
        if a.type in (AccountType.SS_ISA, AccountType.CASH_ISA) and a.currency == Currency.GBP
    )
    if isa_contribution > 0:
        params.isa_contribution = isa_contribution

    pension_contribution = sum(
        a.monthly_contribution * 12 for a in portfolio.accounts
        if a.type == AccountType.UK_PENSION and a.currency == Currency.GBP
    )
    if pension_contribution > 0:
        params.pension_contribution_full = pension_contribution

    results = []
    bridge_years = params.pension_access_age - params.retirement_age
    pension_years = params.death_age - params.pension_access_age + 1

    # Try different bridge spending levels
    for bridge_spend in range(30000, 120000, 5000):
        pension_spend = find_optimal_pension_spend(
            bridge_spend,
            isa_balance, uk_pension_balance, swedish_private_sek, swedish_state_sek, cash_balance,
            params
        )

        final, end_age = run_simulation(
            bridge_spend, pension_spend,
            isa_balance, uk_pension_balance, swedish_private_sek, swedish_state_sek, cash_balance,
            params
        )

        if final >= 0 and end_age >= params.death_age and final < 200000:
            total = bridge_spend * bridge_years + pension_spend * pension_years
            jump_percent = ((pension_spend / bridge_spend) - 1) * 100 if bridge_spend > 0 else 0

            results.append(OptimizationResult(
                bridge_spend=bridge_spend,
                pension_spend=pension_spend,
                bridge_years=bridge_years,
                pension_years=pension_years,
                total_lifetime_spending=total,
                remaining_at_end=final,
                monthly_bridge=bridge_spend / 12,
                monthly_pension=pension_spend / 12,
                jump_percent=jump_percent,
            ))

    # Sort by total lifetime spending (descending)
    results.sort(key=lambda r: r.total_lifetime_spending, reverse=True)

    return results


def get_balances_at_retirement(
    portfolio: Portfolio,
    params: OptimizationParams,
) -> dict:
    """Project balances forward to retirement age."""
    growth = params.growth_rate
    years_to_retirement = params.retirement_age - params.current_age

    # Current balances
    isa = sum(
        a.balance for a in portfolio.accounts
        if a.type in (AccountType.SS_ISA, AccountType.CASH_ISA) and a.currency == Currency.GBP
    )
    uk_pension = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.UK_PENSION and a.currency == Currency.GBP
    )
    swedish_private = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.SWEDISH_PENSION and "state" not in a.name.lower()
    )
    swedish_state = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.SWEDISH_PENSION and "state" in a.name.lower()
    )
    cash = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.CASH and a.currency == Currency.GBP
    )

    # Project forward
    for age in range(params.current_age, params.retirement_age):
        # Contributions
        isa += params.isa_contribution

        if params.pension_contribution_stop_age and age >= params.pension_contribution_stop_age:
            uk_pension += params.pension_contribution_min
        else:
            uk_pension += params.pension_contribution_full

        # Growth
        isa *= (1 + growth)
        uk_pension *= (1 + growth)
        swedish_private *= (1 + growth)
        swedish_state *= (1 + growth)

    return {
        "isa": isa,
        "uk_pension": uk_pension,
        "swedish_private_sek": swedish_private,
        "swedish_state_sek": swedish_state,
        "cash": cash,
        "total_gbp": isa + uk_pension + cash + (swedish_private + swedish_state) * params.sek_to_gbp,
    }


def calculate_isa_needed_for_bridge(
    retirement_age: int,
    pension_access_age: int,
    annual_spending: float,
    swedish_private_access_age: int = 55,
    swedish_private_annual: float = 5275,
    growth_rate: float = 0.04,
) -> float:
    """Calculate ISA balance needed at retirement to bridge to pension access.

    Works backwards from pension access age to determine how much ISA
    is needed to sustain the target spending level.
    """
    if retirement_age >= pension_access_age:
        return 0  # No bridge needed

    isa_needed = 0

    # Work backwards from pension access age
    for age in range(pension_access_age - 1, retirement_age - 1, -1):
        # Swedish private pension helps from its access age
        if age >= swedish_private_access_age:
            withdrawal = annual_spending - swedish_private_annual
        else:
            withdrawal = annual_spending

        # Need to have (isa_needed + withdrawal) at start of year
        # which after growth becomes isa_needed at end of year
        isa_needed = (isa_needed + withdrawal) / (1 + growth_rate)

    return isa_needed


def calculate_max_bridge_spending(
    isa_at_retirement: float,
    retirement_age: int,
    pension_access_age: int,
    swedish_private_access_age: int = 55,
    swedish_private_annual: float = 5275,
    growth_rate: float = 0.04,
) -> float:
    """Calculate maximum sustainable spending during bridge given ISA balance."""
    if retirement_age >= pension_access_age:
        return float('inf')  # No bridge constraint

    # Binary search for max spending
    low, high = 30000, 200000

    while high - low > 100:
        mid = (low + high) / 2
        needed = calculate_isa_needed_for_bridge(
            retirement_age, pension_access_age, mid,
            swedish_private_access_age, swedish_private_annual, growth_rate
        )
        if needed <= isa_at_retirement:
            low = mid
        else:
            high = mid

    return low


def find_earliest_retirement(
    portfolio: Portfolio,
    min_annual_spending: float,
    params: OptimizationParams,
) -> list[dict]:
    """Find the earliest retirement age given minimum spending requirement.

    Returns a list of retirement ages with their ISA projections.
    """
    # Get current balances
    isa_now = sum(
        a.balance for a in portfolio.accounts
        if a.type in (AccountType.SS_ISA, AccountType.CASH_ISA) and a.currency == Currency.GBP
    )
    pension_now = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.UK_PENSION and a.currency == Currency.GBP
    )
    swe_priv_now = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.SWEDISH_PENSION and "state" not in a.name.lower()
    )

    # Swedish private annual payout (calculated at access age)
    years_to_swedish = params.swedish_private_access_age - params.current_age
    swe_priv_at_access = swe_priv_now * ((1 + params.growth_rate) ** years_to_swedish)
    swedish_private_annual = (swe_priv_at_access / params.swedish_payout_years) * params.sek_to_gbp

    results = []

    for retire_age in range(params.current_age, 60):
        # Project ISA to retirement age
        isa = isa_now
        pension = pension_now

        for age in range(params.current_age, retire_age):
            # Contributions
            isa += params.isa_contribution

            if params.pension_contribution_stop_age and age >= params.pension_contribution_stop_age:
                pension += params.pension_contribution_min
            else:
                pension += params.pension_contribution_full

            # Growth
            isa *= (1 + params.growth_rate)
            pension *= (1 + params.growth_rate)

        # Calculate ISA needed for bridge
        isa_needed = calculate_isa_needed_for_bridge(
            retire_age,
            params.pension_access_age,
            min_annual_spending,
            params.swedish_private_access_age,
            swedish_private_annual,
            params.growth_rate,
        )

        # Calculate max bridge spending
        max_bridge = calculate_max_bridge_spending(
            isa,
            retire_age,
            params.pension_access_age,
            params.swedish_private_access_age,
            swedish_private_annual,
            params.growth_rate,
        )

        # Project pension to access age
        pension_at_access = pension
        for age in range(retire_age, params.pension_access_age):
            pension_at_access *= (1 + params.growth_rate)

        surplus = isa - isa_needed
        can_retire = surplus >= 0
        bridge_years = max(0, params.pension_access_age - retire_age)

        results.append({
            "retirement_age": retire_age,
            "isa_at_retirement": isa,
            "isa_needed": isa_needed,
            "surplus": surplus,
            "can_retire": can_retire,
            "bridge_years": bridge_years,
            "pension_at_access": pension_at_access,
            "max_bridge_spend": max_bridge,
        })

    return results
