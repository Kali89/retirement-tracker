"""User configuration management."""

from .models import Portfolio, Settings
from .storage import load_portfolio, save_portfolio


def get_settings() -> Settings:
    """Get current user settings."""
    portfolio = load_portfolio()
    return portfolio.settings


def update_settings(
    annual_expenses: float | None = None,
    safe_withdrawal_rate: float | None = None,
    target_retirement_age: int | None = None,
    current_age: int | None = None,
) -> Settings:
    """Update user settings."""
    portfolio = load_portfolio()

    if annual_expenses is not None:
        portfolio.settings.annual_expenses = annual_expenses
    if safe_withdrawal_rate is not None:
        portfolio.settings.safe_withdrawal_rate = safe_withdrawal_rate
    if target_retirement_age is not None:
        portfolio.settings.target_retirement_age = target_retirement_age
    if current_age is not None:
        portfolio.settings.current_age = current_age

    save_portfolio(portfolio)
    return portfolio.settings


def update_exchange_rate(from_currency: str, to_currency: str, rate: float) -> None:
    """Update an exchange rate."""
    portfolio = load_portfolio()
    rate_key = f"{from_currency}_{to_currency}"
    portfolio.exchange_rates[rate_key] = rate
    save_portfolio(portfolio)
