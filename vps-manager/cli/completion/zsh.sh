#compdef vps-manager
# Zsh completion script for vps-manager CLI

_vps_manager() {
    local -a commands
    commands=(
        'health:Check API health status'
        'list-vps:List all VPS servers'
        'list-customers:List all customers'
        'list-deployments:List deployments'
        'show-config:Show OpenClaw configuration for a customer'
        'deploy-vps:Deploy configuration to a VPS'
        'restart-vps:Restart OpenClaw service on a VPS'
        'check-health:Check health status of a VPS'
        'list-audit-logs:List audit logs'
        'interactive:Start interactive mode'
        'config:Manage CLI configuration'
        'help:Show help message'
    )

    _vps_manager_config_commands() {
        local -a config_commands
        config_commands=(
            'init:Initialize configuration'
            'show:Display current configuration'
            'set:Set a configuration value'
            'get:Get a configuration value'
            'reset:Reset configuration to defaults'
        )
        _describe -t command 'config commands' config_commands
    }

    if (( CURRENT == 2 )); then
        _describe -t command 'commands' commands
    elif (( CURRENT >= 3 )); then
        case ${words[2]} in
            config)
                _vps_manager_config_commands
                ;;
            *)
                # For ID arguments, we could suggest fetching from API
                if [[ ${words[2]} =~ (show-config|deploy-vps|restart-vps|check-health) ]]; then
                    _message -r 'Enter ID number'
                fi
                ;;
        esac
    fi
}

_vps_manager "$@"
