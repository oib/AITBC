# Scenario 43: Compliance, Plugins, and White-Label Expansion

## Goal

Demonstrate that the canonical CLI supports white-label brand plugins,
compliance-aware job submission, and plugin discovery.

## Preconditions

- `aitbc-agent-core` package is available.
- Plugin files live under `/opt/aitbc/plugins/`.
- A sample plugin (`whitelabel_demo.py`) exists.
- `aitbc` CLI has the `brand`, `plugin`, `compliance`, and `ai` groups.

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

4. Create a new brand plugin:
   ```bash
   aitbc plugin create --name mybrand --output /opt/aitbc/plugins
   aitbc plugin list
   aitbc plugin load mybrand
   ```

5. Switch brand via the plugin:
   ```bash
   AITBC_PLUGINS_DIR=/opt/aitbc/plugins AITBC_ACTIVE_PLUGIN=mybrand aitbc brand show
   ```

6. Check a compliance policy without submitting a job:
   ```bash
   aitbc compliance check --framework hipaa --classification public
   aitbc compliance check --framework hipaa --classification phi
   aitbc compliance classify public
   aitbc compliance classify phi
   ```

7. Enforce compliance on a job submission:
   ```bash
   # This is rejected before any network call because `public` is not allowed under HIPAA
   aitbc ai submit --payment 0.001 --provider-address <shop-address> --model llama3.2:3b \
     --prompt "test" --compliance-framework hipaa --classification public
   ```

8. Submit a compliant job:
   ```bash
   aitbc ai submit --payment 0.001 --provider-address <shop-address> --model llama3.2:3b \
     --prompt "patient notes" --compliance-framework hipaa --classification phi
   ```

## Expected results

- `aitbc brand show` returns brand fields (`name`, `token_symbol`, etc.).
- `aitbc plugin list` returns the plugin names under `plugins_dir`.
- `aitbc plugin load <name>` returns the plugin's `brand` and `roles`.
- `aitbc plugin create` writes a `.py` file that `plugin list` and `plugin load`
  can use immediately.
- With `AITBC_ACTIVE_PLUGIN=mybrand`, the brand fields come from the plugin.
- `aitbc compliance check --framework hipaa --classification public` returns `allowed: false`.
- `aitbc compliance check --framework hipaa --classification phi` returns `allowed: true`.
- `aitbc compliance classify <label>` returns the normalized label and `sensitive`.
- The `public` under HIPAA job submission is rejected before a network call.
- The `phi` under HIPAA job submission passes the compliance hook, attaches
  `data_classification: phi` to the job constraints, and proceeds to the
  coordinator.

## Notes

- `AITBC_BRAND_*` environment variables override brand fields.
- `AITBC_PLUGINS_DIR` defaults to `/opt/aitbc/plugins` in the CLI.
- `AITBC_COMPLIANCE_FRAMEWORK` can be set in the environment to always enforce
  a framework.
- Compliance classifications follow `aitbc.compliance.policies.DataClassification`.
- `aitbc plugin create` also writes a `<name>-manifest.json` file for
  documentation, but the loader only requires `<name>.py`.

## Validation

- Run `aitbc brand show`, `aitbc plugin list`, `aitbc plugin load whitelabel_demo`
  on `aitbc3` or `hub.aitbc` and verify output matches the expected results.
- Run `aitbc compliance check` for each framework/classification pair.
- Run `aitbc ai submit --compliance-framework hipaa --classification public` and
  confirm it fails at the compliance hook.
