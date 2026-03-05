# CLI Config Commands Test Scenarios

This document outlines the test scenarios for the `aitbc config` command group. These scenarios verify the functionality of configuration management, including viewing, editing, setting values, and managing environments and profiles.

## 1. `config edit`

**Command Description:** Open the configuration file in the default system editor.

### Scenario 1.1: Edit Local Configuration
- **Command:** `aitbc config edit`
- **Description:** Attempt to open the local repository/project configuration file.
- **Expected Output:** The system's default text editor (e.g., `nano`, `vim`, or `$EDITOR`) opens with the contents of the local configuration file. Exiting the editor should return cleanly to the terminal.

### Scenario 1.2: Edit Global Configuration
- **Command:** `aitbc config edit --global`
- **Description:** Attempt to open the global (user-level) configuration file.
- **Expected Output:** The editor opens the configuration file located in the user's home directory (e.g., `~/.aitbc/config.yaml`).

## 2. `config environments`

**Command Description:** List available environments configured in the system.

### Scenario 2.1: List Environments
- **Command:** `aitbc config environments`
- **Description:** Display all configured environments (e.g., devnet, testnet, mainnet).
- **Expected Output:** A formatted list or table showing available environments, their associated node URLs, and indicating which one is currently active.

## 3. `config export`

**Command Description:** Export configuration to standard output.

### Scenario 3.1: Export as YAML
- **Command:** `aitbc config export --format yaml`
- **Description:** Dump the current active configuration in YAML format.
- **Expected Output:** The complete configuration printed to stdout as valid YAML.

### Scenario 3.2: Export Global Config as JSON
- **Command:** `aitbc config export --global --format json`
- **Description:** Dump the global configuration in JSON format.
- **Expected Output:** The complete global configuration printed to stdout as valid JSON.

## 4. `config import-config`

**Command Description:** Import configuration from a file.

### Scenario 4.1: Merge Configuration
- **Command:** `aitbc config import-config new_config.yaml --merge`
- **Description:** Import a valid YAML config file and merge it with the existing configuration.
- **Expected Output:** Success message indicating the configuration was merged successfully. A subsequent `config show` should reflect the merged values.

## 5. `config path`

**Command Description:** Show the absolute path to the configuration file.

### Scenario 5.1: Local Path
- **Command:** `aitbc config path`
- **Description:** Get the path to the currently active local configuration.
- **Expected Output:** The absolute file path printed to stdout (e.g., `/home/user/project/.aitbc.yaml`).

### Scenario 5.2: Global Path
- **Command:** `aitbc config path --global`
- **Description:** Get the path to the global configuration file.
- **Expected Output:** The absolute file path to the user's global config (e.g., `/home/user/.aitbc/config.yaml`).

## 6. `config profiles`

**Command Description:** Manage configuration profiles.

### Scenario 6.1: List Profiles
- **Command:** `aitbc config profiles list`
- **Description:** View all saved configuration profiles.
- **Expected Output:** A list of profile names with an indicator for the currently active profile.

### Scenario 6.2: Save and Load Profile
- **Command:** 
  1. `aitbc config profiles save test_profile`
  2. `aitbc config profiles load test_profile`
- **Description:** Save the current state as a new profile, then attempt to load it.
- **Expected Output:** Success messages for both saving and loading the profile.

## 7. `config reset`

**Command Description:** Reset configuration to default values.

### Scenario 7.1: Reset Local Configuration
- **Command:** `aitbc config reset`
- **Description:** Revert the local configuration to factory defaults. (Note: May require a confirmation prompt).
- **Expected Output:** Success message indicating the configuration has been reset. A subsequent `config show` should reflect default values.

## 8. `config set`

**Command Description:** Set a specific configuration value.

### Scenario 8.1: Set Valid Key
- **Command:** `aitbc config set node.url "http://localhost:8000"`
- **Description:** Modify a standard configuration key.
- **Expected Output:** Success message indicating the key was updated.

### Scenario 8.2: Set Global Key
- **Command:** `aitbc config set --global default_chain "ait-devnet"`
- **Description:** Modify a key in the global configuration file.
- **Expected Output:** Success message indicating the global configuration was updated.

## 9. `config set-secret` & `config get-secret`

**Command Description:** Manage encrypted configuration values (like API keys or passwords).

### Scenario 9.1: Store and Retrieve Secret
- **Command:** 
  1. `aitbc config set-secret api_key "super_secret_value"`
  2. `aitbc config get-secret api_key`
- **Description:** Securely store a value and retrieve it.
- **Expected Output:** 
  1. Success message for setting the secret.
  2. The string `super_secret_value` is returned upon retrieval.

## 10. `config show`

**Command Description:** Display the current active configuration.

### Scenario 10.1: Display Configuration
- **Command:** `aitbc config show`
- **Description:** View the currently loaded and active configuration settings.
- **Expected Output:** A formatted, readable output of the active configuration tree (usually YAML-like or a formatted table), explicitly hiding or masking sensitive values.

## 11. `config validate`

**Command Description:** Validate the current configuration against the schema.

### Scenario 11.1: Validate Healthy Configuration
- **Command:** `aitbc config validate`
- **Description:** Run validation on a known good configuration file.
- **Expected Output:** Success message stating the configuration is valid.

### Scenario 11.2: Validate Corrupted Configuration
- **Command:** manually edit the config file to contain invalid data (e.g., set a required integer field to a string), then run `aitbc config validate`.
- **Description:** Ensure the validator catches schema violations.
- **Expected Output:** An error message specifying which keys are invalid and why.
