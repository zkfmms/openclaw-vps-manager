#!/usr/bin/env python3
"""Rich CLI interface for OpenClaw VPS Manager."""
import asyncio
import os
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt

app = typer.Typer(help="OpenClaw VPS Manager CLI")
console = Console()

# Configuration
API_BASE_URL = os.getenv("VPS_MANAGER_API_URL", "http://localhost:8000")
API_TOKEN = os.getenv("VPS_MANAGER_TOKEN", "")


def get_client() -> httpx.AsyncClient:
    """Get HTTP client with authentication."""
    headers = {}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    return httpx.AsyncClient(base_url=API_BASE_URL, headers=headers, timeout=30.0)


@app.command()
def health():
    """Check API health status."""
    with console.status("[bold green]Checking API health..."):
        response = httpx.get(f"{API_BASE_URL}/health")

    if response.status_code == 200:
        console.print(Panel(response.json(), title="[bold green]API Health", border_style="green"))
    else:
        console.print(f"[red]API health check failed: {response.status_code}")


@app.command()
def list_vps(customer_id: Optional[int] = typer.Argument(None)):
    """List all VPS servers."""
    async def _list_vps():
        async with get_client() as client:
            params = {}
            if customer_id:
                params["customer_id"] = customer_id

            response = await client.get("/api/v1/vps", params=params)

            if response.status_code != 200:
                console.print(f"[red]Failed to list VPS: {response.status_code}")
                return

            vps_list = response.json()

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
                    f"[{status_color}]{vps['status'][/{status_color}]",
                )

            console.print(table)

    asyncio.run(_list_vps())


@app.command()
def list_customers():
    """List all customers."""
    async def _list_customers():
        async with get_client() as client:
            response = await client.get("/api/v1/customers")

            if response.status_code != 200:
                console.print(f"[red]Failed to list customers: {response.status_code}")
                return

            customers = response.json()

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
    customer_id: Optional[int] = typer.Argument(None),
    vps_id: Optional[int] = typer.Argument(None),
):
    """List deployments."""
    async def _list_deployments():
        async with get_client() as client:
            params = {}
            if customer_id:
                params["customer_id"] = customer_id
            if vps_id:
                params["vps_id"] = vps_id

            response = await client.get("/api/v1/deployments", params=params)

            if response.status_code != 200:
                console.print(f"[red]Failed to list deployments: {response.status_code}")
                return

            deployments = response.json()

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
        async with get_client() as client:
            response = await client.get(f"/api/v1/config/{customer_id}")

            if response.status_code != 200:
                console.print(f"[red]Failed to get config: {response.status_code}")
                return

            config = response.json()
            console.print(Panel.from_dict(config, title="[bold green]OpenClaw Configuration"))

    asyncio.run(_show_config())


@app.command()
def deploy_vps(vps_id: int):
    """Deploy configuration to a VPS."""
    async def _deploy_vps():
        with console.status(f"[bold yellow]Deploying to VPS {vps_id}..."):
            async with get_client() as client:
                response = await client.post(f"/api/v1/vps/{vps_id}/deploy")

        if response.status_code == 200:
            console.print(f"[bold green]Deployment successful for VPS {vps_id}")
            console.print(Panel(response.json()))
        else:
            console.print(f"[red]Deployment failed: {response.status_code}")
            console.print(response.json())

    asyncio.run(_deploy_vps())


@app.command()
def restart_vps(vps_id: int):
    """Restart OpenClaw service on a VPS."""
    async def _restart_vps():
        with console.status(f"[bold yellow]Restarting VPS {vps_id}..."):
            async with get_client() as client:
                response = await client.post(f"/api/v1/vps/{vps_id}/restart")

        if response.status_code == 204:
            console.print(f"[bold green]Restart successful for VPS {vps_id}")
        else:
            console.print(f"[red]Restart failed: {response.status_code}")

    asyncio.run(_restart_vps())


@app.command()
def check_health(vps_id: int):
    """Check health status of a VPS."""
    async def _check_health():
        async with get_client() as client:
            response = await client.get(f"/api/v1/vps/{vps_id}/health")

            if response.status_code != 200:
                console.print(f"[red]Health check failed: {response.status_code}")
                return

            health = response.json()

            table = Table(title=f"VPS {vps_id} Health Status")
            table.add_column("Metric", style="cyan")
            table.add_column("Status", style="bold")

            for key, value in health.items():
                if key != "vps_id":
                    status_color = "green" if value else "red"
                    table.add_row(key.replace("_", " ").title(), f"[{status_color}]{value}[/{status_color}]")

            console.print(table)

    asyncio.run(_check_health())


@app.command()
def list_audit_logs(limit: int = typer.Option(100, help="Number of logs to show")):
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
def restart_vps(vps_id: int):
    """Restart OpenClaw service on a VPS."""
    async def _restart_vps():
        with console.status(f"[bold yellow]Restarting VPS {vps_id}..."):
            async with get_client() as client:
                response = await client.post(f"/api/v1/vps/{vps_id}/restart")

        if response.status_code == 204:
            console.print(f"[bold green]Restart successful for VPS {vps_id}")
        else:
            console.print(f"[red]Restart failed: {response.status_code}")

    asyncio.run(_restart_vps())


@app.command()
def check_health(vps_id: int):
    """Check health status of a VPS."""
    async def _check_health():
        with console.status(f"[bold yellow]Checking VPS {vps_id} health..."):
            async with get_client() as client:
                response = await client.get(f"/api/v1/vps/{vps_id}/health")

        if response.status_code == 200:
            health = response.json()
            status_color = "green" if health.get("service_active") else "yellow"
            console.print(Panel.from_dict(health, title=f"[bold]VPS {vps_id} Health", border_style=status_color))
        else:
            console.print(f"[red]Health check failed: {response.status_code}")

    asyncio.run(_check_health())


@app.command()
def list_audit_logs(limit: int = typer.Option(100, help="Number of logs to show")):
    """List audit logs."""
    async def _list_audit_logs():
        with console.status("[bold green]Fetching audit logs..."):
            async with get_client() as client:
                response = await client.get(f"/api/v1/audit/logs?limit={limit}")

        if response.status_code == 200:
            logs = response.json()
            table = Table(title="Audit Logs")
            table.add_column("ID", style="cyan")
            table.add_column("User ID", style="yellow")
            table.add_column("Action", style="blue")
            table.add_column("Resource", style="magenta")
            table.add_column("Timestamp", style="green")

            for log in logs:
                table.add_row(
                    str(log["id"]),
                    str(log.get("user_id", "N/A")),
                    log["action"],
                    log["resource_type"],
                    log["timestamp"],
                )

            console.print(table)
        else:
            console.print(f"[red]Failed to fetch audit logs: {response.status_code}")

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
                    f"[{status_color}]{record['status'][/{status_color}]",
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
            else:
                console.print(f"[red]Unknown command: {command}[/red]")
                console.print("Type 'help' for available commands\n")

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    app()
