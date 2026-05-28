# Configuration Profiles for hermes Agents

**Level**: Beginner  
**Prerequisites**: Basic CLI knowledge, AITBC CLI installed  
**Estimated Time**: 15 minutes  
**Last Updated**: 2026-05-27  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Configuration Profiles

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [47 Cross Chain Atomic Swap](./47_cross_chain_atomic_swap.md)
- **📖 Next Scenario**: [49 Resource Management](./49_resource_management.md)
- **⚙️ Config Documentation**: [CLI Config Commands](../cli/CLI_DOCUMENTATION.md)

---

## 📚 **Scenario Overview**

This scenario demonstrates how hermes agents use configuration profiles to manage different AITBC environments. Profiles allow agents to quickly switch between development, staging, and production configurations without manually editing config files.

### **Use Case**
An hermes agent needs to:
- Switch between multiple coordinator environments (dev, staging, prod)
- Save frequently-used configurations for quick access
- Maintain separate profiles for different network topologies
- Share configuration profiles across team members

### **What You'll Learn**
- Save current configuration as a named profile
- List all available profiles
- Load a profile to switch configurations
- Delete unused profiles
- Understand profile storage location and format

### **Features Combined**
- **Profile Management**: Save, list, load, and delete configuration profiles
- **Environment Switching**: Quick switching between different coordinator URLs
- **File System Integration**: Profiles stored in `~/.config/aitbc/profiles/`
- **Security**: API keys are not saved in profiles (must be set separately)

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Basic command-line interface usage
- Understanding of YAML configuration files
- AITBC CLI installed and accessible

### **System Requirements**
- AITBC CLI installed
- Write access to `~/.config/aitbc/profiles/` directory
- Coordinator URL configured (can be set via `aitbc config set`)

---

## 🚀 **Quick Start**

```bash
# Save current configuration as a profile
aitbc config profiles save development

# List all available profiles
aitbc config profiles list

# Load a profile
aitbc config profiles load production

# Delete a profile
aitbc config profiles delete old_profile
```

---

## 📖 **Detailed Steps**

### Step 1: Configure Base Settings

Before creating profiles, set up your base configuration:

```bash
# Set coordinator URL
aitbc config set coordinator_url http://127.0.0.1:8011

# Set timeout
aitbc config set timeout 30

# Verify configuration
aitbc config show
```

**Expected Output:**
```
coordinator_url: http://127.0.0.1:8011
api_key: None
timeout: 30
config_file: /home/user/.aitbc.yaml
```

### Step 2: Save Development Profile

Save your current configuration as a development profile:

```bash
aitbc config profiles save development
```

**Expected Output:**
```
Profile 'development' saved
```

**What happens:**
- Profile file created at `~/.config/aitbc/profiles/development.yaml`
- Current coordinator_url and timeout saved
- API key is NOT saved (security measure)

**Verify profile file:**
```bash
cat ~/.config/aitbc/profiles/development.yaml
```

**Expected file content:**
```yaml
coordinator_url: http://127.0.0.1:8011
timeout: 30
```

### Step 3: Configure and Save Production Profile

Switch to production settings and save as a profile:

```bash
# Set production coordinator URL
aitbc config set coordinator_url http://prod.example.com:8011

# Set production timeout
aitbc config set timeout 60

# Save as production profile
aitbc config profiles save production
```

**Expected Output:**
```
Coordinator URL set to: http://prod.example.com:8011
Timeout set to: 60s
Profile 'production' saved
```

### Step 4: List All Profiles

View all available profiles:

```bash
aitbc config profiles list
```

**Expected Output:**
```json
{
  "profiles": [
    {
      "name": "development",
      "coordinator_url": "http://127.0.0.1:8011",
      "timeout": 30
    },
    {
      "name": "production",
      "coordinator_url": "http://prod.example.com:8011",
      "timeout": 60
    }
  ]
}
```

### Step 5: Load a Profile

Switch to a different environment by loading a profile:

```bash
aitbc config profiles load development
```

**Expected Output:**
```
Profile 'development' loaded
```

**What happens:**
- Profile content written to `.aitbc.yaml` in current directory
- Current configuration overwritten with profile values
- CLI now uses the loaded configuration

**Verify loaded configuration:**
```bash
aitbc config show
```

**Expected Output:**
```
coordinator_url: http://127.0.0.1:8011
api_key: None
timeout: 30
config_file: .aitbc.yaml
```

### Step 6: Delete a Profile

Remove an unused profile:

```bash
aitbc config profiles delete old_profile
```

**Expected Output:**
```
Delete profile 'old_profile'? [y/N]: y
Profile 'old_profile' deleted
```

