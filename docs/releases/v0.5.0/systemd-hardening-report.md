# Systemd Hardening Report (v0.5.0)

Date: 2026-06-19
Files modified: 31/31

## Changes per Service

### aitbc-agent-coordinator.service
Path: `/opt/aitbc/apps/agent-coordinator/aitbc-agent-coordinator.service`
Changes:
- + PrivateTmp=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-agent-daemon.service
Path: `/opt/aitbc/apps/agent-daemon/aitbc-agent-daemon.service`
Changes:
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-agent-management.service
Path: `/opt/aitbc/apps/agent-management/aitbc-agent-management.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-ai.service
Path: `/opt/aitbc/apps/ai-engine/aitbc-ai.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-learning.service
Path: `/opt/aitbc/apps/ai-engine/aitbc-learning.service`
Changes:
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-modality-optimization.service
Path: `/opt/aitbc/apps/ai-engine/aitbc-modality-optimization.service`
Changes:
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-multimodal.service
Path: `/opt/aitbc/apps/ai-engine/aitbc-multimodal.service`
Changes:
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-api-gateway.service
Path: `/opt/aitbc/apps/api-gateway/aitbc-api-gateway.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-blockchain-event-bridge.service
Path: `/opt/aitbc/apps/blockchain-event-bridge/aitbc-blockchain-event-bridge.service`
Changes:
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-blockchain-explorer.service
Path: `/opt/aitbc/apps/blockchain-explorer/aitbc-blockchain-explorer.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-blockchain-node.service
Path: `/opt/aitbc/apps/blockchain-node/aitbc-blockchain-node.service`
Changes:
- + PrivateTmp=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-blockchain-p2p.service
Path: `/opt/aitbc/apps/blockchain-node/aitbc-blockchain-p2p.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=strict
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-blockchain-rpc.service
Path: `/opt/aitbc/apps/blockchain-node/aitbc-blockchain-rpc.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-blockchain-sync.service
Path: `/opt/aitbc/apps/blockchain-node/aitbc-blockchain-sync.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-bridge-monitor.service
Path: `/opt/aitbc/apps/bridge-monitor/aitbc-bridge-monitor.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-coordinator-api.service
Path: `/opt/aitbc/apps/coordinator-api/aitbc-coordinator-api.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-edge.service
Path: `/opt/aitbc/apps/edge/aitbc-edge.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-exchange.service
Path: `/opt/aitbc/apps/exchange/aitbc-exchange.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-ffmpeg.service
Path: `/opt/aitbc/apps/ffmpeg/aitbc-ffmpeg.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-governance.service
Path: `/opt/aitbc/apps/governance/aitbc-governance.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-gpu.service
Path: `/opt/aitbc/apps/gpu/aitbc-gpu.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-hermes.service
Path: `/opt/aitbc/apps/hermes/aitbc-hermes.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-marketplace.service
Path: `/opt/aitbc/apps/marketplace/aitbc-marketplace.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-miner.service
Path: `/opt/aitbc/apps/miner/aitbc-miner.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-trading.service
Path: `/opt/aitbc/apps/trading/aitbc-trading.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-wallet.service
Path: `/opt/aitbc/apps/wallet/aitbc-wallet.service`
Changes:
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-whisper.service
Path: `/opt/aitbc/apps/whisper/aitbc-whisper.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + RestartSec=5
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-monitoring.service
Path: `/opt/aitbc/scripts/monitoring/aitbc-monitoring.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-recovery.service
Path: `/opt/aitbc/scripts/systemd/aitbc-recovery.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=full
- + ReadWritePaths=/opt/aitbc /var/lib/aitbc /var/log/aitbc /run/aitbc
- + RestartSec=5
- ~ Restart=on-failure
- + WatchdogSec=30
- + NotifyAccess=all

### aitbc-load-secrets.service
Path: `/opt/aitbc/scripts/utils/aitbc-load-secrets.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=strict

### aitbc-plugin.service
Path: `/opt/aitbc/scripts/utils/aitbc-plugin.service`
Changes:
- + PrivateTmp=yes
- + NoNewPrivileges=yes
- + ProtectHome=yes
- + ProtectKernelTunables=yes
- + ProtectKernelModules=yes
- + ProtectControlGroups=yes
- + RestrictSUIDSGID=yes
- + RestrictRealtime=yes
- + RestrictNamespaces=yes
- + LockPersonality=yes
- + MemoryDenyWriteExecute=yes
- + SystemCallArchitectures=native
- + SystemCallFilter=@system-service
- + ProtectSystem=strict
