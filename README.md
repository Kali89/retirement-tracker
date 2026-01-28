# FIRE Tracker

A Python CLI tool for tracking progress towards FIRE (Financial Independence, Retire Early) with support for UK and Swedish accounts.

## Features

- **Multi-currency support**: Track accounts in GBP and SEK
- **UK & Swedish accounts**: S&S ISAs, Cash ISAs, UK pensions, Swedish pensions
- **FIRE calculations**: FI number, Coast FIRE, time to FI projections
- **Scenario modeling**: Model salary sacrifice, expense changes, life events
- **Monthly snapshots**: Track progress over time

## Installation

```bash
# Clone and install
cd retirement-tracker
pip install -e .

# Or with uv
uv pip install -e .
```

## Quick Start

```bash
# Initialize with example configuration
fire init

# View your FIRE status
fire status

# View all accounts
fire accounts

# Update account balances
fire update

# View projections
fire projections

# View safe spending amounts
fire spending
```

## Commands

| Command | Description |
|---------|-------------|
| `fire status` | Overview of current FI progress |
| `fire accounts` | List all accounts and balances |
| `fire add-account` | Add a new account |
| `fire update` | Update account balances (saves monthly snapshot) |
| `fire projections` | Show time to FI projections |
| `fire spending` | Calculate safe spending amounts |
| `fire history` | View monthly/yearly progress |
| `fire scenario` | Run what-if scenarios |
| `fire config` | View or update settings |
| `fire init` | Initialize with example data |

## Scenario Modeling

### Salary Sacrifice

Model the impact of different pension contribution levels:

```bash
# What if I increased salary sacrifice to 10%?
fire scenario --salary-sacrifice 10

# With 3% employer matching
fire scenario --salary-sacrifice 10 --employer-match 3
```

### Expense Changes

Model future expense reductions (e.g., mortgage payoff):

```bash
# Immediate expense reduction
fire scenario --expense-change -1500

# Future expense reduction
fire scenario --expense-change -1500 --from 2035-06 --event-name "Mortgage paid"
```

## Configuration

Configuration is stored in `data/config.yaml`. See `data/example_config.yaml` for a full example.

### Settings

```yaml
settings:
  base_currency: GBP
  annual_expenses: 40000
  safe_withdrawal_rate: 0.04
  target_retirement_age: 55
  current_age: 35
```

### Accounts

```yaml
accounts:
  - name: "Vanguard S&S ISA"
    type: ss_isa        # ss_isa, cash_isa, cash, uk_pension, swedish_pension
    currency: GBP
    balance: 50000
    monthly_contribution: 500
    expected_return: 0.07
    accessible_age: null  # Optional: age when funds become accessible
```

### Life Events

```yaml
life_events:
  - name: "Mortgage paid off"
    date: "2035-06"
    expense_change: -1500  # Monthly reduction
```

### Income (for salary sacrifice modeling)

```yaml
income:
  gross_salary: 75000
  salary_sacrifice_percent: 5
```

## FIRE Calculations

### FI Number

The portfolio size needed to cover your expenses:

```
FI Number = Annual Expenses / Safe Withdrawal Rate
```

With 4% SWR: £40,000 / 0.04 = £1,000,000

### Coast FIRE

The amount needed now to reach FI without further contributions:

```
Coast FI = FI Number / (1 + return)^years
```

### Time to FI

Projected months until reaching FI, based on current portfolio, contributions, and expected returns.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=fire_tracker
```

## License

MIT
