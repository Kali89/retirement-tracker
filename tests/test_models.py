"""Tests for data models."""

import pytest
from datetime import date

from fire_tracker.models import (
    Account,
    AccountType,
    Currency,
    Income,
    LifeEvent,
    Portfolio,
    Settings,
    HistorySnapshot,
)


class TestAccount:
    """Tests for Account model."""

    def test_account_creation(self):
        """Test basic account creation."""
        account = Account(
            name="Test ISA",
            type=AccountType.SS_ISA,
            currency=Currency.GBP,
            balance=50000,
            monthly_contribution=500,
            expected_return=0.07,
        )

        assert account.name == "Test ISA"
        assert account.type == AccountType.SS_ISA
        assert account.balance == 50000
        assert account.accessible_age is None

    def test_account_to_dict(self):
        """Test account serialization."""
        account = Account(
            name="Pension",
            type=AccountType.UK_PENSION,
            currency=Currency.GBP,
            balance=80000,
            accessible_age=57,
        )

        data = account.to_dict()

        assert data["name"] == "Pension"
        assert data["type"] == "uk_pension"
        assert data["currency"] == "GBP"
        assert data["accessible_age"] == 57

    def test_account_from_dict(self):
        """Test account deserialization."""
        data = {
            "name": "Swedish Pension",
            "type": "swedish_pension",
            "currency": "SEK",
            "balance": 200000,
            "monthly_contribution": 0,
            "expected_return": 0.05,
            "accessible_age": 65,
        }

        account = Account.from_dict(data)

        assert account.name == "Swedish Pension"
        assert account.type == AccountType.SWEDISH_PENSION
        assert account.currency == Currency.SEK
        assert account.accessible_age == 65


class TestLifeEvent:
    """Tests for LifeEvent model."""

    def test_life_event_creation(self):
        """Test life event creation."""
        event = LifeEvent(
            name="Mortgage paid off",
            date=date(2035, 6, 1),
            expense_change=-1500,
        )

        assert event.name == "Mortgage paid off"
        assert event.expense_change == -1500

    def test_life_event_to_dict(self):
        """Test life event serialization."""
        event = LifeEvent(
            name="Kids leave",
            date=date(2040, 1, 1),
            expense_change=-500,
        )

        data = event.to_dict()

        assert data["name"] == "Kids leave"
        assert data["date"] == "2040-01"
        assert data["expense_change"] == -500

    def test_life_event_from_dict(self):
        """Test life event deserialization."""
        data = {
            "name": "Retire early",
            "date": "2045-06",
            "expense_change": 500,
        }

        event = LifeEvent.from_dict(data)

        assert event.name == "Retire early"
        assert event.date == date(2045, 6, 1)
        assert event.expense_change == 500


class TestPortfolio:
    """Tests for Portfolio model."""

    @pytest.fixture
    def sample_portfolio(self):
        """Create a sample portfolio."""
        return Portfolio(
            settings=Settings(
                base_currency=Currency.GBP,
                annual_expenses=40000,
            ),
            exchange_rates={"SEK_GBP": 0.073},
            accounts=[
                Account(
                    name="UK ISA",
                    type=AccountType.SS_ISA,
                    currency=Currency.GBP,
                    balance=100_000,
                    monthly_contribution=500,
                ),
                Account(
                    name="Swedish Pension",
                    type=AccountType.SWEDISH_PENSION,
                    currency=Currency.SEK,
                    balance=1_000_000,
                    accessible_age=65,
                ),
            ],
        )

    def test_total_balance_single_currency(self):
        """Test total balance with single currency."""
        portfolio = Portfolio(
            accounts=[
                Account(
                    name="ISA1",
                    type=AccountType.SS_ISA,
                    currency=Currency.GBP,
                    balance=50_000,
                ),
                Account(
                    name="ISA2",
                    type=AccountType.SS_ISA,
                    currency=Currency.GBP,
                    balance=30_000,
                ),
            ],
        )

        assert portfolio.total_balance(Currency.GBP) == 80_000

    def test_total_balance_multi_currency(self, sample_portfolio):
        """Test total balance with currency conversion."""
        total = sample_portfolio.total_balance(Currency.GBP)

        # 100,000 GBP + 1,000,000 SEK * 0.073 = 173,000 GBP
        assert total == pytest.approx(173_000, rel=0.01)

    def test_accessible_balance_at_age(self, sample_portfolio):
        """Test accessible balance at different ages."""
        # At age 35, only ISA is accessible
        accessible_35 = sample_portfolio.accessible_balance(Currency.GBP, 35)
        assert accessible_35 == 100_000

        # At age 65, both are accessible
        accessible_65 = sample_portfolio.accessible_balance(Currency.GBP, 65)
        assert accessible_65 == pytest.approx(173_000, rel=0.01)

    def test_monthly_contributions(self, sample_portfolio):
        """Test monthly contributions calculation."""
        contributions = sample_portfolio.monthly_contributions(Currency.GBP)

        # Only UK ISA has contributions in this fixture
        assert contributions == 500

    def test_portfolio_roundtrip(self, sample_portfolio):
        """Test serialization and deserialization."""
        sample_portfolio.life_events = [
            LifeEvent(
                name="Test Event",
                date=date(2035, 1, 1),
                expense_change=-500,
            ),
        ]
        sample_portfolio.income = Income(
            gross_salary=75000,
            salary_sacrifice_percent=5,
        )

        data = sample_portfolio.to_dict()
        restored = Portfolio.from_dict(data)

        assert len(restored.accounts) == 2
        assert len(restored.life_events) == 1
        assert restored.income is not None
        assert restored.income.gross_salary == 75000


class TestHistorySnapshot:
    """Tests for HistorySnapshot model."""

    def test_snapshot_creation(self):
        """Test snapshot creation."""
        snapshot = HistorySnapshot(
            date=date(2024, 1, 31),
            account_balances={"ISA": 50000, "Pension": 80000},
            total_gbp=130000,
            fi_percentage=32.5,
        )

        assert snapshot.total_gbp == 130000
        assert snapshot.fi_percentage == 32.5
        assert len(snapshot.account_balances) == 2

    def test_snapshot_roundtrip(self):
        """Test snapshot serialization and deserialization."""
        snapshot = HistorySnapshot(
            date=date(2024, 3, 15),
            account_balances={"Account1": 100000},
            total_gbp=100000,
            fi_percentage=25.0,
        )

        data = snapshot.to_dict()
        restored = HistorySnapshot.from_dict(data)

        assert restored.date == snapshot.date
        assert restored.total_gbp == snapshot.total_gbp
        assert restored.fi_percentage == snapshot.fi_percentage
