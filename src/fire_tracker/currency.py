"""Multi-currency handling utilities."""

from .models import Currency, Portfolio


def convert_to_base(
    amount: float,
    from_currency: Currency,
    portfolio: Portfolio,
) -> float:
    """Convert an amount to the portfolio's base currency."""
    base = portfolio.settings.base_currency
    if from_currency == base:
        return amount

    return portfolio._convert_currency(amount, from_currency, base)


def format_currency(amount: float, currency: Currency) -> str:
    """Format an amount with currency symbol."""
    if currency == Currency.GBP:
        return f"£{amount:,.2f}"
    elif currency == Currency.SEK:
        return f"{amount:,.2f} kr"
    return f"{amount:,.2f} {currency.value}"


def format_currency_short(amount: float, currency: Currency) -> str:
    """Format an amount with currency symbol, using K/M for large numbers."""
    if amount >= 1_000_000:
        value = amount / 1_000_000
        suffix = "M"
    elif amount >= 1_000:
        value = amount / 1_000
        suffix = "K"
    else:
        return format_currency(amount, currency)

    if currency == Currency.GBP:
        return f"£{value:,.1f}{suffix}"
    elif currency == Currency.SEK:
        return f"{value:,.1f}{suffix} kr"
    return f"{value:,.1f}{suffix} {currency.value}"
