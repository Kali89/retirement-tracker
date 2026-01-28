"""Tests for FIRE calculations."""

import pytest
from datetime import date

from fire_tracker.calculations import (
    calculate_fi_number,
    calculate_safe_withdrawal,
    calculate_fi_percentage,
    calculate_coast_fi,
    calculate_months_to_fi,
    get_fi_status,
    get_coast_fi_status,
    get_time_to_fi,
)
from fire_tracker.models import (
    Account,
    AccountType,
    Currency,
    Portfolio,
    Settings,
)


class TestFINumber:
    """Tests for FI number calculation."""

    def test_standard_4_percent_rule(self):
        """Test classic 4% rule calculation."""
        fi_number = calculate_fi_number(40000, 0.04)
        assert fi_number == 1_000_000

    def test_3_percent_rule(self):
        """Test more conservative 3% rule."""
        fi_number = calculate_fi_number(40000, 0.03)
        assert fi_number == pytest.approx(1_333_333.33, rel=0.01)

    def test_zero_swr_raises(self):
        """Test that zero SWR raises error."""
        with pytest.raises(ValueError):
            calculate_fi_number(40000, 0)

    def test_negative_swr_raises(self):
        """Test that negative SWR raises error."""
        with pytest.raises(ValueError):
            calculate_fi_number(40000, -0.04)


class TestSafeWithdrawal:
    """Tests for safe withdrawal calculation."""

    def test_4_percent_withdrawal(self):
        """Test 4% withdrawal from portfolio."""
        withdrawal = calculate_safe_withdrawal(1_000_000, 0.04)
        assert withdrawal == 40_000

    def test_3_percent_withdrawal(self):
        """Test 3% withdrawal from portfolio."""
        withdrawal = calculate_safe_withdrawal(1_000_000, 0.03)
        assert withdrawal == 30_000


class TestFIPercentage:
    """Tests for FI percentage calculation."""

    def test_halfway_to_fi(self):
        """Test 50% FI progress."""
        percentage = calculate_fi_percentage(500_000, 1_000_000)
        assert percentage == 50.0

    def test_at_fi(self):
        """Test 100% FI progress."""
        percentage = calculate_fi_percentage(1_000_000, 1_000_000)
        assert percentage == 100.0

    def test_over_fi(self):
        """Test over 100% FI progress."""
        percentage = calculate_fi_percentage(1_200_000, 1_000_000)
        assert percentage == 120.0

    def test_zero_fi_number(self):
        """Test with zero FI number returns 0."""
        percentage = calculate_fi_percentage(100_000, 0)
        assert percentage == 0.0


class TestCoastFI:
    """Tests for Coast FI calculation."""

    def test_coast_fi_20_years(self):
        """Test Coast FI with 20 years to retirement."""
        # With 7% return, need about $258,419 now to reach $1M in 20 years
        coast = calculate_coast_fi(1_000_000, 20, 0.07)
        assert coast == pytest.approx(258_419, rel=0.01)

    def test_coast_fi_10_years(self):
        """Test Coast FI with 10 years to retirement."""
        coast = calculate_coast_fi(1_000_000, 10, 0.07)
        assert coast == pytest.approx(508_349, rel=0.01)

    def test_coast_fi_zero_years(self):
        """Test Coast FI at retirement age equals FI number."""
        coast = calculate_coast_fi(1_000_000, 0, 0.07)
        assert coast == 1_000_000


class TestMonthsToFI:
    """Tests for time to FI calculation."""

    def test_already_at_fi(self):
        """Test when already at FI."""
        months = calculate_months_to_fi(1_000_000, 1_000_000, 1000)
        assert months == 0

    def test_no_contributions_positive_return(self):
        """Test growth only with no contributions."""
        # $500k growing at 7% to reach $1M
        months = calculate_months_to_fi(500_000, 1_000_000, 0, 0.07 / 12)
        assert months is not None
        assert months > 0
        # Should take about 10 years (120 months)
        assert 110 < months < 130

    def test_with_contributions(self):
        """Test with regular contributions."""
        months = calculate_months_to_fi(100_000, 1_000_000, 2000, 0.07 / 12)
        assert months is not None
        assert months > 0

    def test_unreachable_fi(self):
        """Test when FI is unreachable."""
        # No contributions, no growth
        months = calculate_months_to_fi(100_000, 1_000_000, 0, 0)
        assert months is None


class TestGetFIStatus:
    """Tests for comprehensive FI status."""

    def test_basic_status(self):
        """Test basic FI status calculation."""
        portfolio = Portfolio(
            settings=Settings(
                annual_expenses=40000,
                safe_withdrawal_rate=0.04,
                current_age=35,
            ),
            accounts=[
                Account(
                    name="ISA",
                    type=AccountType.SS_ISA,
                    currency=Currency.GBP,
                    balance=500_000,
                    monthly_contribution=1000,
                ),
            ],
        )

        status = get_fi_status(portfolio)

        assert status.fi_number == 1_000_000
        assert status.current_portfolio == 500_000
        assert status.fi_percentage == 50.0
        assert status.monthly_expenses == pytest.approx(3333.33, rel=0.01)


class TestGetCoastFIStatus:
    """Tests for Coast FI status."""

    def test_coast_fi_achieved(self):
        """Test when Coast FI is achieved."""
        portfolio = Portfolio(
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
                    balance=300_000,
                ),
            ],
        )

        status = get_coast_fi_status(portfolio)

        # Coast FI for 20 years at 7% is ~$258k
        assert status.is_coast_fi is True
        assert status.surplus_or_deficit > 0

    def test_coast_fi_not_achieved(self):
        """Test when Coast FI is not achieved."""
        portfolio = Portfolio(
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
                ),
            ],
        )

        status = get_coast_fi_status(portfolio)

        assert status.is_coast_fi is False
        assert status.surplus_or_deficit < 0


class TestMultiCurrency:
    """Tests for multi-currency portfolio calculations."""

    def test_sek_to_gbp_conversion(self):
        """Test SEK to GBP conversion in totals."""
        portfolio = Portfolio(
            settings=Settings(base_currency=Currency.GBP),
            exchange_rates={"SEK_GBP": 0.073},
            accounts=[
                Account(
                    name="UK ISA",
                    type=AccountType.SS_ISA,
                    currency=Currency.GBP,
                    balance=100_000,
                ),
                Account(
                    name="Swedish Pension",
                    type=AccountType.SWEDISH_PENSION,
                    currency=Currency.SEK,
                    balance=1_000_000,  # 1M SEK = 73,000 GBP
                ),
            ],
        )

        total = portfolio.total_balance(Currency.GBP)

        # 100,000 GBP + 1,000,000 SEK * 0.073 = 173,000 GBP
        assert total == pytest.approx(173_000, rel=0.01)
