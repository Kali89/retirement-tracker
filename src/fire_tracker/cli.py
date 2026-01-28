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


@cli.command("retire")
@click.option("--retirement-age", "-r", type=int, default=45, help="Age to retire")
@click.option("--expenses", "-e", type=float, default=70000, help="Annual expenses in retirement")
@click.option("--years", "-y", type=int, default=60, help="Years to project")
@click.option("--swedish-payout", type=int, default=20, help="Swedish private pension payout years")
@click.option("--pension-stop", type=int, default=None, help="Age to stop max pension contributions (continues with employer match)")
@click.option("--pension-min", type=float, default=None, help="Minimum annual pension contribution after stop age (default: 12% of salary for employer match)")
@click.option("--isa-stop", type=int, default=None, help="Age to stop ISA contributions")
def retire(retirement_age: int, expenses: float, years: int, swedish_payout: int,
           pension_stop: Optional[int], pension_min: Optional[float], isa_stop: Optional[int]):
    """Project retirement withdrawals with multiple pots at different access ages.

    Shows year-by-year projection of:
    - Which pots you can access at each age
    - How much to withdraw from each pot
    - Whether you'll have shortfalls

    Access ages:
    - ISA: Anytime (from retirement)
    - Swedish Private Pension: 55
    - UK Pension: 57
    - Swedish State Pension: 66
    - UK State Pension: 67

    When --pension-stop is used, contributions drop to the employer match level
    (default 12% of salary = 4% employee + 8% employer) rather than stopping
    entirely. Override with --pension-min.

    Examples:
    - fire retire --pension-stop 38   # Reduce to employer match at 38
    - fire retire --pension-stop 38 --pension-min 30000  # Custom minimum
    - fire retire -r 50 -e 60000      # Retire at 50 with £60k expenses
    """
    from .retirement_model import (
        RetirementScenario,
        RetirementPot,
        PotType,
        run_retirement_projection,
    )

    portfolio = load_portfolio()

    if not portfolio.accounts:
        console.print("[yellow]No accounts configured.[/yellow]")
        return

    currency = portfolio.settings.base_currency
    current_age = portfolio.settings.current_age

    # Build pots from portfolio accounts
    pots = []

    # Aggregate ISAs
    isa_balance = sum(
        a.balance for a in portfolio.accounts
        if a.type in (AccountType.SS_ISA, AccountType.CASH_ISA) and a.currency == Currency.GBP
    )
    isa_contribution = sum(
        a.monthly_contribution * 12 for a in portfolio.accounts
        if a.type in (AccountType.SS_ISA, AccountType.CASH_ISA) and a.currency == Currency.GBP
    )
    if isa_balance > 0 or isa_contribution > 0:
        pots.append(RetirementPot(
            name="S&S ISAs",
            pot_type=PotType.ISA,
            balance=isa_balance,
            currency=Currency.GBP,
            annual_contribution=isa_contribution,
            growth_rate=0.04,
            accessible_age=0,
        ))

    # Aggregate UK Pensions
    pension_balance = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.UK_PENSION and a.currency == Currency.GBP
    )
    pension_contribution = sum(
        a.monthly_contribution * 12 for a in portfolio.accounts
        if a.type == AccountType.UK_PENSION and a.currency == Currency.GBP
    )
    if pension_balance > 0 or pension_contribution > 0:
        pots.append(RetirementPot(
            name="UK Pensions",
            pot_type=PotType.UK_PENSION,
            balance=pension_balance,
            currency=Currency.GBP,
            annual_contribution=pension_contribution,
            growth_rate=0.04,
            accessible_age=57,
        ))

    # Swedish Private Pension
    swedish_private = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.SWEDISH_PENSION and "state" not in a.name.lower()
    )
    if swedish_private > 0:
        pots.append(RetirementPot(
            name="Swedish Private Pension",
            pot_type=PotType.SWEDISH_PRIVATE_PENSION,
            balance=swedish_private,
            currency=Currency.SEK,
            annual_contribution=0,
            growth_rate=0.04,
            accessible_age=55,
            payout_years=swedish_payout,
        ))

    # Swedish State Pension
    swedish_state = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.SWEDISH_PENSION and "state" in a.name.lower()
    )
    if swedish_state > 0:
        pots.append(RetirementPot(
            name="Swedish State Pension",
            pot_type=PotType.SWEDISH_STATE_PENSION,
            balance=swedish_state,
            currency=Currency.SEK,
            annual_contribution=0,
            growth_rate=0.04,
            accessible_age=66,
            payout_years=20,
        ))

    # Cash
    cash_balance = sum(
        a.balance for a in portfolio.accounts
        if a.type == AccountType.CASH and a.currency == Currency.GBP
    )
    if cash_balance > 0:
        pots.append(RetirementPot(
            name="Cash",
            pot_type=PotType.CASH,
            balance=cash_balance,
            currency=Currency.GBP,
            annual_contribution=0,
            growth_rate=0.02,
            accessible_age=0,
        ))

    if not pots:
        console.print("[yellow]No retirement pots found in accounts.[/yellow]")
        return

    scenario = RetirementScenario(
        current_age=current_age,
        retirement_age=retirement_age,
        annual_expenses=expenses,
        base_currency=currency,
        exchange_rate_sek_gbp=portfolio.exchange_rates.get("SEK_GBP", 0.073),
        pots=pots,
    )

    # Use provided stop ages or default to retirement age
    effective_pension_stop = pension_stop if pension_stop is not None else retirement_age
    effective_isa_stop = isa_stop if isa_stop is not None else retirement_age

    # Calculate minimum pension contribution (employer match)
    # Default: 12% of salary (4% employee + 8% employer match)
    if pension_min is not None:
        effective_pension_min = pension_min
    elif portfolio.income:
        effective_pension_min = portfolio.income.gross_salary * 0.12
    else:
        effective_pension_min = 0.0

    projections = run_retirement_projection(
        scenario, years,
        pension_contribution_stop_age=effective_pension_stop,
        isa_contribution_stop_age=effective_isa_stop,
        pension_contribution_minimum=effective_pension_min,
    )

    # Display results
    console.print()
    title = f"[bold]Retirement Projection: Retire at {retirement_age}[/bold]"
    if pension_stop or isa_stop:
        title += " (modified contributions)"
    console.print(Panel.fit(title, style="blue"))
    console.print()

    console.print("[bold]Current Pots:[/bold]")
    for pot in pots:
        if pot.currency == Currency.SEK:
            balance_str = f"{pot.balance:,.0f} SEK (£{pot.balance * scenario.exchange_rate_sek_gbp:,.0f})"
        else:
            balance_str = f"£{pot.balance:,.0f}"
        access_str = f"from age {pot.accessible_age}" if pot.accessible_age > 0 else "anytime"
        contrib_str = f", +£{pot.annual_contribution:,.0f}/yr" if pot.annual_contribution > 0 else ""
        console.print(f"  {pot.name}: {balance_str} ({access_str}{contrib_str})")

    console.print()
    console.print(f"[bold]Assumptions:[/bold]")
    console.print(f"  Retirement age: {retirement_age}")
    console.print(f"  Annual expenses: £{expenses:,.0f}")
    console.print(f"  Growth rate: 4% real")

    # Show pension contribution phases
    pension_full = sum(p.annual_contribution for p in pots if p.pot_type == PotType.UK_PENSION)
    if pension_stop and pension_stop < retirement_age:
        console.print(f"  Pension: £{pension_full:,.0f}/yr until {effective_pension_stop}, then £{effective_pension_min:,.0f}/yr (employer match) until {retirement_age}")
    else:
        console.print(f"  Pension contributions: £{pension_full:,.0f}/yr until age {effective_pension_stop}")

    console.print(f"  ISA contributions: until age {effective_isa_stop}")
    console.print(f"  UK State Pension: £11,500/yr from age 67")
    console.print(f"  Swedish private pension payout: {swedish_payout} years from age 55")

    console.print()
    console.print("[bold]Year-by-Year Projection:[/bold]")
    console.print()

    # Create table
    table = Table()
    table.add_column("Age", justify="right", style="cyan")
    table.add_column("Year", justify="right")
    table.add_column("ISA", justify="right")
    table.add_column("UK Pension", justify="right")
    table.add_column("Swe Priv", justify="right")
    table.add_column("Total", justify="right", style="green")
    table.add_column("Income", justify="right")
    table.add_column("From", justify="left")

    # Show key years
    key_ages = set([current_age, retirement_age, 55, 57, 66, 67])
    for proj in projections:
        # Show: current, every year until retirement, then key ages, then every 5 years
        show = (
            proj.age == current_age or
            proj.age <= retirement_age or
            proj.age in key_ages or
            (proj.age > retirement_age and (proj.age - retirement_age) % 5 == 0) or
            proj.shortfall > 0
        )
        if not show:
            continue

        swe_priv_gbp = proj.swedish_private_balance * scenario.exchange_rate_sek_gbp

        # Build income source string
        sources = []
        if proj.isa_withdrawal > 0:
            sources.append(f"ISA £{proj.isa_withdrawal:,.0f}")
        if proj.uk_pension_withdrawal > 0:
            sources.append(f"Pen £{proj.uk_pension_withdrawal:,.0f}")
        if proj.swedish_private_withdrawal > 0:
            sources.append(f"SwP £{proj.swedish_private_withdrawal:,.0f}")
        if proj.swedish_state_withdrawal > 0:
            sources.append(f"SwS £{proj.swedish_state_withdrawal:,.0f}")
        if proj.uk_state_pension > 0:
            sources.append(f"SP £{proj.uk_state_pension:,.0f}")
        source_str = ", ".join(sources) if sources else "-"

        income_str = f"£{proj.total_income:,.0f}" if proj.total_income > 0 else "-"
        if proj.shortfall > 0:
            income_str = f"[red]£{proj.total_income:,.0f} (SHORT £{proj.shortfall:,.0f})[/red]"

        row_style = ""
        if proj.age == retirement_age:
            row_style = "bold"
        elif proj.shortfall > 0:
            row_style = "red"

        table.add_row(
            str(proj.age),
            str(proj.year),
            f"£{proj.isa_balance:,.0f}",
            f"£{proj.uk_pension_balance:,.0f}",
            f"£{swe_priv_gbp:,.0f}",
            f"£{proj.total_portfolio_gbp:,.0f}",
            income_str,
            source_str,
            style=row_style,
        )

    console.print(table)

    # Summary
    console.print()
    retirement_proj = next((p for p in projections if p.age == retirement_age), None)
    if retirement_proj:
        console.print(f"[bold]At retirement (age {retirement_age}):[/bold]")
        console.print(f"  Total portfolio: £{retirement_proj.total_portfolio_gbp:,.0f}")
        console.print(f"  Available immediately (ISA): £{retirement_proj.isa_balance:,.0f}")

        # Years until other pots accessible
        years_to_55 = max(0, 55 - retirement_age)
        years_to_57 = max(0, 57 - retirement_age)
        if years_to_55 > 0:
            console.print(f"  Swedish private pension accessible in {years_to_55} years (age 55)")
        if years_to_57 > 0:
            console.print(f"  UK pension accessible in {years_to_57} years (age 57)")

    # Check for shortfalls
    shortfall_years = [p for p in projections if p.shortfall > 0]
    if shortfall_years:
        console.print()
        console.print(f"[red bold]Warning: Shortfalls detected in {len(shortfall_years)} years![/red bold]")
        first_shortfall = shortfall_years[0]
        console.print(f"  First shortfall at age {first_shortfall.age}: £{first_shortfall.shortfall:,.0f}")
    else:
        # Find when money runs out
        last_funded = projections[-1]
        for p in reversed(projections):
            if p.total_portfolio_gbp > 1000:
                last_funded = p
                break
        console.print()
        console.print(f"[green]Portfolio sustains expenses until age {last_funded.age} ({last_funded.year})[/green]")


