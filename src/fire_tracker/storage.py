"""YAML read/write for portfolio data."""

import os
from datetime import date
from pathlib import Path

import yaml

from .models import HistorySnapshot, Portfolio


def get_data_dir() -> Path:
    """Get the data directory path."""
    # Check for FIRE_DATA_DIR environment variable first
    if env_dir := os.environ.get("FIRE_DATA_DIR"):
        return Path(env_dir)

    # Default to ./data relative to current directory
    return Path.cwd() / "data"


def get_config_path() -> Path:
    """Get the config file path."""
    return get_data_dir() / "config.yaml"


def get_history_dir() -> Path:
    """Get the history directory path."""
    return get_data_dir() / "history"


def load_portfolio() -> Portfolio:
    """Load portfolio from config file."""
    config_path = get_config_path()

    if not config_path.exists():
        # Return empty portfolio if no config exists
        return Portfolio()

    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}

    return Portfolio.from_dict(data)


def save_portfolio(portfolio: Portfolio) -> None:
    """Save portfolio to config file."""
    config_path = get_config_path()

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(portfolio.to_dict(), f, default_flow_style=False, sort_keys=False)


def load_history_snapshot(snapshot_date: date) -> HistorySnapshot | None:
    """Load a specific history snapshot."""
    filename = snapshot_date.strftime("%Y-%m") + ".yaml"
    filepath = get_history_dir() / filename

    if not filepath.exists():
        return None

    with open(filepath, "r") as f:
        data = yaml.safe_load(f) or {}

    return HistorySnapshot.from_dict(data)


def save_history_snapshot(snapshot: HistorySnapshot) -> None:
    """Save a history snapshot."""
    history_dir = get_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)

    filename = snapshot.date.strftime("%Y-%m") + ".yaml"
    filepath = history_dir / filename

    with open(filepath, "w") as f:
        yaml.dump(snapshot.to_dict(), f, default_flow_style=False, sort_keys=False)


def list_history_snapshots() -> list[date]:
    """List all available history snapshot dates."""
    history_dir = get_history_dir()

    if not history_dir.exists():
        return []

    dates = []
    for filepath in history_dir.glob("*.yaml"):
        try:
            # Parse YYYY-MM from filename
            year, month = filepath.stem.split("-")
            dates.append(date(int(year), int(month), 1))
        except (ValueError, IndexError):
            continue

    return sorted(dates)


def load_all_history() -> list[HistorySnapshot]:
    """Load all history snapshots."""
    snapshots = []
    for snapshot_date in list_history_snapshots():
        snapshot = load_history_snapshot(snapshot_date)
        if snapshot:
            snapshots.append(snapshot)
    return snapshots
