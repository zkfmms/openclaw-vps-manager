#!/usr/bin/env python3
"""Rich CLI interface for OpenClaw VPS Manager."""
import asyncio
import json
import os
from typing import Optional, List

import httpx
import typer
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.json import RichJsonEncoder
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Import config
try:
    from cli.config import get_config, CLIConfig
except ImportError:
    # Fallback for when running from different directory
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from cli.config import get_config, CLIConfig

app = typer.Typer(help="OpenClaw VPS Manager CLI")
console = Console()

# Global flags
verbose = False
quiet = False
output_format = "table"


def format_output(data, format_type: str = None):
    """
    Format output according to specified format.

    Args:
        data: Data to format.
        format_type: Output format (table, json, yaml).
    """
    fmt = format_type or output_format

    if fmt == "json":
        console.print_json(json.dumps(data, cls=RichJsonEncoder))
        return True
    elif fmt == "yaml":
        console.print(yaml.dump(data, default_flow_style=False))
        return True
    return False  # Caller handles table format


def get_client(config: CLIConfig = None) -> httpx.AsyncClient:
    """
    Get HTTP client with authentication.

    Args:
        config: Optional CLI configuration.

    Returns:
        Configured httpx.AsyncClient.
    """
    cfg = config or get_config()
    api_url = cfg.get_api_url()
    token = cfg.get_token()
    timeout = cfg.get_timeout()
    verify_ssl = cfg.get_verify_ssl()

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return httpx.AsyncClient(
        base_url=api_url,
        headers=headers,
        timeout=timeout,
        verify=verify_ssl,
    )


def log_verbose(message: str):
    """Log verbose message if verbose mode is enabled."""
    if verbose:
        console.print(f"[dim]{message}[/dim]")


def log_quiet(message: str):
    """Log message if quiet mode is disabled."""
    if not quiet:
        console.print(message)


@app.callback()
def main(
    verbose_flag: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    quiet_flag: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output"),
    output_fmt: str = typer.Option("table", "--output", "-o", help="Output format (table, json, yaml)"),
):
    """
    Global CLI options.
    """
    global verbose, quiet, output_format
    verbose = verbose_flag
    quiet = quiet_flag
    output_format = output_fmt

    if output_fmt not in ("table", "json", "yaml"):
        console.print("[red]Output format must be one of: table, json, yaml[/red]")
        raise typer.Exit(1)


@app.command()
def health():
    """Check API health status."""
    config = get_config()
    log_verbose(f"Checking health at: {config.get_api_url()}")

    with console.status("[bold green]Checking API health..."):
        response = httpx.get(f"{config.get_api_url()}/health", verify=config.get_verify_ssl())

    if response.status_code == 200:
        data = response.json()
        if format_output(data):
            return
        console.print(Panel(data, title="[bold green]API Health", border_style="green"))
    else:
        console.print(f"[red]API health check failed: {response.status_code}[/red]")


@app.command()
def list_vps(
    customer_id: Optional[int] = typer.Option(None, "--customer-id", "-c", help="Filter by customer ID"),
):
    """List all VPS servers."""
    async def _list_vps():
        config = get_config()
        async with get_client(config) as client:
            params = {}
            if customer_id:
                params["customer_id"] = customer_id

            log_verbose(f"Fetching VPS list with params: {params}")
            response = await client.get("/api/v1/vps", params=params)

            if response.status_code != 200:
                console.print(f"[red]Failed to list VPS: {response.status_code}[/red]")
                if not quiet:
                    console.print(response.text)
                return

            vps_list = response.json()
            log_quiet(f"Found {len(vps_list)} VPS servers")

            if format_output(vps_list):
                return

            table = Table(title="VPS Servers")
            table.add_column("ID", style="cyan")
            table.add_column("Customer ID", style="magenta")
            table.add_column("Hostname", style="yellow")
            table.add_column("SSH User", style="blue")
            table.add_column("Version", style="green")
            table.add_column("Status", style="bold")

            for vps in vps_list:
                status_color = "green" if vps["status"] == "active" else "yellow"
                table.add_row(
                    str(vps["id"]),
                    str(vps["customer_id"]),
                    vps["hostname"],
                    vps["ssh_user"],
                    vps["openclaw_version"],
                    f"[{status_color}]{vps['status']}[/{status_color}]",
                )

            console.print(table)

    asyncio.run(_list_vps())