@cli.command("optimize")
@click.option("--retirement-age", "-r", type=int, default=45, help="Age to retire")
@click.option("--death-age", "-d", type=int, default=100, help="Target age for portfolio depletion")
@click.option("--pension-stop", type=int, default=38, help="Age to stop max pension contributions")
@click.option("--pension-access", type=int, default=57, help="Age when UK pension becomes accessible")
@click.option("--top", "-n", type=int, default=10, help="Number of strategies to show")
def optimize(retirement_age: int, death_age: int, pension_stop: int, pension_access: int, top: int):
    """Find optimal two-phase withdrawal strategy.

    Calculates the best bridge (pre-pension) and pension phase spending
    to maximize lifetime spending while depleting to ~£0 at target death age.

    The bridge phase is from retirement until UK pension access (typically 57).
    Every pound saved during the bridge grows and funds more spending later.

    Examples:
        fire optimize                      # Default: retire 45, die 100
        fire optimize -r 50 -d 95          # Retire 50, die 95
        fire optimize --pension-stop 40    # Stop max pension at 40
    """
    from .optimizer import (
        OptimizationParams,
        optimize_withdrawal_strategy,
        get_balances_at_retirement,
    )

    portfolio = load_portfolio()

    if not portfolio.accounts:
        console.print("[yellow]No accounts configured. Run 'fire init' or update data/config.yaml[/yellow]")
        return

    current_age = portfolio.settings.current_age

    # Set up parameters
    params = OptimizationParams(
        current_age=current_age,
        retirement_age=retirement_age,
        death_age=death_age,
        pension_access_age=pension_access,
        pension_contribution_stop_age=pension_stop,
    )

    # Get contribution info from portfolio
    if portfolio.income:
        params.pension_contribution_min = portfolio.income.gross_salary * 0.12
        console.print(f"[dim]Using 12% employer match: £{params.pension_contribution_min:,.0f}/yr[/dim]")

    # Get exchange rate
    params.sek_to_gbp = portfolio.exchange_rates.get("SEK_GBP", 0.073)

    # Show current balances and projected at retirement
    console.print()
    console.print(Panel.fit("[bold]Withdrawal Optimization[/bold]", style="blue"))
    console.print()

    balances = get_balances_at_retirement(portfolio, params)

    console.print(f"[bold]Projected Balances at Retirement (age {retirement_age}):[/bold]")
    console.print(f"  ISA: £{balances['isa']:,.0f}")
    console.print(f"  UK Pension: £{balances['uk_pension']:,.0f}")
    console.print(f"  Swedish Private: {balances['swedish_private_sek']:,.0f} SEK (£{balances['swedish_private_sek'] * params.sek_to_gbp:,.0f})")
    console.print(f"  Swedish State: {balances['swedish_state_sek']:,.0f} SEK (£{balances['swedish_state_sek'] * params.sek_to_gbp:,.0f})")
    console.print(f"  Cash: £{balances['cash']:,.0f}")
    console.print(f"  [bold]Total: £{balances['total_gbp']:,.0f}[/bold]")

    console.print()
    console.print(f"[bold]Assumptions:[/bold]")
    console.print(f"  Current age: {current_age}")
    console.print(f"  Retire at: {retirement_age}")
    console.print(f"  Target death age: {death_age}")
    console.print(f"  UK pension accessible: {pension_access}")
    console.print(f"  Bridge phase: {retirement_age}-{pension_access - 1} ({pension_access - retirement_age} years)")
    console.print(f"  Pension phase: {pension_access}-{death_age} ({death_age - pension_access + 1} years)")
    console.print(f"  Pension contributions: full until {pension_stop}, then employer match until {retirement_age}")
    console.print(f"  Growth rate: 4% real")

    # Run optimization
    console.print()
    console.print("[bold]Finding optimal strategies...[/bold]")

    results = optimize_withdrawal_strategy(portfolio, params)

    if not results:
        console.print("[red]No viable strategies found. You may need to work longer or reduce spending.[/red]")
        return

    console.print()
    console.print(f"[bold]Top {min(top, len(results))} Strategies (sorted by lifetime spending):[/bold]")
    console.print()

    table = Table()
    table.add_column("Bridge\n(45-56)", justify="right")
    table.add_column("Pension\n(57-100)", justify="right")
    table.add_column("Monthly\nBridge", justify="right")
    table.add_column("Monthly\nPension", justify="right")
    table.add_column("Jump at\n57", justify="right")
    table.add_column("Lifetime\nTotal", justify="right", style="green")

    for i, r in enumerate(results[:top]):
        style = "bold" if i == 0 else ""
        jump_style = "green" if r.jump_percent > 0 else "red" if r.jump_percent < 0 else ""

        table.add_row(
            f"£{r.bridge_spend:,.0f}",
            f"£{r.pension_spend:,.0f}",
            f"£{r.monthly_bridge:,.0f}",
            f"£{r.monthly_pension:,.0f}",
            f"[{jump_style}]{r.jump_percent:+.0f}%[/{jump_style}]" if jump_style else f"{r.jump_percent:+.0f}%",
            f"£{r.total_lifetime_spending:,.0f}",
            style=style,
        )

    console.print(table)

    # Highlight best and most balanced
    best = results[0]
    console.print()
    console.print(f"[bold green]Maximum Lifetime Spending:[/bold green]")
    console.print(f"  Bridge: £{best.bridge_spend:,.0f}/yr (£{best.monthly_bridge:,.0f}/mo)")
    console.print(f"  Pension: £{best.pension_spend:,.0f}/yr (£{best.monthly_pension:,.0f}/mo)")
    console.print(f"  Total: £{best.total_lifetime_spending:,.0f} over {best.bridge_years + best.pension_years} years")

    # Find most balanced (closest to 30-40% jump)
    balanced = min(results, key=lambda r: abs(r.jump_percent - 35))
    if balanced != best:
        console.print()
        console.print(f"[bold cyan]Most Balanced (35% jump):[/bold cyan]")
        console.print(f"  Bridge: £{balanced.bridge_spend:,.0f}/yr (£{balanced.monthly_bridge:,.0f}/mo)")
        console.print(f"  Pension: £{balanced.pension_spend:,.0f}/yr (£{balanced.monthly_pension:,.0f}/mo)")
        console.print(f"  Total: £{balanced.total_lifetime_spending:,.0f} over {balanced.bridge_years + balanced.pension_years} years")

    # Find flat rate option
    flat = min(results, key=lambda r: abs(r.jump_percent))
    if flat not in (best, balanced):
        console.print()
        console.print(f"[bold yellow]Flat Rate (simplest):[/bold yellow]")
        console.print(f"  £{flat.bridge_spend:,.0f}/yr throughout")
        console.print(f"  Total: £{flat.total_lifetime_spending:,.0f}")


if __name__ == "__main__":
    cli()
