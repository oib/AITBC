#!/bin/bash
# AITBC CLI completion script for bash/zsh

_aitbc_completion() {
    local cur prev words
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    words=("${COMP_WORDS[@]}")

    # Main commands
    if [[ ${COMP_CWORD} -eq 1 ]]; then
        local commands="admin agent agent-comm analytics auth blockchain chain client config config-show deploy exchange genesis governance marketplace miner monitor multimodal node optimize plugin simulate swarm version wallet"
        COMPREPLY=($(compgen -W "${commands}" -- "${cur}"))
        return 0
    fi

    # Subcommand completions
    case "${words[1]}" in
        wallet)
            local wallet_commands="address backup balance create delete earn history info liquidity-stake liquidity-unstake list multisig-create multisig-propose multisig-sign request-payment restore rewards send spend stake staking-info stats switch unstake"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${wallet_commands}" -- "${cur}"))
            fi
            ;;
        blockchain)
            local blockchain_commands="block blocks info peers status supply sync-status transaction validators"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${blockchain_commands}" -- "${cur}"))
            fi
            ;;
        marketplace)
            local marketplace_commands="agents bid gpu governance offers orders pricing review reviews test"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${marketplace_commands}" -- "${cur}"))
            fi
            ;;
        config)
            local config_commands="edit environments export get-secret import-config path profiles reset set set-secret show validate"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${config_commands}" -- "${cur}"))
            fi
            ;;
        analytics)
            local analytics_commands="alerts dashboard monitor optimize predict summary"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${analytics_commands}" -- "${cur}"))
            fi
            ;;
        agent-comm)
            local agent_comm_commands="collaborate discover list monitor network register reputation send status"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${agent_comm_commands}" -- "${cur}"))
            fi
            ;;
        chain)
            local chain_commands="create delete info list status switch validate"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${chain_commands}" -- "${cur}"))
            fi
            ;;
        client)
            local client_commands="batch-submit blocks cancel history receipt status submit template"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${client_commands}" -- "${cur}"))
            fi
            ;;
        miner)
            local miner_commands="concurrent-mine deregister earnings heartbeat jobs mine poll register status update-capabilities"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${miner_commands}" -- "${cur}"))
            fi
            ;;
        auth)
            local auth_commands="import-env keys login logout refresh status token"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${auth_commands}" -- "${cur}"))
            fi
            ;;
        monitor)
            local monitor_commands="alerts dashboard history metrics webhooks"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${monitor_commands}" -- "${cur}"))
            fi
            ;;
        simulate)
            local simulate_commands="init load-test reset results scenario user workflow"
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${simulate_commands}" -- "${cur}"))
            fi
            ;;
    esac

    # Option completions
    case "${prev}" in
        --output)
            COMPREPLY=($(compgen -W "table json yaml" -- "${cur}"))
            ;;
        --config-file)
            COMPREPLY=($(compgen -f -- "${cur}"))
            ;;
        --wallet-name)
            COMPREPLY=($(compgen -W "$(aitbc wallet list 2>/dev/null | awk 'NR>2 {print $1}')" -- "${cur}"))
            ;;
        --api-key)
            COMPREPLY=($(compgen -W "your_api_key_here" -- "${cur}"))
            ;;
        --url)
            COMPREPLY=($(compgen -W "http://localhost:8000 http://127.0.0.1:18000" -- "${cur}"))
            ;;
    esac

    return 0
}

complete -F _aitbc_completion aitbc