@app.command()
def list_customers():
    """List all customers."""
    async def _list_customers():
        config = get_config()
        async with get_client(config) as client:
            log_verbose("Fetching customers list")
            response = await client.get("/api/v1/customers")

            if response.status_code != 200:
                console.print(f"[red]Failed to list customers: {response.status_code}[/red]")
                return

            customers = response.json()
            log_quiet(f"Found {len(customers)} customers")

            if format_output(customers):
                return

            table = Table(title="Customers")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="yellow")
            table.add_column("Description", style="blue")
            table.add_column("Git Branch", style="magenta")
            table.add_column("Status", style="bold")

            for customer in customers:
                status_color = "green" if customer["is_active"] else "red"
                table.add_row(
                    str(customer["id"]),
                    customer["name"],
                    customer.get("description", "N/A"),
                    customer["git_branch"],
                    f"[{status_color}]{'Active' if customer['is_active'] else 'Inactive'}[/{status_color}]",
                )

            console.print(table)

    asyncio.run(_list_customers())


@app.command()
def list_deployments(
    customer_id: Optional[int] = typer.Option(None, "--customer-id", "-c", help="Filter by customer ID"),
    vps_id: Optional[int] = typer.Option(None, "--vps-id", "-v", help="Filter by VPS ID"),
    status_filter: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
):
    """List deployments."""
    async def _list_deployments():
        config = get_config()
        async with get_client(config) as client:
            params = {}
            if customer_id:
                params["customer_id"] = customer_id
            if vps_id:
                params["vps_id"] = vps_id
            if status_filter:
                params["status_filter"] = status_filter

            log_verbose(f"Fetching deployments with params: {params}")
            response = await client.get("/api/v1/deployments", params=params)

            if response.status_code != 200:
                console.print(f"[red]Failed to list deployments: {response.status_code}[/red]")
                return

            deployments = response.json()
            log_quiet(f"Found {len(deployments)} deployments")

            if format_output(deployments):
                return

            table = Table(title="Deployments")
            table.add_column("ID", style="cyan")
            table.add_column("VPS ID", style="yellow")
            table.add_column("Customer ID", style="magenta")
            table.add_column("Commit", style="blue")
            table.add_column("Deployed At", style="green")
            table.add_column("Status", style="bold")

            for dep in deployments:
                status_color = "green" if dep["status"] == "success" else "red"
                table.add_row(
                    str(dep["id"]),
                    str(dep["vps_id"]),
                    str(dep["customer_id"]),
                    dep["git_commit_hash"][:7],
                    dep["deployed_at"],
                    f"[{status_color}]{dep['status'].upper()}[/{status_color}]",
                )

            console.print(table)

    asyncio.run(_list_deployments())


@app.command()
def show_config(customer_id: int):
    """Show OpenClaw configuration for a customer."""
    async def _show_config():
        config = get_config()
        async with get_client(config) as client:
            log_verbose(f"Fetching config for customer {customer_id}")
            response = await client.get(f"/api/v1/config/{customer_id}")

            if response.status_code != 200:
                console.print(f"[red]Failed to get config: {response.status_code}[/red]")
                return

            config_data = response.json()

            if format_output(config_data):
                return

            console.print(Panel.from_dict(config_data, title="[bold green]OpenClaw Configuration"))

    asyncio.run(_show_config())


@app.command()
def deploy_vps(vps_id: int):
    """Deploy configuration to a VPS."""
    async def _deploy_vps():
        config = get_config()
        async with get_client(config) as client:
            log_verbose(f"Deploying to VPS {vps_id}")

            with console.status(f"[bold yellow]Deploying to VPS {vps_id}..."):
                response = await client.post(f"/api/v1/vps/{vps_id}/deploy")

        if response.status_code == 200:
            console.print(f"[bold green]Deployment successful for VPS {vps_id}[/bold green]")
            log_quiet("Deployment completed successfully")
            if not quiet and output_format == "table":
                console.print(Panel(response.json()))
        else:
            console.print(f"[red]Deployment failed: {response.status_code}[/red]")
            console.print(response.text)

    asyncio.run(_deploy_vps())


