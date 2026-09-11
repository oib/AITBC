#!/bin/bash
# Shared deployment target configuration.
#
# These scripts used to hardcode one server's ssh alias and public hostname.
# That tied them to a single deployment and put infrastructure identifiers in a
# public repository. Set them in the environment instead:
#
#   export AITBC_SSH_TARGET=my-host-root       # ssh/scp destination
#   export AITBC_PUBLIC_HOST=aitbc.example.net # public FQDN, for TLS and URLs
#
# Source this file, then call require_deploy_var for whatever the script needs.

require_deploy_var() {
    local name="$1" hint="$2"
    if [ -z "${!name:-}" ]; then
        echo "ERROR: $name is not set." >&2
        echo "       $hint" >&2
        echo "       See scripts/deployment/deploy/deploy-env.sh" >&2
        exit 1
    fi
}
