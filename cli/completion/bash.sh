#!/bin/bash
# Bash completion script for vps-manager CLI

_vps_manager_completion() {
    local cur prev words cword
    _init_completion || return

    # Main commands
    local commands="health list-vps list-customers list-deployments show-config deploy-vps restart-vps check-health list-audit-logs interactive config help"

    # Subcommands
    case "${prev}" in
        config)
            local config_commands="init show set get reset"
            COMPREPLY=($(compgen -W "${config_commands}" -- "${cur}"))
            return 0
            ;;
        show-config)
            # Need to suggest customer IDs - would need to call API
            return 0
            ;;
        deploy-vps|restart-vps|check-health)
            # Need to suggest VPS IDs - would need to call API
            return 0
            ;;
        help)
            COMPREPLY=($(compgen -W "${commands}" -- "${cur}"))
            return 0
            ;;
    esac

    # Top-level completion
    if [[ ${cword} -eq 1 ]]; then
        COMPREPLY=($(compgen -W "${commands}" -- "${cur}"))
    fi

    # Config subcommand completion
    if [[ ${cword} -eq 2 && ${prev} == "config" ]]; then
        local config_commands="init show set get reset"
        COMPREPLY=($(compgen -W "${config_commands}" -- "${cur}"))
    fi
}

complete -F _vps_manager_completion vps-manager
complete -F _vps_manager_completion python
