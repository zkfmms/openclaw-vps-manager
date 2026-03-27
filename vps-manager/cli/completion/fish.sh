#!/usr/bin/env fish
# Fish completion script for vps-manager CLI

complete -c vps-manager -f

# Main commands
complete -c vps-manager -n __fish_use_subcommand -a health -d 'Check API health status'
complete -c vps-manager -n __fish_use_subcommand -a list-vps -d 'List all VPS servers'
complete -c vps-manager -n __fish_use_subcommand -a list-customers -d 'List all customers'
complete -c vps-manager -n __fish_use_subcommand -a list-deployments -d 'List deployments'
complete -c vps-manager -n __fish_use_subcommand -a show-config -d 'Show OpenClaw configuration for a customer'
complete -c vps-manager -n __fish_use_subcommand -a deploy-vps -d 'Deploy configuration to a VPS'
complete -c vps-manager -n __fish_use_subcommand -a restart-vps -d 'Restart OpenClaw service on a VPS'
complete -c vps-manager -n __fish_use_subcommand -a check-health -d 'Check health status of a VPS'
complete -c vps-manager -n __fish_use_subcommand -a list-audit-logs -d 'List audit logs'
complete -c vps-manager -n __fish_use_subcommand -a interactive -d 'Start interactive mode'
complete -c vps-manager -n __fish_use_subcommand -a config -d 'Manage CLI configuration'
complete -c vps-manager -n __fish_use_subcommand -a help -d 'Show help message'

# Options
complete -c vps-manager -s h -l help -d 'Show help message'
complete -c vps-manager -s v -l verbose -d 'Enable verbose output'
complete -c vps-manager -s q -l quiet -d 'Suppress output'
complete -c vps-manager -l output -d 'Output format (table, json, yaml)' -x -a 'table json yaml'

# Config subcommands
complete -c vps-manager -n '__fish_seen_subcommand_from config' -a init -d 'Initialize configuration'
complete -c vps-manager -n '__fish_seen_subcommand_from config' -a show -d 'Display current configuration'
complete -c vps-manager -n '__fish_seen_subcommand_from config' -a set -d 'Set a configuration value'
complete -c vps-manager -n '__fish_seen_subcommand_from config' -a get -d 'Get a configuration value'
complete -c vps-manager -n '__fish_seen_subcommand_from config' -a reset -d 'Reset configuration to defaults'

# Options for list-audit-logs
complete -c vps-manager -n '__fish_seen_subcommand_from list-audit-logs' -l limit -d 'Number of logs to show' -r
