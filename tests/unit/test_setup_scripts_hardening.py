"""#870-#874: pins for setup.sh / setup_postgresql_databases.sh hardening.

#870 umask 077 set inside setup_credentials() used to leak into the venv
     step, leaving site-packages unreadable by the aitbc service user.
#871 the profiles step created blockchain.env first, so the identities
     step's open-island template seeding never ran.
#872 a random PROPOSER_ID was written before init_proposer.py ran, so a
     fresh hub never got a real proposer wallet (init_proposer refuses to
     replace a configured id that has no keystore).
#873 setup_postgresql_databases.sh rotated every role password on each
     run and clobbered env files with `cat >`.
#874 listen_addresses changes need a postmaster restart, not a reload.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETUP = (REPO / "scripts/deployment/setup.sh").read_text()
PG = (REPO / "scripts/deployment/setup_postgresql_databases.sh").read_text()


def _func(text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}\(\) \{{(.*?)^\}}", text, re.S | re.M)
    assert m, f"function {name} not found"
    return m.group(1)


# --- #870 -----------------------------------------------------------------


def test_umask_077_is_restored_after_setup_credentials():
    body = _func(SETUP, "setup_credentials")
    save = body.find("$(umask)")
    # only real `umask 077` statements, not mentions in comments
    stmts = [m.start() for m in re.finditer(r"^\s*umask 077\s*$", body, re.M)]
    restore = body.rfind('umask "$_creds_umask"')
    assert save != -1, "setup_credentials must save the caller's umask"
    assert stmts, "expected umask 077 for secret writes"
    assert save < stmts[0], "umask must be saved before the first umask 077"
    assert restore > stmts[-1], "umask must be restored after the last umask 077 in setup_credentials"


def test_venv_readability_checked_as_aitbc_user():
    body = _func(SETUP, "setup_venvs")
    assert "sudo -u aitbc" in body, "post-install readability check must run as aitbc"
    assert re.search(r"sudo -u aitbc test -r /opt/aitbc/venv", body)


# --- #871 -----------------------------------------------------------------


def test_profiles_step_seeds_template_for_followers():
    body = _func(SETUP, "setup_node_profiles")
    assert "blockchain.env.open-island" in body, (
        "profiles step must seed the open-island template before writing "
        "profile keys, otherwise blockchain.env exists and step 8 never "
        "seeds the template"
    )
    # a hub must not inherit follower template keys
    seed_idx = body.find("blockchain.env.open-island")
    assert '!= "hub"' in body[:seed_idx] or '!= "hub"' in body[seed_idx - 200 : seed_idx + 200], (
        "template seeding must be gated to non-hub modes"
    )


def test_identities_step_adds_missing_p2p_node_id_to_existing_env():
    body = _func(SETUP, "setup_node_identities")
    m = re.search(
        r"Preserving existing /etc/aitbc/blockchain\.env(.*?)(?:elif|else)",
        body,
        re.S,
    )
    assert m, "preserve-existing branch not found"
    assert "set_env P2P_NODE_ID" in m.group(1), (
        "when blockchain.env already exists (e.g. seeded by the profiles step), P2P_NODE_ID must still be added"
    )


# --- #872 -----------------------------------------------------------------


def test_no_random_proposer_id_for_hub_mode():
    body = _func(SETUP, "setup_node_identities")
    assert '"${BLOCKCHAIN_MODE:-follower}" != "hub"' in body, "PROPOSER_ID writes must be gated to non-hub mode"
    for m in re.finditer(r"set_env PROPOSER_ID", body):
        window = body[max(0, m.start() - 300) : m.start()]
        assert '"${BLOCKCHAIN_MODE:-follower}" != "hub"' in window, (
            "every set_env PROPOSER_ID must be inside the non-hub guard"
        )


# --- #873 -----------------------------------------------------------------


def test_pg_setup_never_rotates_existing_role_passwords():
    assert "ALTER USER" not in PG, "re-running setup must not rotate passwords of existing roles"
    assert "pg_roles" in PG or "pg_catalog.pg_roles" in PG


def test_pg_setup_psql_failures_are_fatal():
    for i, line in enumerate(PG.splitlines(), 1):
        if "psql" in line and re.search(r"\|\|\s*(true|echo)", line):
            raise AssertionError(f"line {i} swallows a psql failure: {line.strip()}")


def test_pg_setup_merges_env_keys_instead_of_clobbering():
    assert 'cat > "$GOV_ENV"' not in PG, "governance env must merge keys, not clobber"
    assert 'cat > "$MEMPOOL_ENV"' not in PG, "mempool env must merge keys, not clobber"
    assert "set_env_key" in PG


# --- #874 -----------------------------------------------------------------


def test_listen_addresses_change_restarts_postgresql():
    for name in ("enforce_local_only", "configure_remote_connections"):
        body = _func(PG, name)
        assert "restart postgresql" in body or "systemctl restart" in body, (
            f"{name}: listen_addresses needs a restart, reload is not enough"
        )
        assert "pending_restart" in body, f"{name}: must check pg_settings.pending_restart and report real state"