@app.command()
def restart_vps(vps_id: int):
    """Restart OpenClaw service on a VPS."""
    async def _restart_vps():
        config = get_config()
        async with get_client(config) as client:
            log_verbose(f"Restarting VPS {vps_id}")

            with console.status(f"[bold yellow]Restarting VPS {vps_id}..."):
                response = await client.post(f"/api/v1/vps/{vps_id}/restart")

            if response.status_code == 204:
                console.print(f"[bold green]Restart successful for VPS {vps_id}[/bold green]")
                log_quiet("Restart completed successfully")
            else:
                console.print(f"[red]Restart failed: {response.status_code}[/red]")
                console.print(response.text)

    asyncio.run(_restart_vps())


@app.command()
def check_health(
    vps_id: int,
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show detailed health information"),
):
    """Check health status of a VPS."""
    async def _check_health():
        config = get_config()
        async with get_client(config) as client:
            log_verbose(f"Checking health for VPS {vps_id}")
            response = await client.get(f"/api/v1/vps/{vps_id}/health")

            if response.status_code != 200:
                console.print(f"[red]Health check failed: {response.status_code}")
                return

            health = response.json()

            if format_output(health):
                return

            if detailed:
                table = Table(title=f"VPS {vps_id} Health Status")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="bold")

                for key, value in health.items():
                    if key != "vps_id":
                        table.add_row(key.replace("_", " ").title(), str(value))
                console.print(table)
            else:
                # Simplified view
                status = "healthy" if health.get("service_active") else "unhealthy"
                color = "green" if health.get("service_active") else "red"
                console.print(f"[{color}]VPS {vps_id} is {status}[/{color}]")

    asyncio.run(_check_health())


@app.command()
def list_audit_logs(
    limit: int = typer.Option(100, help="Number of logs to show"),
    action: Optional[str] = typer.Option(None, help="Filter by action"),
):
    """List audit logs."""
    async def _list_audit_logs():
        async with get_client() as client:
            response = await client.get(f"/api/v1/audit/logs?limit={limit}")

            if response.status_code != 200:
                console.print(f"[red]Failed to list audit logs: {response.status_code}")
                return

            logs = response.json()

            table = Table(title="Audit Logs")
            table.add_column("ID", style="cyan")
            table.add_column("User ID", style="yellow")
            table.add_column("Action", style="green")
            table.add_column("Resource", style="blue")
            table.add_column("Timestamp", style="magenta")

            for log in logs[:limit]:
                table.add_row(
                    str(log["id"]),
                    str(log.get("user_id", "N/A")),
                    log["action"],
                    log["resource_type"],
                    log["timestamp"],
                )

            console.print(table)

    asyncio.run(_list_audit_logs())


@app.command()
def sync_vps(
    vps_id: int,
    pull: bool = typer.Option(False, "--pull", help="Pull changes from VPS only"),
    push: bool = typer.Option(False, "--push", help="Push changes to VPS only"),
    force: bool = typer.Option(False, "--force", help="Force sync without conflict detection"),
):
    """Sync with VPS (bidirectional Git sync)."""
    async def _sync_vps():
        with console.status(f"[bold yellow]Syncing VPS {vps_id}..."):
            params = {"direction": "both"}
            if pull:
                params["direction"] = "pull"
            if push:
                params["direction"] = "push"
            if force:
                params["force"] = True

            async with get_client() as client:
                response = await client.post(f"/api/v1/sync/vps/{vps_id}/sync", json=params)

        if response.status_code == 200:
            status = response.json()
            status_icon = "✓" if status["status"] == "success" else "✗"
            console.print(f"[bold]Sync {status_icon} {status['message']}[/bold]")
            console.print(f"  Status: {status['status']}")
            console.print(f"  Local commit: {status.get('local_commit', 'N/A')[:7]}...")
            console.print(f"  VPS commit: {status.get('remote_commit', 'N/A')[:7]}...")
            if status.get("conflicts"):
                console.print(f"[red]  Conflicts detected. Use 'sync vps <id> resolve <resolution>' to resolve")
        else:
            console.print(f"[red]Sync failed: {response.status_code}")

    asyncio.run(_sync_vps())


