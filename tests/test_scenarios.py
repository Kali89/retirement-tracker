"""Tests for scenario modeling."""

import pytest
from datetime import date

from fire_tracker.scenarios import (
    create_salary_sacrifice_scenario,
    create_expense_change_scenario,
    create_contribution_change_scenario,
    compare_scenarios,
)
from fire_tracker.models import (
    Account,
    AccountType,
    Currency,
    Income,
    Portfolio,
    Settings,
)


@pytest.fixture
def sample_portfolio():
    """Create a sample portfolio for testing."""
    return Portfolio(
        settings=Settings(
            annual_expenses=40000,
            safe_withdrawal_rate=0.04,
            current_age=35,
            target_retirement_age=55,
        ),
        accounts=[
            Account(
                name="ISA",
                type=AccountType.SS_ISA,
                currency=Currency.GBP,
                balance=100_000,
                monthly_contribution=500,
            ),
            Account(
                name="Workplace Pension",
                type=AccountType.UK_PENSION,
                currency=Currency.GBP,
                balance=80_000,
                monthly_contribution=400,
                accessible_age=57,
            ),
        ],
        income=Income(
            gross_salary=75000,
            salary_sacrifice_percent=5,
        ),
    )


class TestSalarySacrificeScenario:
    """Tests for salary sacrifice scenarios."""

    def test_increase_salary_sacrifice(self, sample_portfolio):
        """Test increasing salary sacrifice from 5% to 10%."""
        scenario = create_salary_sacrifice_scenario(sample_portfolio, 10.0)

        # Original pension contribution was 400/month
        # Adding extra 5% of 75k = 3750/year = 312.50/month
        pension = next(a for a in scenario.accounts if a.type == AccountType.UK_PENSION)

        assert pension.monthly_contribution == pytest.approx(712.50, rel=0.01)
        assert scenario.income.salary_sacrifice_percent == 10.0

    def test_with_employer_match(self, sample_portfolio):
        """Test salary sacrifice with employer matching."""
        scenario = create_salary_sacrifice_scenario(sample_portfolio, 10.0, employer_match_percent=3.0)

        pension = next(a for a in scenario.accounts if a.type == AccountType.UK_PENSION)

        # Extra 5% employee + 3% employer = 8% of 75k = 6000/year = 500/month extra
        # Original 400 + 312.50 (extra 5%) + 187.50 (3% match) = 900
        assert pension.monthly_contribution == pytest.approx(900, rel=0.01)

    def test_no_income_raises(self):
        """Test that missing income raises error."""
        portfolio = Portfolio(
            accounts=[
                Account(
                    name="ISA",
                    type=AccountType.SS_ISA,
                    currency=Currency.GBP,
                    balance=100_000,
                ),
            ],
        )

        with pytest.raises(ValueError, match="No income configured"):
            create_salary_sacrifice_scenario(portfolio, 10.0)


class TestExpenseChangeScenario:
    """Tests for expense change scenarios."""

    def test_immediate_expense_reduction(self, sample_portfolio):
        """Test immediate expense reduction."""
        scenario = create_expense_change_scenario(sample_portfolio, -1500)

        # Original 40000 - (1500 * 12) = 22000
        assert scenario.settings.annual_expenses == 22000

    def test_future_expense_reduction(self, sample_portfolio):
        """Test future expense reduction creates life event."""
        future_date = date(2035, 6, 1)
        scenario = create_expense_change_scenario(
            sample_portfolio, -1500, future_date, "Mortgage paid"
        )

        # Annual expenses unchanged
        assert scenario.settings.annual_expenses == 40000

        # Life event added
        assert len(scenario.life_events) == 1
        event = scenario.life_events[0]
        assert event.name == "Mortgage paid"
        assert event.date == future_date
        assert event.expense_change == -1500


class TestContributionChangeScenario:
    """Tests for contribution change scenarios."""

    def test_increase_isa_contribution(self, sample_portfolio):
        """Test increasing ISA contribution."""
        scenario = create_contribution_change_scenario(sample_portfolio, "ISA", 1000)

        isa = next(a for a in scenario.accounts if a.name == "ISA")
        assert isa.monthly_contribution == 1000

    def test_account_not_found_raises(self, sample_portfolio):
        """Test that missing account raises error."""
        with pytest.raises(ValueError, match="not found"):
            create_contribution_change_scenario(sample_portfolio, "Nonexistent", 1000)


class TestScenarioComparison:
    """Tests for scenario comparison."""

    def test_salary_sacrifice_comparison(self, sample_portfolio):
        """Test comparing baseline to salary sacrifice scenario."""
        scenario = create_salary_sacrifice_scenario(sample_portfolio, 10.0)
        comparison = compare_scenarios(sample_portfolio, scenario, "10% Sacrifice")

        assert comparison.baseline.name == "Current"
        assert comparison.scenario.name == "10% Sacrifice"

        # Higher contributions should lead to faster FI
        if comparison.baseline.time_to_fi.can_reach_fi and comparison.scenario.time_to_fi.can_reach_fi:
            assert comparison.months_saved > 0

    def test_expense_reduction_comparison(self, sample_portfolio):
        """Test comparing baseline to expense reduction scenario."""
        scenario = create_expense_change_scenario(sample_portfolio, -1000)
        comparison = compare_scenarios(sample_portfolio, scenario, "Lower Expenses")

        # Lower expenses = lower FI number = higher FI percentage
        assert comparison.fi_percentage_change > 0
