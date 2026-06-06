#!/bin/bash
# AITBC CLI Shell Completion Script
# Source this file in your .bashrc or .zshrc to enable tab completion

# AITBC CLI completion for bash
_aitbc_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    # Main commands
    if [[ ${COMP_CWORD} -eq 1 ]]; then
        opts="client miner wallet auth blockchain marketplace admin config simulate help --help --version --url --api-key --output -v --debug --config-file"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
        return 0
    fi
    
    # Command-specific completions
    case "${COMP_WORDS[1]}" in
        client)
            _aitbc_client_completion
            ;;
        miner)
            _aitbc_miner_completion
            ;;
        wallet)
            _aitbc_wallet_completion
            ;;
        auth)
            _aitbc_auth_completion
            ;;
        blockchain)
            _aitbc_blockchain_completion
            ;;
        marketplace)
            _aitbc_marketplace_completion
            ;;
        admin)
            _aitbc_admin_completion
            ;;
        config)
            _aitbc_config_completion
            ;;
        simulate)
            _aitbc_simulate_completion
            ;;
        --output)
            opts="table json yaml"
            COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
            ;;
        *)
            ;;
    esac
}

# Client command completion
_aitbc_client_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="submit status blocks receipts cancel history"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} -eq 3 ]]; then
        case "${COMP_WORDS[2]}" in
            submit)
                opts="inference training fine-tuning"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            status|cancel)
                # Complete with job IDs (placeholder)
                COMPREPLY=( $(compgen -W "job_123 job_456 job_789" -- ${cur}) )
                ;;
            *)
                ;;
        esac
    fi
}

# Miner command completion
_aitbc_miner_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="register poll mine heartbeat status"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    fi
}

# Wallet command completion
_aitbc_wallet_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="balance earn spend history address stats send request"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    fi
}

# Auth command completion
_aitbc_auth_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="login logout token status refresh keys import-env"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} -eq 3 ]]; then
        case "${COMP_WORDS[2]}" in
            keys)
                opts="create list revoke"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            *)
                ;;
        esac
    fi
}

# Blockchain command completion
_aitbc_blockchain_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="blocks block transaction status sync-status peers info supply validators"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    fi
}

# Marketplace command completion
_aitbc_marketplace_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="gpu orders pricing reviews"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} -eq 3 ]]; then
        case "${COMP_WORDS[2]}" in
            gpu)
                opts="list details book release"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            *)
                ;;
        esac
    fi
}

# Admin command completion
_aitbc_admin_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="status jobs miners analytics logs maintenance action"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} -eq 3 ]]; then
        case "${COMP_WORDS[2]}" in
            jobs|miners)
                opts="list details cancel suspend"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            *)
                ;;
        esac
    fi
}

# Config command completion
_aitbc_config_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="show set path edit reset export import validate environments profiles"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} -eq 3 ]]; then
        case "${COMP_WORDS[2]}" in
            set)
                opts="coordinator_url api_key timeout"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            export|import)
                opts="--format json yaml"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            profiles)
                opts="save list load delete"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            *)
                ;;
        esac
    fi
}

# Simulate command completion
_aitbc_simulate_completion() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} -eq 2 ]]; then
        opts="init user workflow load-test scenario results reset"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} -eq 3 ]]; then
        case "${COMP_WORDS[2]}" in
            user)
                opts="create list balance fund"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            scenario)
                opts="list run"
                COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
                ;;
            *)
                ;;
        esac
    fi
}

# Register the completion
complete -F _aitbc_completion aitbc

# For zsh compatibility
if [[ -n "$ZSH_VERSION" ]]; then
    autoload -U compinit
    compinit -i
    _aitbc_completion() {
        local matches
        matches=($(compgen -W "$(aitbc _completion_helper "${words[@]}")" -- "${words[CURRENT]}"))
        _describe 'aitbc commands' matches
    }
    compdef _aitbc_completion aitbc
fi

echo "AITBC CLI shell completion loaded!"
echo "Tab completion is now enabled for the aitbc command."