@app.command()
def sync_status(vps_id: int):
    """Get current synchronization status for a VPS."""
    async def _sync_status():
        with console.status("[bold green]Checking sync status..."):
            async with get_client() as client:
                response = await client.get(f"/api/v1/sync/vps/{vps_id}/status")

        if response.status_code == 200:
            status = response.json()
            console.print(Panel.from_dict(status, title=f"[bold]Sync Status - VPS {vps_id}", border_style="blue"))
        else:
            console.print(f"[red]Failed to get sync status: {response.status_code}")

    asyncio.run(_sync_status())


@app.command()
def sync_history(vps_id: int, limit: int = typer.Option(20, help="Number of sync records to show")):
    """Get synchronization history for a VPS."""
    async def _sync_history():
        with console.status("[bold green]Fetching sync history..."):
            async with get_client() as client:
                response = await client.get(f"/api/v1/sync/vps/{vps_id}/history?limit={limit}")

        if response.status_code == 200:
            history = response.json()
            table = Table(title=f"Sync History - VPS {vps_id}")
            table.add_column("Sync ID", style="cyan")
            table.add_column("Status", style="yellow")
            table.add_column("Local Commit", style="blue")
            table.add_column("Remote Commit", style="magenta")
            table.add_column("Type", style="green")
            table.add_column("Time", style="grey")

            for record in history:
                status_color = "green" if record["status"] == "success" else "yellow" if record["status"] == "conflict" else "red"
                table.add_row(
                    str(record["sync_id"]),
                    f"[{status_color}]{record['status']}[/{status_color}]",
                    record.get("local_commit", "N/A")[:7] + "...",
                    record.get("remote_commit", "N/A")[:7] + "...",
                    record["sync_type"],
                    record["created_at"][:19] + "...",
                )

            console.print(table)
        else:
            console.print(f"[red]Failed to fetch sync history: {response.status_code}")

    asyncio.run(_sync_history())


@app.command()
def resolve_sync_conflict(
    vps_id: int,
    resolution: str = typer.Argument(..., help="Resolution: local, remote, merge, or manual"),
):
    """Resolve a merge conflict during synchronization."""
    async def _resolve():
        with console.status(f"[bold yellow]Resolving conflict for VPS {vps_id} using '{resolution}' strategy..."):
            async with get_client() as client:
                response = await client.post(
                    f"/api/v1/sync/vps/{vps_id}/resolve-conflict",
                    json={"resolution": resolution}
                )

        if response.status_code == 200:
            console.print(f"[bold green]Conflict resolved successfully![/bold]")
            console.print(f"Resolution: {resolution}")
        else:
            console.print(f"[red]Failed to resolve conflict: {response.status_code}")

    asyncio.run(_resolve())


@app.command()
def completion(
    shell: str = typer.Argument(..., help="Shell type (bash, zsh, fish)"),
    show_path: bool = typer.Option(False, "--show-path", help="Show the path to completion script"),
):
    """Generate shell completion script."""
    from cli.completion import get_completion_scripts_dir

    scripts_dir = get_completion_scripts_dir()

    if shell == "bash":
        script_path = scripts_dir / "bash.sh"
    elif shell == "zsh":
        script_path = scripts_dir / "zsh.sh"
    elif shell == "fish":
        script_path = scripts_dir / "fish.sh"
    else:
        console.print(f"[red]Unsupported shell: {shell}[/red]")
        console.print("Supported shells: bash, zsh, fish")
        raise typer.Exit(1)

    if show_path:
        console.print(str(script_path))
        return

    console.print(f"To enable {shell} completion, add the following to your {shell} config:")
    console.print()
    console.print(f"[cyan]source {script_path}[/cyan]")
    console.print()
    console.print("Or use the install command:")
    console.print(f"[cyan]vps-manager config completion install {shell}[/cyan]")