**What happens:**
- Profile file removed from `~/.config/aitbc/profiles/`
- Confirmation prompt before deletion
- No impact on current configuration

---

## 🔧 **Advanced Usage**

### Profile with Different Network Topologies

Create profiles for different network configurations:

```bash
# Local development
aitbc config set coordinator_url http://localhost:8011
aitbc config profiles save local

# Testnet
aitbc config set coordinator_url http://testnet.aitbc.io:8011
aitbc config profiles save testnet

# Mainnet
aitbc config set coordinator_url http://mainnet.aitbc.io:8011
aitbc config profiles save mainnet
```

### Profile for Different Agent Roles

Create profiles specific to agent roles:

```bash
# GPU provider profile
aitbc config set coordinator_url http://gpu-hub.aitbc.io:8011
aitbc config set timeout 120
aitbc config profiles save gpu-provider

# AI job submitter profile
aitbc config set coordinator_url http://ai-hub.aitbc.io:8011
aitbc config set timeout 30
aitbc config profiles save ai-submitter
```

### Manual Profile Editing

Profiles can be manually edited for advanced configurations:

```bash
# Edit profile file directly
nano ~/.config/aitbc/profiles/custom.yaml
```

**Custom profile example:**
```yaml
coordinator_url: http://custom.example.com:8011
timeout: 45
custom_field: custom_value
```

---

## ⚠️ **Important Notes**

### Security Considerations
- **API keys are NOT saved in profiles** - must be set separately
- Profile files are stored in plain text YAML
- Ensure `~/.config/aitbc/` directory has appropriate permissions (600 for secrets)

### Profile Storage Location
- Profiles stored in: `~/.config/aitbc/profiles/`
- Profile file format: `<profile_name>.yaml`
- Config loaded to: `.aitbc.yaml` in current directory

### Profile Limitations
- Only saves `coordinator_url` and `timeout`
- Does not save API keys (security measure)
- Does not save environment variables
- Overwrites current config when loaded

---

## 🐛 **Troubleshooting**

### Profile not found

**Error:**
```
Error: Profile 'my_profile' not found
```

**Solution:**
```bash
# List available profiles
aitbc config profiles list

# Check if profiles directory exists
ls -la ~/.config/aitbc/profiles/
```

### Permission denied

**Error:**
```
Error: Permission denied when saving profile
```

**Solution:**
```bash
# Create profiles directory with correct permissions
mkdir -p ~/.config/aitbc/profiles
chmod 755 ~/.config/aitbc
chmod 755 ~/.config/aitbc/profiles
```

### Config file not created after load

**Error:**
Profile loads but `.aitbc.yaml` not created

**Solution:**
```bash
# Check current directory
pwd

# Ensure write permissions
ls -la .

# Manually create config file
aitbc config profiles load my_profile
```

### Profile contains unexpected values

**Issue:**
Loaded profile has different values than expected

**Solution:**
```bash
# Inspect profile file directly
cat ~/.config/aitbc/profiles/my_profile.yaml

# Re-save profile with current config
aitbc config set coordinator_url http://correct:8011
aitbc config profiles save my_profile
```

---

## 📊 **Testing**

Run the integration test script to verify profile operations:

```bash
# Run pytest tests
cd /opt/aitbc
pytest tests/cli/test_config_profiles.py -v

# Run bash integration test
scripts/testing/test_config_profiles.sh
```

**Expected test output:**
```
tests/cli/test_config_profiles.py::TestConfigProfilesIntegration::test_profiles_save_creates_file PASSED
tests/cli/test_config_profiles.py::TestConfigProfilesIntegration::test_profiles_list_multiple PASSED
tests/cli/test_config_profiles.py::TestConfigProfilesIntegration::test_profiles_load_creates_config PASSED
...
```

---

## 🎓 **Summary**

In this scenario, you learned:
- How to save current configuration as a named profile
- How to list and inspect available profiles
- How to load profiles to switch between environments
- How to delete unused profiles
- Profile storage location and security considerations

**Key Takeaways:**
- Profiles enable quick environment switching
- API keys are not saved in profiles (security)
- Profiles stored in `~/.config/aitbc/profiles/`
- Load overwrites current configuration
- Use profiles for different environments, roles, or network topologies

---

## 🔄 **Related Scenarios**
- **Scenario 01**: [Wallet Basics](./01_wallet_basics.md) - Basic wallet operations
- **Scenario 49**: [Resource Management](./49_resource_management.md) - Resource allocation
- **Scenario 50**: [Workflow Management](./50_workflow_management.md) - Workflow operations
