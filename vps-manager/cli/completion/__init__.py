"""Shell completion utilities for VPS Manager CLI."""
import os
from pathlib import Path
from typing import List


def get_completion_scripts_dir() -> Path:
    """
    Get the directory containing completion scripts.

    Returns:
        Path to completion scripts directory.
    """
    return Path(__file__).parent


def install_bash_completion() -> str:
    """
    Get bash completion installation instruction.

    Returns:
        Command to install bash completion.
    """
    script_path = get_completion_scripts_dir() / "bash.sh"
    return f"source {script_path}"


def install_zsh_completion() -> str:
    """
    Get zsh completion installation instruction.

    Returns:
        Command to install zsh completion.
    """
    script_path = get_completion_scripts_dir() / "zsh.sh"
    return f"source {script_path}"


def install_fish_completion() -> str:
    """
    Get fish completion installation instruction.

    Returns:
        Command to install fish completion.
    """
    script_path = get_completion_scripts_dir() / "fish.sh"
    fish_dir = Path.home() / ".config" / "fish" / "completions"
    return f"mkdir -p {fish_dir} && cp {script_path} {fish_dir}/vps-manager.fish"


def get_shell_type() -> str:
    """
    Detect the current shell type.

    Returns:
        Shell type (bash, zsh, fish, or unknown).
    """
    shell = os.environ.get("SHELL", "")

    if "bash" in shell:
        return "bash"
    elif "zsh" in shell:
        return "zsh"
    elif "fish" in shell:
        return "fish"
    else:
        return "unknown"


def get_available_completions() -> List[str]:
    """
    Get list of available completion script types.

    Returns:
        List of shell types with completion scripts.
    """
    return ["bash", "zsh", "fish"]


def get_completion_installation_commands(shell_type: str) -> str:
    """
    Get installation command for a specific shell type.

    Args:
        shell_type: Type of shell (bash, zsh, fish).

    Returns:
        Installation command string.
    """
    if shell_type == "bash":
        return install_bash_completion()
    elif shell_type == "zsh":
        return install_zsh_completion()
    elif shell_type == "fish":
        return install_fish_completion()
    else:
        return f"Unknown shell type: {shell_type}"
