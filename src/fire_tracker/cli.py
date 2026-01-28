"""Click-based CLI for FIRE tracker."""

from datetime import date
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from .calculations import (
    get_coast_fi_status,
    get_fi_status,
    get_time_to_fi,
    project_portfolio,
)
from .currency import format_currency, format_currency_short
from .history import (
    create_snapshot,
    get_history_stats,
    get_monthly_progress,
    get_yearly_summary,
    save_current_snapshot,
)
from .models import Account, AccountType, Currency, Income, LifeEvent, Portfolio
from .scenarios import (
    compare_scenarios,
    create_expense_change_scenario,
    create_salary_sacrifice_scenario,
)
from .storage import load_portfolio, save_portfolio

console = Console()


@click.group()
@click.version_option()
def cli():
    """FIRE Tracker - Track your progress towards Financial Independence."""
    pass


@cli.command()
def status():
    """Overview of current FIRE progress."""
    portfolio = load_portfolio()

    if not portfolio.accounts:
        console.print(
            "[yellow]No accounts configured. Run 'fire add-account' to get started.[/yellow]"
        )
        return

    currency = portfolio.settings.base_currency
    fi_status = get_fi_status(portfolio)
    coast_status = get_coast_fi_status(portfolio)
    time_to_fi = get_time_to_fi(portfolio)

    # Main status panel
    console.print()
    console.print(Panel.fit("[bold]FIRE Status[/bold]", style="blue"))

    # Portfolio summary
    table = Table(show_header=False, box=None)
    table.add_column("Label", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("Current Portfolio", format_currency(fi_status.current_portfolio, currency))
    table.add_row("Accessible Now", format_currency(fi_status.accessible_portfolio, currency))
    table.add_row("FI Number", format_currency(fi_status.fi_number, currency))
    table.add_row("Monthly Expenses", format_currency(fi_status.monthly_expenses, currency))

    console.print(table)
    console.print()

    # Progress bar
    percentage = min(fi_status.fi_percentage, 100)
    bar_width = 40
    filled = int(percentage / 100 * bar_width)
    bar = "[green]" + "█" * filled + "[/green]" + "░" * (bar_width - filled)
    console.print(f"FI Progress: {bar} {fi_status.fi_percentage:.1f}%")
    console.print()

    # Time to FI
    if time_to_fi.can_reach_fi:
        if time_to_fi.months_to_fi == 0:
            console.print("[green bold]🎉 You've reached Financial Independence![/green bold]")
        else:
            years = time_to_fi.months_to_fi // 12
            months = time_to_fi.months_to_fi % 12
            if years > 0:
                time_str = f"{years} years, {months} months"
            else:
                time_str = f"{months} months"
            console.print(f"Time to FI: [cyan]{time_str}[/cyan] ({time_to_fi.target_date.strftime('%B %Y')})")
    else:
        console.print("[yellow]FI projection not available with current contributions.[/yellow]")

    console.print()

    # Coast FI
    if coast_status.is_coast_fi:
        console.print("[green]✓ Coast FI achieved![/green] You could stop saving and still retire on time.")
    else:
        deficit = abs(coast_status.surplus_or_deficit)
        console.print(
            f"Coast FI: Need {format_currency(deficit, currency)} more to coast to retirement."
        )

    console.print()

    # Safe withdrawal
    console.print(f"Safe Monthly Spending: {format_currency(fi_status.safe_withdrawal_amount, currency)}")


@cli.command()
def accounts():
    """List all accounts and balances."""
    portfolio = load_portfolio()

    if not portfolio.accounts:
        console.print("[yellow]No accounts configured.[/yellow]")
        return

    table = Table(title="Accounts")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Balance", justify="right", style="green")
    table.add_column("Monthly", justify="right")
    table.add_column("Return", justify="right")
    table.add_column("Access Age", justify="right")

    for account in portfolio.accounts:
        access_age = str(account.accessible_age) if account.accessible_age else "-"
        table.add_row(
            account.name,
            account.type.value,
            format_currency(account.balance, account.currency),
            format_currency(account.monthly_contribution, account.currency),
            f"{account.expected_return * 100:.1f}%",
            access_age,
        )

    console.print(table)

    # Totals
    currency = portfolio.settings.base_currency
    total = portfolio.total_balance(currency)
    monthly = portfolio.monthly_contributions(currency)

    console.print()
    console.print(f"[bold]Total:[/bold] {format_currency(total, currency)}")
    console.print(f"[bold]Monthly Contributions:[/bold] {format_currency(monthly, currency)}")


@cli.command("add-account")
@click.option("--name", prompt="Account name", help="Name of the account")
@click.option(
    "--type",
    "account_type",
    prompt="Account type",
    type=click.Choice([t.value for t in AccountType]),
    help="Type of account",
)
@click.option(
    "--currency",
    prompt="Currency",
    type=click.Choice(["GBP", "SEK"]),
    default="GBP",
    help="Account currency",
)
@click.option("--balance", prompt="Current balance", type=float, help="Current balance")
@click.option(
    "--monthly",
    prompt="Monthly contribution",
    type=float,
    default=0.0,
    help="Monthly contribution amount",
)
@click.option(
    "--return",
    "expected_return",
    prompt="Expected annual return (e.g., 0.07 for 7%)",
    type=float,
    default=0.07,
    help="Expected annual return",
)
@click.option(
    "--access-age",
    type=int,
    default=None,
    help="Age when funds become accessible",
)
def add_account(
    name: str,
    account_type: str,
    currency: str,
    balance: float,
    monthly: float,
    expected_return: float,
    access_age: Optional[int],
):
    """Add a new account to track."""
    portfolio = load_portfolio()

    account = Account(
        name=name,
        type=AccountType(account_type),
        currency=Currency(currency),
        balance=balance,
        monthly_contribution=monthly,
        expected_return=expected_return,
        accessible_age=access_age,
    )

    portfolio.accounts.append(account)
    save_portfolio(portfolio)

    console.print(f"[green]Added account: {name}[/green]")


@cli.command()
@click.option("--account", "-a", help="Specific account to update")
@click.option("--balance", "-b", type=float, help="New balance")
@click.option("--snapshot/--no-snapshot", default=True, help="Save monthly snapshot")
def update(account: Optional[str], balance: Optional[float], snapshot: bool):
    """Update account balances."""
    portfolio = load_portfolio()

    if not portfolio.accounts:
        console.print("[yellow]No accounts configured.[/yellow]")
        return

    if account and balance is not None:
        # Update specific account
        for acc in portfolio.accounts:
            if acc.name == account:
                old_balance = acc.balance
                acc.balance = balance
                save_portfolio(portfolio)
                console.print(
                    f"Updated {account}: {format_currency(old_balance, acc.currency)} → {format_currency(balance, acc.currency)}"
                )
                break
        else:
            console.print(f"[red]Account '{account}' not found.[/red]")
            return
    else:
        # Interactive update
        for acc in portfolio.accounts:
            current = format_currency(acc.balance, acc.currency)
            new_balance = click.prompt(
                f"{acc.name} (current: {current})",
                type=float,
                default=acc.balance,
            )
            acc.balance = new_balance

        save_portfolio(portfolio)
        console.print("[green]All balances updated.[/green]")

    if snapshot:
        snap = save_current_snapshot(portfolio)
        console.print(f"[dim]Saved snapshot for {snap.date.strftime('%Y-%m')}[/dim]")


@cli.command()
@click.option("--years", "-y", type=int, default=30, help="Years to project")
@click.option("--return", "expected_return", type=float, default=0.07, help="Expected return")
def projections(years: int, expected_return: float):
    """Show time to FI projections."""
    portfolio = load_portfolio()

    if not portfolio.accounts:
        console.print("[yellow]No accounts configured.[/yellow]")
        return

    currency = portfolio.settings.base_currency
    time_to_fi = get_time_to_fi(portfolio, expected_return)

    console.print(Panel.fit("[bold]FI Projections[/bold]", style="blue"))
    console.print()

    table = Table(show_header=False, box=None)
    table.add_column("Label", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("Current Portfolio", format_currency(time_to_fi.current_portfolio, currency))
    table.add_row("FI Target", format_currency(time_to_fi.fi_number, currency))
    table.add_row("Monthly Contributions", format_currency(time_to_fi.monthly_contribution, currency))
    table.add_row("Assumed Return", f"{expected_return * 100:.1f}%")

    console.print(table)
    console.print()

    if time_to_fi.can_reach_fi:
        years_val = time_to_fi.months_to_fi // 12
        months_val = time_to_fi.months_to_fi % 12
        console.print(f"[green]Projected FI Date:[/green] {time_to_fi.target_date.strftime('%B %Y')}")
        console.print(f"Time remaining: {years_val} years, {months_val} months")
    else:
        console.print("[yellow]Cannot reach FI with current contributions and return assumptions.[/yellow]")

    # Show projection milestones
    if time_to_fi.can_reach_fi:
        projections_data = project_portfolio(portfolio, years, expected_return)

        console.print()
        console.print("[bold]Milestones:[/bold]")

        milestones = [25, 50, 75, 100]
        shown = set()

        for proj in projections_data:
            for milestone in milestones:
                if proj.fi_percentage >= milestone and milestone not in shown:
                    shown.add(milestone)
                    console.print(
                        f"  {milestone}% FI: {proj.date.strftime('%B %Y')} "
                        f"({format_currency_short(proj.portfolio_value, currency)})"
                    )

    # Life events impact
    if portfolio.life_events:
        console.print()
        console.print("[bold]Life Events Factored In:[/bold]")
        for event in sorted(portfolio.life_events, key=lambda e: e.date):
            sign = "+" if event.expense_change > 0 else ""
            console.print(
                f"  {event.date.strftime('%Y-%m')}: {event.name} ({sign}{format_currency(event.expense_change, currency)}/mo)"
            )


@cli.command()
def spending():
    """Calculate safe spending amounts."""
    portfolio = load_portfolio()

    if not portfolio.accounts:
        console.print("[yellow]No accounts configured.[/yellow]")
        return

    fi_status = get_fi_status(portfolio)
    currency = portfolio.settings.base_currency

    console.print(Panel.fit("[bold]Safe Spending[/bold]", style="blue"))
    console.print()

    table = Table(show_header=True)
    table.add_column("Withdrawal Rate")
    table.add_column("Monthly", justify="right")
    table.add_column("Annual", justify="right")

    rates = [0.03, 0.035, 0.04, 0.045, 0.05]

    for rate in rates:
        annual = fi_status.current_portfolio * rate
        monthly = annual / 12
        style = "green" if rate == portfolio.settings.safe_withdrawal_rate else ""
        marker = " ←" if rate == portfolio.settings.safe_withdrawal_rate else ""
        table.add_row(
            f"{rate * 100:.1f}%{marker}",
            format_currency(monthly, currency),
            format_currency(annual, currency),
            style=style,
        )

    console.print(table)

    console.print()
    console.print(f"[dim]Current expenses: {format_currency(portfolio.settings.annual_expenses, currency)}/year[/dim]")

    # Can you retire now?
    swr_annual = fi_status.current_portfolio * portfolio.settings.safe_withdrawal_rate
    if swr_annual >= portfolio.settings.annual_expenses:
        surplus = swr_annual - portfolio.settings.annual_expenses
        console.print()
        console.print(
            f"[green bold]You can cover your expenses![/green bold] "
            f"Surplus: {format_currency(surplus, currency)}/year"
        )
    else:
        shortfall = portfolio.settings.annual_expenses - swr_annual
        console.print()
        console.print(
            f"[yellow]Shortfall:[/yellow] {format_currency(shortfall, currency)}/year "
            f"to cover expenses at {portfolio.settings.safe_withdrawal_rate * 100:.0f}% SWR"
        )


@cli.command()
@click.option("--monthly/--yearly", default=True, help="Show monthly or yearly view")
def history(monthly: bool):
    """View progress over time."""
    stats = get_history_stats()

    if stats["total_snapshots"] == 0:
        console.print("[yellow]No history recorded yet. Run 'fire update' to save a snapshot.[/yellow]")
        return

    console.print(Panel.fit("[bold]Portfolio History[/bold]", style="blue"))
    console.print()

    console.print(f"Tracking since: {stats['first_date'].strftime('%B %Y')}")
    console.print(f"Total snapshots: {stats['total_snapshots']}")
    console.print()

    if monthly:
        progress = get_monthly_progress()
        if not progress:
            console.print("[dim]Need at least 2 snapshots for progress data.[/dim]")
            return

        table = Table(title="Monthly Progress")
        table.add_column("Month")
        table.add_column("Total", justify="right")
        table.add_column("Change", justify="right")
        table.add_column("FI %", justify="right")

        for p in progress[-12:]:  # Last 12 months
            change_style = "green" if p["change"] >= 0 else "red"
            sign = "+" if p["change"] >= 0 else ""
            table.add_row(
                p["date"].strftime("%Y-%m"),
                f"£{p['total']:,.0f}",
                f"[{change_style}]{sign}£{p['change']:,.0f}[/{change_style}]",
                f"{p['fi_percentage']:.1f}%",
            )

        console.print(table)
    else:
        summaries = get_yearly_summary()
        if not summaries:
            console.print("[dim]No yearly data available.[/dim]")
            return

        table = Table(title="Yearly Summary")
        table.add_column("Year")
        table.add_column("Start", justify="right")
        table.add_column("End", justify="right")
        table.add_column("Change", justify="right")
        table.add_column("FI %", justify="right")

        for s in summaries:
            change_style = "green" if s["change"] >= 0 else "red"
            sign = "+" if s["change"] >= 0 else ""
            table.add_row(
                str(s["year"]),
                f"£{s['start_value']:,.0f}",
                f"£{s['end_value']:,.0f}",
                f"[{change_style}]{sign}£{s['change']:,.0f} ({s['change_percent']:+.1f}%)[/{change_style}]",
                f"{s['fi_percentage']:.1f}%",
            )

        console.print(table)


@cli.command()
@click.option("--salary-sacrifice", type=float, help="Model salary sacrifice percentage (e.g., 10 for 10%)")
@click.option("--employer-match", type=float, default=0.0, help="Employer match percentage")
@click.option("--expense-change", type=float, help="Model monthly expense change")
@click.option("--from", "from_date", type=str, help="When expense change takes effect (YYYY-MM)")
@click.option("--event-name", default="Expense Change", help="Name for the expense change event")
def scenario(
    salary_sacrifice: Optional[float],
    employer_match: float,
    expense_change: Optional[float],
    from_date: Optional[str],
    event_name: str,
):
    """Run what-if scenarios."""
    portfolio = load_portfolio()

    if not portfolio.accounts:
        console.print("[yellow]No accounts configured.[/yellow]")
        return

    currency = portfolio.settings.base_currency

    if salary_sacrifice is not None:
        if portfolio.income is None:
            console.print("[red]No income configured. Add income to config.yaml first.[/red]")
            return

        try:
            scenario_portfolio = create_salary_sacrifice_scenario(
                portfolio, salary_sacrifice, employer_match
            )
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            return

        comparison = compare_scenarios(
            portfolio, scenario_portfolio, f"Salary Sacrifice {salary_sacrifice}%"
        )

    elif expense_change is not None:
        event_date = None
        if from_date:
            year, month = from_date.split("-")
            event_date = date(int(year), int(month), 1)

        scenario_portfolio = create_expense_change_scenario(
            portfolio, expense_change, event_date, event_name
        )

        comparison = compare_scenarios(portfolio, scenario_portfolio, event_name)

    else:
        console.print("Specify a scenario type:")
        console.print("  --salary-sacrifice 10    Model 10% salary sacrifice")
        console.print("  --expense-change -1500   Model £1500/month expense reduction")
        console.print()
        console.print("Examples:")
        console.print("  fire scenario --salary-sacrifice 10 --employer-match 3")
        console.print("  fire scenario --expense-change -1500 --from 2035-06 --event-name 'Mortgage paid'")
        return

    # Display comparison
    console.print(Panel.fit("[bold]Scenario Comparison[/bold]", style="blue"))
    console.print()

    table = Table()
    table.add_column("Metric")
    table.add_column("Current", justify="right")
    table.add_column(comparison.scenario.name, justify="right")
    table.add_column("Difference", justify="right")

    # FI Percentage
    diff = comparison.fi_percentage_change
    diff_str = f"{diff:+.1f}%"
    if diff > 0:
        diff_str = f"[green]{diff_str}[/green]"
    elif diff < 0:
        diff_str = f"[red]{diff_str}[/red]"
    table.add_row(
        "FI %",
        f"{comparison.baseline.fi_status.fi_percentage:.1f}%",
        f"{comparison.scenario.fi_status.fi_percentage:.1f}%",
        diff_str,
    )

    # Time to FI
    if comparison.baseline.time_to_fi.can_reach_fi and comparison.scenario.time_to_fi.can_reach_fi:
        base_time = f"{comparison.baseline.time_to_fi.years_to_fi:.1f} years"
        scen_time = f"{comparison.scenario.time_to_fi.years_to_fi:.1f} years"
        months_diff = comparison.months_saved
        if months_diff > 0:
            diff_str = f"[green]{months_diff} months faster[/green]"
        elif months_diff < 0:
            diff_str = f"[red]{abs(months_diff)} months slower[/red]"
        else:
            diff_str = "No change"
        table.add_row("Time to FI", base_time, scen_time, diff_str)

    # Monthly contributions
    base_contrib = comparison.baseline.fi_status.monthly_expenses
    scen_contrib = comparison.scenario.fi_status.monthly_expenses
    if base_contrib != scen_contrib:
        diff_val = scen_contrib - base_contrib
        table.add_row(
            "Monthly Expenses",
            format_currency(base_contrib, currency),
            format_currency(scen_contrib, currency),
            f"{'+' if diff_val > 0 else ''}{format_currency(diff_val, currency)}",
        )

    console.print(table)

    if comparison.months_saved > 0:
        console.print()
        console.print(
            f"[green bold]This scenario gets you to FI {comparison.months_saved} months earlier![/green bold]"
        )


@cli.command("init")
def init_config():
    """Initialize configuration with example data."""
    portfolio = load_portfolio()

    if portfolio.accounts:
        if not click.confirm("Configuration already exists. Overwrite with example data?"):
            return

    # Create example portfolio
    portfolio = Portfolio(
        accounts=[
            Account(
                name="Vanguard S&S ISA",
                type=AccountType.SS_ISA,
                currency=Currency.GBP,
                balance=50000,
                monthly_contribution=500,
                expected_return=0.07,
            ),
            Account(
                name="Workplace Pension",
                type=AccountType.UK_PENSION,
                currency=Currency.GBP,
                balance=80000,
                monthly_contribution=800,
                expected_return=0.06,
                accessible_age=57,
            ),
            Account(
                name="Swedish Tjänstepension",
                type=AccountType.SWEDISH_PENSION,
                currency=Currency.SEK,
                balance=200000,
                monthly_contribution=0,
                expected_return=0.05,
                accessible_age=65,
            ),
        ],
        life_events=[
            LifeEvent(
                name="Mortgage paid off",
                date=date(2035, 6, 1),
                expense_change=-1500,
            ),
        ],
        income=Income(
            gross_salary=75000,
            salary_sacrifice_percent=5,
        ),
    )

    save_portfolio(portfolio)
    console.print("[green]Created example configuration in data/config.yaml[/green]")
    console.print("Run 'fire status' to see your FIRE progress.")


@cli.command("config")
@click.option("--expenses", type=float, help="Set annual expenses")
@click.option("--swr", type=float, help="Set safe withdrawal rate (e.g., 0.04)")
@click.option("--age", type=int, help="Set current age")
@click.option("--target-age", type=int, help="Set target retirement age")
def config_cmd(
    expenses: Optional[float],
    swr: Optional[float],
    age: Optional[int],
    target_age: Optional[int],
):
    """View or update configuration settings."""
    portfolio = load_portfolio()

    # If no options provided, show current config
    if all(v is None for v in [expenses, swr, age, target_age]):
        console.print(Panel.fit("[bold]Configuration[/bold]", style="blue"))
        console.print()

        table = Table(show_header=False, box=None)
        table.add_column("Setting", style="dim")
        table.add_column("Value", style="bold")

        s = portfolio.settings
        table.add_row("Base Currency", s.base_currency.value)
        table.add_row("Annual Expenses", format_currency(s.annual_expenses, s.base_currency))
        table.add_row("Safe Withdrawal Rate", f"{s.safe_withdrawal_rate * 100:.1f}%")
        table.add_row("Current Age", str(s.current_age))
        table.add_row("Target Retirement Age", str(s.target_retirement_age))

        console.print(table)

        if portfolio.income:
            console.print()
            console.print("[bold]Income:[/bold]")
            console.print(f"  Gross Salary: {format_currency(portfolio.income.gross_salary, s.base_currency)}")
            console.print(f"  Salary Sacrifice: {portfolio.income.salary_sacrifice_percent}%")

        if portfolio.exchange_rates:
            console.print()
            console.print("[bold]Exchange Rates:[/bold]")
            for key, rate in portfolio.exchange_rates.items():
                console.print(f"  {key}: {rate}")

        return

    # Update provided settings
    if expenses is not None:
        portfolio.settings.annual_expenses = expenses
    if swr is not None:
        portfolio.settings.safe_withdrawal_rate = swr
    if age is not None:
        portfolio.settings.current_age = age
    if target_age is not None:
        portfolio.settings.target_retirement_age = target_age

    save_portfolio(portfolio)
    console.print("[green]Settings updated.[/green]")


if __name__ == "__main__":
    cli()
