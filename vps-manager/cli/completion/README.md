# Shell Completion for VPS Manager CLI

This directory contains shell completion scripts for the VPS Manager CLI.

## Installation

### Bash

Add the completion to your `.bashrc`:

```bash
source /path/to/vps-manager/cli/completion/bash.sh
```

Or copy to the bash completion directory:

```bash
cp /path/to/vps-manager/cli/completion/bash.sh /etc/bash_completion.d/vps-manager
```

### Zsh

Add the completion to your `.zshrc`:

```bash
source /path/to/vps-manager/cli/completion/zsh.sh
```

Or copy to the zsh completion directory:

```bash
cp /path/to/vps-manager/cli/completion/zsh.sh ~/.zsh/completions/_vps-manager
```

### Fish

Copy the completion to the fish completion directory:

```bash
cp /path/to/vps-manager/cli/completion/fish.sh ~/.config/fish/completions/vps-manager.fish
```

## Usage

Once installed, you can use tab completion to:

- See available commands
- See subcommands
- Get hints for command arguments
- See available options

Example:

```bash
vps-manager <TAB>  # Shows main commands
vps-manager config <TAB>  # Shows config subcommands
vps-manager --<TAB>  # Shows available options
```
