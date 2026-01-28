"""Data models for FIRE tracker."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class AccountType(Enum):
    """Supported account types."""

    # UK accounts
    SS_ISA = "ss_isa"  # Stocks & Shares ISA
    CASH_ISA = "cash_isa"
    CASH = "cash"
    UK_PENSION = "uk_pension"  # Workplace pension, SIPP

    # Swedish accounts
    SWEDISH_PENSION = "swedish_pension"  # Tjänstepension, PPM

    # Generic
    BROKERAGE = "brokerage"
    OTHER = "other"


class Currency(Enum):
    """Supported currencies."""

    GBP = "GBP"
    SEK = "SEK"


@dataclass
class Account:
    """A single investment/savings account."""

    name: str
    type: AccountType
    currency: Currency
    balance: float
    monthly_contribution: float = 0.0
    expected_return: float = 0.07  # 7% default
    accessible_age: Optional[int] = None  # Age when funds become accessible

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        data = {
            "name": self.name,
            "type": self.type.value,
            "currency": self.currency.value,
            "balance": self.balance,
            "monthly_contribution": self.monthly_contribution,
            "expected_return": self.expected_return,
        }
        if self.accessible_age is not None:
            data["accessible_age"] = self.accessible_age
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            type=AccountType(data["type"]),
            currency=Currency(data["currency"]),
            balance=data["balance"],
            monthly_contribution=data.get("monthly_contribution", 0.0),
            expected_return=data.get("expected_return", 0.07),
            accessible_age=data.get("accessible_age"),
        )


@dataclass
class LifeEvent:
    """A future event that changes expenses."""

    name: str
    date: date
    expense_change: float  # Monthly change (negative = reduction)

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        return {
            "name": self.name,
            "date": self.date.strftime("%Y-%m"),
            "expense_change": self.expense_change,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LifeEvent":
        """Create from dictionary."""
        date_str = data["date"]
        if isinstance(date_str, str):
            year, month = date_str.split("-")
            event_date = date(int(year), int(month), 1)
        else:
            event_date = date_str
        return cls(
            name=data["name"],
            date=event_date,
            expense_change=data["expense_change"],
        )


@dataclass
class Income:
    """Income and salary sacrifice settings."""

    gross_salary: float
    salary_sacrifice_percent: float = 0.0  # Pension contribution %

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        return {
            "gross_salary": self.gross_salary,
            "salary_sacrifice_percent": self.salary_sacrifice_percent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Income":
        """Create from dictionary."""
        return cls(
            gross_salary=data["gross_salary"],
            salary_sacrifice_percent=data.get("salary_sacrifice_percent", 0.0),
        )


@dataclass
class Settings:
    """User configuration settings."""

    base_currency: Currency = Currency.GBP
    annual_expenses: float = 40000.0
    safe_withdrawal_rate: float = 0.04
    target_retirement_age: int = 55
    current_age: int = 35

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        return {
            "base_currency": self.base_currency.value,
            "annual_expenses": self.annual_expenses,
            "safe_withdrawal_rate": self.safe_withdrawal_rate,
            "target_retirement_age": self.target_retirement_age,
            "current_age": self.current_age,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """Create from dictionary."""
        return cls(
            base_currency=Currency(data.get("base_currency", "GBP")),
            annual_expenses=data.get("annual_expenses", 40000.0),
            safe_withdrawal_rate=data.get("safe_withdrawal_rate", 0.04),
            target_retirement_age=data.get("target_retirement_age", 55),
            current_age=data.get("current_age", 35),
        )


@dataclass
class Portfolio:
    """Complete portfolio with all accounts and settings."""

    settings: Settings = field(default_factory=Settings)
    exchange_rates: dict[str, float] = field(default_factory=lambda: {"SEK_GBP": 0.073})
    accounts: list[Account] = field(default_factory=list)
    life_events: list[LifeEvent] = field(default_factory=list)
    income: Optional[Income] = None

    def total_balance(self, currency: Currency) -> float:
        """Calculate total balance in specified currency."""
        total = 0.0
        for account in self.accounts:
            balance = account.balance
            if account.currency != currency:
                balance = self._convert_currency(balance, account.currency, currency)
            total += balance
        return total

    def accessible_balance(self, currency: Currency, age: int) -> float:
        """Calculate balance accessible at a given age."""
        total = 0.0
        for account in self.accounts:
            if account.accessible_age is None or age >= account.accessible_age:
                balance = account.balance
                if account.currency != currency:
                    balance = self._convert_currency(balance, account.currency, currency)
                total += balance
        return total

    def _convert_currency(self, amount: float, from_curr: Currency, to_curr: Currency) -> float:
        """Convert between currencies."""
        if from_curr == to_curr:
            return amount

        rate_key = f"{from_curr.value}_{to_curr.value}"
        reverse_key = f"{to_curr.value}_{from_curr.value}"

        if rate_key in self.exchange_rates:
            return amount * self.exchange_rates[rate_key]
        elif reverse_key in self.exchange_rates:
            return amount / self.exchange_rates[reverse_key]
        else:
            raise ValueError(f"No exchange rate found for {from_curr.value} to {to_curr.value}")

    def monthly_contributions(self, currency: Currency) -> float:
        """Calculate total monthly contributions in specified currency."""
        total = 0.0
        for account in self.accounts:
            contribution = account.monthly_contribution
            if account.currency != currency:
                contribution = self._convert_currency(contribution, account.currency, currency)
            total += contribution
        return total

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        data = {
            "settings": self.settings.to_dict(),
            "exchange_rates": self.exchange_rates,
            "accounts": [a.to_dict() for a in self.accounts],
        }
        if self.life_events:
            data["life_events"] = [e.to_dict() for e in self.life_events]
        if self.income:
            data["income"] = self.income.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        """Create from dictionary."""
        return cls(
            settings=Settings.from_dict(data.get("settings", {})),
            exchange_rates=data.get("exchange_rates", {"SEK_GBP": 0.073}),
            accounts=[Account.from_dict(a) for a in data.get("accounts", [])],
            life_events=[LifeEvent.from_dict(e) for e in data.get("life_events", [])],
            income=Income.from_dict(data["income"]) if data.get("income") else None,
        )


@dataclass
class HistorySnapshot:
    """A monthly snapshot of portfolio state."""

    date: date
    account_balances: dict[str, float]  # account name -> balance
    total_gbp: float
    fi_percentage: float

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "accounts": [
                {"name": name, "balance": balance}
                for name, balance in self.account_balances.items()
            ],
            "totals": {
                "gbp": self.total_gbp,
                "fi_percentage": self.fi_percentage,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistorySnapshot":
        """Create from dictionary."""
        date_str = data["date"]
        if isinstance(date_str, str):
            snapshot_date = date.fromisoformat(date_str)
        else:
            snapshot_date = date_str

        account_balances = {
            a["name"]: a["balance"] for a in data.get("accounts", [])
        }

        totals = data.get("totals", {})
        return cls(
            date=snapshot_date,
            account_balances=account_balances,
            total_gbp=totals.get("gbp", 0.0),
            fi_percentage=totals.get("fi_percentage", 0.0),
        )
