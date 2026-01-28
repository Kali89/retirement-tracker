"""Monthly snapshot tracking and history management."""

from datetime import date
from typing import Optional

from .calculations import calculate_fi_number, calculate_fi_percentage
from .models import Currency, HistorySnapshot, Portfolio
from .storage import (
    load_all_history,
    load_history_snapshot,
    list_history_snapshots,
    save_history_snapshot,
)


def create_snapshot(portfolio: Portfolio) -> HistorySnapshot:
    """Create a snapshot of current portfolio state."""
    currency = portfolio.settings.base_currency
    total = portfolio.total_balance(currency)

    fi_number = calculate_fi_number(
        portfolio.settings.annual_expenses,
        portfolio.settings.safe_withdrawal_rate,
    )
    fi_percentage = calculate_fi_percentage(total, fi_number)

    account_balances = {account.name: account.balance for account in portfolio.accounts}

    return HistorySnapshot(
        date=date.today(),
        account_balances=account_balances,
        total_gbp=total if currency == Currency.GBP else 0,
        fi_percentage=fi_percentage,
    )


def save_current_snapshot(portfolio: Portfolio) -> HistorySnapshot:
    """Create and save a snapshot of current portfolio state."""
    snapshot = create_snapshot(portfolio)
    save_history_snapshot(snapshot)
    return snapshot


def get_monthly_progress() -> list[dict]:
    """Get month-over-month progress data."""
    snapshots = load_all_history()

    if len(snapshots) < 2:
        return []

    progress = []
    for i in range(1, len(snapshots)):
        prev = snapshots[i - 1]
        curr = snapshots[i]

        change = curr.total_gbp - prev.total_gbp
        fi_change = curr.fi_percentage - prev.fi_percentage

        progress.append({
            "date": curr.date,
            "total": curr.total_gbp,
            "change": change,
            "fi_percentage": curr.fi_percentage,
            "fi_change": fi_change,
        })

    return progress


def get_yearly_summary() -> list[dict]:
    """Get year-over-year summary data."""
    snapshots = load_all_history()

    if not snapshots:
        return []

    # Group by year
    yearly: dict[int, list[HistorySnapshot]] = {}
    for snapshot in snapshots:
        year = snapshot.date.year
        if year not in yearly:
            yearly[year] = []
        yearly[year].append(snapshot)

    summaries = []
    sorted_years = sorted(yearly.keys())

    for i, year in enumerate(sorted_years):
        year_snapshots = yearly[year]

        # Get last snapshot of the year
        last_snapshot = max(year_snapshots, key=lambda s: s.date)

        # Calculate year start value
        if i > 0:
            prev_year = sorted_years[i - 1]
            prev_last = max(yearly[prev_year], key=lambda s: s.date)
            start_value = prev_last.total_gbp
        else:
            first_snapshot = min(year_snapshots, key=lambda s: s.date)
            start_value = first_snapshot.total_gbp

        end_value = last_snapshot.total_gbp
        change = end_value - start_value
        change_percent = (change / start_value * 100) if start_value > 0 else 0

        summaries.append({
            "year": year,
            "start_value": start_value,
            "end_value": end_value,
            "change": change,
            "change_percent": change_percent,
            "fi_percentage": last_snapshot.fi_percentage,
        })

    return summaries


def get_history_stats() -> dict:
    """Get overall history statistics."""
    snapshots = load_all_history()

    if not snapshots:
        return {
            "total_snapshots": 0,
            "first_date": None,
            "last_date": None,
            "months_tracked": 0,
        }

    first = min(snapshots, key=lambda s: s.date)
    last = max(snapshots, key=lambda s: s.date)

    # Calculate months between first and last
    months = (
        (last.date.year - first.date.year) * 12 + last.date.month - first.date.month + 1
    )

    return {
        "total_snapshots": len(snapshots),
        "first_date": first.date,
        "last_date": last.date,
        "months_tracked": months,
        "first_value": first.total_gbp,
        "last_value": last.total_gbp,
        "total_growth": last.total_gbp - first.total_gbp,
        "first_fi_percentage": first.fi_percentage,
        "last_fi_percentage": last.fi_percentage,
    }
