# Scenario 43: Compliance, Plugins, and White-Label Expansion

## Goal

Demonstrate that the canonical CLI supports white-label brand plugins,
compliance-aware job submission, and plugin discovery.

## Preconditions

- `aitbc-agent-core` package is available.
- Plugin files live under `/opt/aitbc/plugins/`.
- A sample plugin (`whitelabel_demo.py`) exists.

## Steps

1. Show the active brand:
   ```bash
   aitbc brand show
   ```

2. List available plugins:
   ```bash
   aitbc plugin list
   ```

3. Load a plugin:
   ```bash
   aitbc plugin load whitelabel_demo
   ```

4. Switch brand via the plugin:
   ```bash
   AITBC_PLUGINS_DIR=/opt/aitbc/plugins AITBC_ACTIVE_PLUGIN=whitelabel_demo aitbc brand show
   ```

5. Enforce compliance on a job submission:
   ```bash
   # This should be rejected because `public` is not allowed under HIPAA
   aitbc ai submit --type inference --prompt "test" \
     --compliance-framework hipaa --classification public
   ```

6. Submit a compliant job:
   ```bash
   aitbc ai submit --type inference --prompt "patient notes" \
     --compliance-framework hipaa --classification phi
   ```

## Expected results

- `aitbc brand show` returns brand fields (`name`, `token_symbol`, etc.).
- `aitbc plugin list` returns the plugin names under `plugins_dir`.
- `aitbc plugin load <name>` returns the plugin's `brand` and `roles`.
- With `AITBC_ACTIVE_PLUGIN=whitelabel_demo`, the brand fields come from the
  plugin.
- The `public` under HIPAA submission is rejected.
- The `phi` under HIPAA submission is accepted and the constraint is attached.

## Notes

- `AITBC_BRAND_*` environment variables override brand fields.
- `AITBC_PLUGINS_DIR` defaults to `/opt/aitbc/plugins` in the CLI.
- `AITBC_COMPLIANCE_FRAMEWORK` can be set in the environment to always enforce
  a framework.
- Compliance classifications follow `aitbc.compliance.policies.DataClassification`.