@app.command()
def check_all_health():
    """Check health status of all VPS servers."""
    async def _check_all():
        config = get_config()
        async with get_client(config) as client:
            log_verbose("Fetching VPS list for health check")

            # Get VPS list
            response = await client.get("/api/v1/vps")
            if response.status_code != 200:
                console.print("[red]Failed to get VPS list[/red]")
                return

            vps_list = response.json()
            if not vps_list:
                console.print("[yellow]No VPS servers found[/yellow]")
                return

            # Check each VPS health
            results = {"healthy": [], "unhealthy": [], "error": []}

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console,
            ) as progress:
                task = progress.add_task("[bold yellow]Checking VPS health...", total=len(vps_list))

                async with get_client(config) as client:
                    for vps in vps_list:
                        vps_id = vps["id"]
                        response = await client.get(f"/api/v1/vps/{vps_id}/health")

                        if response.status_code == 200:
                            health = response.json()
                            if health.get("service_active"):
                                results["healthy"].append(vps_id)
                            else:
                                results["unhealthy"].append(vps_id)
                        else:
                            results["error"].append(vps_id)

                        progress.update(task, advance=1)

            # Display results
            console.print(f"\n[bold green]Health Check Summary:[/bold green]")
            console.print(f"  [green]Healthy: {len(results['healthy'])}[/green]")
            console.print(f"  [yellow]Unhealthy: {len(results['unhealthy'])}[/yellow]")
            console.print(f"  [red]Error: {len(results['error'])}[/red]")

            if output_format == "table" and not quiet:
                table = Table(title="VPS Health Status")
                table.add_column("ID", style="cyan")
                table.add_column("Hostname", style="yellow")
                table.add_column("Status", style="bold")

                for vps in vps_list:
                    vps_id = vps["id"]
                    if vps_id in results["healthy"]:
                        status = f"[green]healthy[/green]"
                    elif vps_id in results["unhealthy"]:
                        status = f"[yellow]unhealthy[/yellow]"
                    else:
                        status = f"[red]error[/red]"
                    table.add_row(str(vps_id), vps["hostname"], status)

                console.print(table)

    asyncio.run(_check_all())


@app.command()
def deploy_multiple(
    vps_ids: List[int] = typer.Option(..., "--vps-id", "-v", help="VPS IDs to deploy"),
):
    """Deploy configuration to multiple VPS servers."""
    async def _deploy_multiple():
        config = get_config()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("[bold yellow]Deploying to VPS servers...", total=len(vps_ids))

            results = {"success": [], "failed": []}

            async with get_client(config) as client:
                for vps_id in vps_ids:
                    log_verbose(f"Deploying to VPS {vps_id}")
                    response = await client.post(f"/api/v1/vps/{vps_id}/deploy")

                    if response.status_code == 200:
                        results["success"].append(vps_id)
                    else:
                        results["failed"].append(vps_id)

                    progress.update(task, advance=1)

        console.print(f"[bold green]Deployment summary:[/bold green]")
        console.print(f"  Successful: {len(results['success'])}")
        console.print(f"  Failed: {len(results['failed'])}")

        if results["failed"]:
            console.print(f"[red]Failed VPS IDs: {results['failed']}[/red]")
        else:
            console.print(f"[green]All deployments succeeded![/green]")

    asyncio.run(_deploy_multiple())


# Config command group
config_app = typer.Typer(help="Manage CLI configuration")
app.add_typer(config_app, name="config")


@config_app.command("init")
def config_init(
    api_url: str = typer.Option(..., prompt="API URL", help="VPS Manager API URL"),
    token: str = typer.Option(..., prompt="API Token", help="Authentication token"),
):
    """Initialize CLI configuration."""
    config = get_config()
    config.init(api_url, token)
    console.print(f"[green]Configuration initialized for API at: {api_url}[/green]")


@config_app.command("show")
def config_show():
    """Display current configuration."""
    config = get_config()
    config.show()


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Configuration key"),
):
    """Get a configuration value."""
    config = get_config()
    value = config.get(key)
    if value is not None:
        console.print(value)
    else:
        console.print(f"[yellow]Configuration key '{key}' not found[/yellow]")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value"),
):
    """Set a configuration value."""
    config = get_config()

    # Handle special keys
    if key == "api_url":
        config.set_api_url(value)
    elif key == "token":
        config.set_token(value)
    elif key == "output_format":
        config.set_output_format(value)
    else:
        config.set(key, value)

    console.print(f"[green]Configuration set: {key} = {value}[/green]")


