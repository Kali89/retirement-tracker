"""What-if scenario modeling."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .calculations import (
    get_fi_status,
    get_time_to_fi,
    project_portfolio,
    FIStatus,
    TimeToFIResult,
    ProjectionPoint,
)
from .models import Account, Currency, LifeEvent, Portfolio


@dataclass
class ScenarioResult:
    """Result of a scenario comparison."""

    name: str
    fi_status: FIStatus
    time_to_fi: TimeToFIResult
    projections: list[ProjectionPoint]


@dataclass
class ScenarioComparison:
    """Comparison between baseline and scenario."""

    baseline: ScenarioResult
    scenario: ScenarioResult
    months_saved: int  # Positive = reaches FI faster
    fi_percentage_change: float


def create_salary_sacrifice_scenario(
    portfolio: Portfolio,
    new_sacrifice_percent: float,
    employer_match_percent: float = 0.0,
) -> Portfolio:
    """Create a scenario with different salary sacrifice percentage.

    Args:
        portfolio: Current portfolio
        new_sacrifice_percent: New salary sacrifice percentage (e.g., 10 for 10%)
        employer_match_percent: Employer matching percentage (e.g., 3 for 3%)

    Returns:
        Modified portfolio with updated pension contributions
    """
    scenario = deepcopy(portfolio)

    if scenario.income is None:
        raise ValueError("No income configured. Add income to use salary sacrifice scenarios.")

    gross_salary = scenario.income.gross_salary
    current_sacrifice = scenario.income.salary_sacrifice_percent

    # Calculate contribution difference
    old_monthly = (gross_salary * current_sacrifice / 100) / 12
    new_monthly = (gross_salary * new_sacrifice_percent / 100) / 12

    # Add employer match if applicable
    employer_contribution = (gross_salary * employer_match_percent / 100) / 12
    contribution_increase = (new_monthly - old_monthly) + employer_contribution

    # Find UK pension account and update contribution
    for account in scenario.accounts:
        if account.type.value == "uk_pension":
            account.monthly_contribution += contribution_increase
            break
    else:
        # No pension account found, create one
        scenario.accounts.append(
            Account(
                name="Workplace Pension (Scenario)",
                type=Account.AccountType.UK_PENSION if hasattr(Account, 'AccountType') else "uk_pension",
                currency=Currency.GBP,
                balance=0,
                monthly_contribution=new_monthly + employer_contribution,
                expected_return=0.06,
                accessible_age=57,
            )
        )

    scenario.income.salary_sacrifice_percent = new_sacrifice_percent
    return scenario


def create_expense_change_scenario(
    portfolio: Portfolio,
    expense_change: float,
    from_date: Optional[date] = None,
    event_name: str = "Expense Change",
) -> Portfolio:
    """Create a scenario with changed expenses.

    Args:
        portfolio: Current portfolio
        expense_change: Monthly expense change (negative = reduction)
        from_date: When the change takes effect (None = immediately)
        event_name: Name for the life event

    Returns:
        Modified portfolio with expense change
    """
    scenario = deepcopy(portfolio)

    if from_date is None or from_date <= date.today():
        # Apply immediately to annual expenses
        scenario.settings.annual_expenses += expense_change * 12
    else:
        # Add as future life event
        scenario.life_events.append(
            LifeEvent(
                name=event_name,
                date=from_date,
                expense_change=expense_change,
            )
        )

    return scenario


def create_contribution_change_scenario(
    portfolio: Portfolio,
    account_name: str,
    new_contribution: float,
) -> Portfolio:
    """Create a scenario with changed contribution to a specific account.

    Args:
        portfolio: Current portfolio
        account_name: Name of account to modify
        new_contribution: New monthly contribution amount

    Returns:
        Modified portfolio with updated contribution
    """
    scenario = deepcopy(portfolio)

    for account in scenario.accounts:
        if account.name == account_name:
            account.monthly_contribution = new_contribution
            return scenario

    raise ValueError(f"Account '{account_name}' not found")


def compare_scenarios(
    baseline: Portfolio,
    scenario: Portfolio,
    scenario_name: str = "Scenario",
    projection_years: int = 30,
    expected_return: float = 0.07,
) -> ScenarioComparison:
    """Compare baseline portfolio with a scenario."""
    baseline_fi = get_fi_status(baseline)
    baseline_time = get_time_to_fi(baseline, expected_return)
    baseline_proj = project_portfolio(baseline, projection_years, expected_return)

    scenario_fi = get_fi_status(scenario)
    scenario_time = get_time_to_fi(scenario, expected_return)
    scenario_proj = project_portfolio(scenario, projection_years, expected_return)

    # Calculate months saved
    if baseline_time.can_reach_fi and scenario_time.can_reach_fi:
        months_saved = baseline_time.months_to_fi - scenario_time.months_to_fi
    elif scenario_time.can_reach_fi and not baseline_time.can_reach_fi:
        months_saved = 999  # Scenario makes FI possible
    elif baseline_time.can_reach_fi and not scenario_time.can_reach_fi:
        months_saved = -999  # Scenario makes FI impossible
    else:
        months_saved = 0

    return ScenarioComparison(
        baseline=ScenarioResult(
            name="Current",
            fi_status=baseline_fi,
            time_to_fi=baseline_time,
            projections=baseline_proj,
        ),
        scenario=ScenarioResult(
            name=scenario_name,
            fi_status=scenario_fi,
            time_to_fi=scenario_time,
            projections=scenario_proj,
        ),
        months_saved=months_saved,
        fi_percentage_change=scenario_fi.fi_percentage - baseline_fi.fi_percentage,
    )


def run_salary_sacrifice_scenario(
    portfolio: Portfolio,
    new_sacrifice_percent: float,
    employer_match_percent: float = 0.0,
    projection_years: int = 30,
) -> ScenarioComparison:
    """Run a salary sacrifice scenario and compare to baseline."""
    scenario = create_salary_sacrifice_scenario(
        portfolio, new_sacrifice_percent, employer_match_percent
    )
    return compare_scenarios(
        baseline=portfolio,
        scenario=scenario,
        scenario_name=f"Salary Sacrifice {new_sacrifice_percent}%",
        projection_years=projection_years,
    )


def run_expense_change_scenario(
    portfolio: Portfolio,
    expense_change: float,
    from_date: Optional[date] = None,
    event_name: str = "Expense Change",
    projection_years: int = 30,
) -> ScenarioComparison:
    """Run an expense change scenario and compare to baseline."""
    scenario = create_expense_change_scenario(
        portfolio, expense_change, from_date, event_name
    )
    return compare_scenarios(
        baseline=portfolio,
        scenario=scenario,
        scenario_name=event_name,
        projection_years=projection_years,
    )
