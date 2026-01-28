"""FIRE calculations - FI number, projections, safe withdrawal rates."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import Currency, LifeEvent, Portfolio


@dataclass
class FIStatus:
    """Current FI status summary."""

    fi_number: float
    current_portfolio: float
    accessible_portfolio: float
    fi_percentage: float
    accessible_fi_percentage: float
    monthly_expenses: float
    safe_withdrawal_amount: float
    currency: Currency


@dataclass
class CoastFIResult:
    """Coast FIRE calculation result."""

    coast_number: float
    current_portfolio: float
    is_coast_fi: bool
    surplus_or_deficit: float
    years_to_traditional_retirement: int
    assumed_return: float
    currency: Currency


@dataclass
class TimeToFIResult:
    """Time to FI projection result."""

    months_to_fi: int
    years_to_fi: float
    target_date: date
    fi_number: float
    current_portfolio: float
    monthly_contribution: float
    assumed_return: float
    currency: Currency
    can_reach_fi: bool  # False if contributions are negative


@dataclass
class ProjectionPoint:
    """A single point in a projection timeline."""

    date: date
    portfolio_value: float
    monthly_expenses: float
    fi_percentage: float
    is_fi: bool


def calculate_fi_number(annual_expenses: float, swr: float) -> float:
    """Calculate the FI number (target portfolio size).

    FI Number = Annual Expenses / Safe Withdrawal Rate
    With 4% rule: £40,000 / 0.04 = £1,000,000
    """
    if swr <= 0:
        raise ValueError("Safe withdrawal rate must be positive")
    return annual_expenses / swr


def calculate_safe_withdrawal(portfolio_value: float, swr: float) -> float:
    """Calculate safe annual withdrawal from portfolio.

    Safe Withdrawal = Portfolio Value * Safe Withdrawal Rate
    """
    return portfolio_value * swr


def calculate_fi_percentage(current_portfolio: float, fi_number: float) -> float:
    """Calculate percentage progress towards FI.

    FI% = (Current Portfolio / FI Number) * 100
    """
    if fi_number <= 0:
        return 0.0
    return (current_portfolio / fi_number) * 100


def calculate_coast_fi(
    fi_number: float,
    years_to_retirement: int,
    expected_return: float = 0.07,
) -> float:
    """Calculate Coast FI number - amount needed now to coast to FI.

    Coast FI = FI Number / (1 + return)^years
    This is the present value needed to reach FI with no further contributions.
    """
    if years_to_retirement <= 0:
        return fi_number
    growth_factor = (1 + expected_return) ** years_to_retirement
    return fi_number / growth_factor


def calculate_months_to_fi(
    current_portfolio: float,
    fi_number: float,
    monthly_contribution: float,
    monthly_return: float = 0.07 / 12,
) -> int | None:
    """Calculate months until FI is reached.

    Uses compound interest formula with regular contributions.
    Returns None if FI is unreachable (no contributions and below FI).
    """
    if current_portfolio >= fi_number:
        return 0

    if monthly_contribution <= 0 and current_portfolio < fi_number:
        # Can still reach FI through growth alone if return is positive
        if monthly_return <= 0:
            return None

        # Calculate months needed for growth to reach FI
        # FV = PV * (1 + r)^n
        # n = log(FV/PV) / log(1 + r)
        import math

        months = math.log(fi_number / current_portfolio) / math.log(1 + monthly_return)
        return int(math.ceil(months))

    # With contributions, iterate month by month
    portfolio = current_portfolio
    months = 0
    max_months = 12 * 100  # Cap at 100 years

    while portfolio < fi_number and months < max_months:
        portfolio = portfolio * (1 + monthly_return) + monthly_contribution
        months += 1

    if months >= max_months:
        return None

    return months


def get_fi_status(portfolio: Portfolio) -> FIStatus:
    """Get comprehensive FI status."""
    currency = portfolio.settings.base_currency
    annual_expenses = portfolio.settings.annual_expenses
    swr = portfolio.settings.safe_withdrawal_rate
    current_age = portfolio.settings.current_age

    fi_number = calculate_fi_number(annual_expenses, swr)
    current_portfolio = portfolio.total_balance(currency)
    accessible_portfolio = portfolio.accessible_balance(currency, current_age)

    fi_percentage = calculate_fi_percentage(current_portfolio, fi_number)
    accessible_fi_percentage = calculate_fi_percentage(accessible_portfolio, fi_number)

    monthly_expenses = annual_expenses / 12
    safe_withdrawal = calculate_safe_withdrawal(current_portfolio, swr)

    return FIStatus(
        fi_number=fi_number,
        current_portfolio=current_portfolio,
        accessible_portfolio=accessible_portfolio,
        fi_percentage=fi_percentage,
        accessible_fi_percentage=accessible_fi_percentage,
        monthly_expenses=monthly_expenses,
        safe_withdrawal_amount=safe_withdrawal / 12,  # Monthly
        currency=currency,
    )


def get_coast_fi_status(
    portfolio: Portfolio,
    expected_return: float = 0.07,
) -> CoastFIResult:
    """Calculate Coast FI status."""
    currency = portfolio.settings.base_currency
    current_age = portfolio.settings.current_age
    target_age = portfolio.settings.target_retirement_age
    years_to_retirement = max(0, target_age - current_age)

    fi_number = calculate_fi_number(
        portfolio.settings.annual_expenses,
        portfolio.settings.safe_withdrawal_rate,
    )
    coast_number = calculate_coast_fi(fi_number, years_to_retirement, expected_return)
    current_portfolio = portfolio.total_balance(currency)

    return CoastFIResult(
        coast_number=coast_number,
        current_portfolio=current_portfolio,
        is_coast_fi=current_portfolio >= coast_number,
        surplus_or_deficit=current_portfolio - coast_number,
        years_to_traditional_retirement=years_to_retirement,
        assumed_return=expected_return,
        currency=currency,
    )


def get_time_to_fi(
    portfolio: Portfolio,
    expected_return: float = 0.07,
) -> TimeToFIResult:
    """Calculate time to FI."""
    currency = portfolio.settings.base_currency
    fi_number = calculate_fi_number(
        portfolio.settings.annual_expenses,
        portfolio.settings.safe_withdrawal_rate,
    )
    current_portfolio = portfolio.total_balance(currency)
    monthly_contribution = portfolio.monthly_contributions(currency)
    monthly_return = expected_return / 12

    months = calculate_months_to_fi(
        current_portfolio,
        fi_number,
        monthly_contribution,
        monthly_return,
    )

    if months is None:
        # FI is unreachable
        return TimeToFIResult(
            months_to_fi=0,
            years_to_fi=0,
            target_date=date.today(),
            fi_number=fi_number,
            current_portfolio=current_portfolio,
            monthly_contribution=monthly_contribution,
            assumed_return=expected_return,
            currency=currency,
            can_reach_fi=False,
        )

    target_date = date.today()
    years = months // 12
    remaining_months = months % 12
    target_date = date(
        target_date.year + years + (target_date.month + remaining_months - 1) // 12,
        (target_date.month + remaining_months - 1) % 12 + 1,
        1,
    )

    return TimeToFIResult(
        months_to_fi=months,
        years_to_fi=months / 12,
        target_date=target_date,
        fi_number=fi_number,
        current_portfolio=current_portfolio,
        monthly_contribution=monthly_contribution,
        assumed_return=expected_return,
        currency=currency,
        can_reach_fi=True,
    )


def project_portfolio(
    portfolio: Portfolio,
    years: int = 30,
    expected_return: float = 0.07,
    life_events: Optional[list[LifeEvent]] = None,
) -> list[ProjectionPoint]:
    """Project portfolio growth over time, accounting for life events."""
    if life_events is None:
        life_events = portfolio.life_events

    currency = portfolio.settings.base_currency
    current_value = portfolio.total_balance(currency)
    monthly_contribution = portfolio.monthly_contributions(currency)
    monthly_return = expected_return / 12

    # Start with current annual expenses
    annual_expenses = portfolio.settings.annual_expenses
    swr = portfolio.settings.safe_withdrawal_rate

    # Sort life events by date
    sorted_events = sorted(life_events, key=lambda e: e.date)

    projections = []
    current_date = date.today()

    for month in range(years * 12):
        # Calculate date for this month
        year_offset = month // 12
        month_offset = month % 12
        proj_date = date(
            current_date.year + year_offset + (current_date.month + month_offset - 1) // 12,
            (current_date.month + month_offset - 1) % 12 + 1,
            1,
        )

        # Apply any life events that occur this month
        for event in sorted_events:
            if event.date.year == proj_date.year and event.date.month == proj_date.month:
                # Apply monthly expense change to annual expenses
                annual_expenses += event.expense_change * 12

        # Recalculate FI number with current expenses
        fi_number = calculate_fi_number(annual_expenses, swr)
        fi_percentage = calculate_fi_percentage(current_value, fi_number)

        projections.append(
            ProjectionPoint(
                date=proj_date,
                portfolio_value=current_value,
                monthly_expenses=annual_expenses / 12,
                fi_percentage=fi_percentage,
                is_fi=fi_percentage >= 100,
            )
        )

        # Grow portfolio for next month
        current_value = current_value * (1 + monthly_return) + monthly_contribution

    return projections