@config_app.command("reset")
def config_reset(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Reset configuration to defaults."""
    config = get_config()

    if not confirm:
        if not Confirm.ask("Are you sure you want to reset configuration?", default=False):
            console.print("[yellow]Reset cancelled[/yellow]")
            return

    config.reset()


@app.command()
def interactive():
    """Start interactive mode."""
    console.print("[bold green]OpenClaw VPS Manager - Interactive Mode[/bold green]")
    console.print("Type 'help' for available commands or 'exit' to quit\n")

    while True:
        try:
            command = Prompt.ask("[bold cyan]vps-manager[/bold cyan]")

            if command.lower() in ("exit", "quit"):
                console.print("[yellow]Goodbye![/yellow]")
                break
            elif command.lower() == "help":
                console.print("""
[bold]Available commands:[/bold]
  health              - Check API health
  list-vps            - List all VPS servers
  list-customers      - List all customers
  list-deployments    - List deployments
  show-config <id>    - Show configuration for customer
  deploy <vps-id>     - Deploy to VPS
  restart <vps-id>    - Restart VPS service
  check <vps-id>      - Check VPS health
  logs                - Show audit logs
  sync vps <id>      - Sync with VPS (bidirectional Git)
  sync vps <id> --pull  - Pull changes from VPS
  sync vps <id> --push   - Push changes to VPS
  sync vps <id> --force  - Force sync (overwrite)
  sync status <id>      - Get sync status
  sync history <id>     - Get sync history
  resolve sync <id> <resolution> - Resolve merge conflict
  help                - Show this help
  exit                - Exit interactive mode
                """)
            elif command.lower() == "health":
                health()
            elif command.lower() == "list-vps":
                list_vps()
            elif command.lower() == "list-customers":
                list_customers()
            elif command.lower() == "list-deployments":
                list_deployments()
            elif command.lower().startswith("show-config"):
                try:
                    customer_id = int(command.split()[1])
                    show_config(customer_id)
                except (IndexError, ValueError):
                    console.print("[red]Usage: show-config <customer-id>[/red]")
            elif command.lower().startswith("deploy"):
                try:
                    vps_id = int(command.split()[1])
                    deploy_vps(vps_id)
                except (IndexError, ValueError):
                    console.print("[red]Usage: deploy <vps-id>[/red]")
            elif command.lower().startswith("restart"):
                try:
                    vps_id = int(command.split()[1])
                    restart_vps(vps_id)
                except (IndexError, ValueError):
                    console.print("[red]Usage: restart <vps-id>[/red]")
            elif command.lower().startswith("check"):
                try:
                    vps_id = int(command.split()[1])
                    check_health(vps_id)
                except (IndexError, ValueError):
                    console.print("[red]Usage: check <vps-id>[/red]")
            elif command.lower() == "logs":
                list_audit_logs()
            elif command.lower().startswith("sync"):
                try:
                    parts = command.split()
                    if len(parts) < 3:
                        console.print("[red]Usage: sync vps <id> [--pull|--push|--force] | sync status <id> | sync history <id> | resolve sync <id> <resolution>[/red]")
                    elif parts[1] == "vps":
                        vps_id = int(parts[2])
                        if "--pull" in parts:
                            sync_vps(vps_id, pull=True)
                        elif "--push" in parts:
                            sync_vps(vps_id, push=True)
                        elif "--force" in parts:
                            sync_vps(vps_id, force=True)
                        else:
                            sync_vps(vps_id)
                    elif parts[1] == "status":
                        vps_id = int(parts[2])
                        sync_status(vps_id)
                    elif parts[1] == "history":
                        vps_id = int(parts[2])
                        sync_history(vps_id)
                    else:
                        console.print("[red]Unknown sync command. Usage: sync vps <id> | sync status <id> | sync history <id>[/red]")
                except (IndexError, ValueError):
                    console.print("[red]Usage: sync vps <id> | sync status <id> | sync history <id>[/red]")
            elif command.lower().startswith("resolve"):
                try:
                    parts = command.split()
                    if len(parts) < 4:
                        console.print("[red]Usage: resolve sync <id> <resolution>[/red]")
                    elif parts[1] == "sync":
                        vps_id = int(parts[2])
                        resolution = parts[3]
                        resolve_sync_conflict(vps_id, resolution)
                    else:
                        console.print("[red]Unknown resolve command. Usage: resolve sync <id> <resolution>[/red]")
                except (IndexError, ValueError):
                    console.print("[red]Usage: resolve sync <id> <resolution>[/red]")
            else:
                console.print(f"[red]Unknown command: {command}[/red]")
                console.print("Type 'help' for available commands\n")

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    app()
