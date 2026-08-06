#!/bin/bash
# Canonical AITBC service list -- the single place this is written down.
#
# It used to be spelled out inline in diagnose-services.sh, stop-services.sh,
# fix-services.sh and run-local-services.sh. The four had already drifted: diagnose
# listed aitbc-load-secrets and the others did not, and stop-services split the list
# across two systemctl lines, so adding a service meant remembering four edits and
# nothing complained when you forgot one.
#
# Source it:
#     source "$(dirname "${BASH_SOURCE[0]}")/lib/services.sh"
# then iterate AITBC_SERVICES, which is ordered for startup: the chain comes up before
# anything that talks to it.

# Startup order. Reverse it to shut down.
AITBC_SERVICES=(
    aitbc-coordinator-api
    aitbc-blockchain-rpc
    aitbc-blockchain-p2p
    aitbc-exchange
    aitbc-marketplace
    aitbc-trading
    aitbc-wallet
)

# Port each service listens on, for reachability checks. Services with no HTTP port are
# simply absent rather than given a placeholder.
declare -A AITBC_SERVICE_PORTS=(
    [aitbc-coordinator-api]=8203
    [aitbc-blockchain-rpc]=8202
    [aitbc-exchange]=8106
    [aitbc-marketplace]=8107
    [aitbc-trading]=8201
    [aitbc-wallet]=8108
)

# A oneshot unit that loads secrets before the rest start. Not part of AITBC_SERVICES
# because it is not a long-running service -- "is-active" means something different for
# it, and stopping it is meaningless.
AITBC_SECRETS_UNIT="aitbc-load-secrets"

# Shutdown order: dependents first.
aitbc_services_reversed() {
    local i
    for ((i = ${#AITBC_SERVICES[@]} - 1; i >= 0; i--)); do
        printf '%s\n' "${AITBC_SERVICES[i]}"
    done
}
