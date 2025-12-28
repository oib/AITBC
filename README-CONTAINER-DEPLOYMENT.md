# AITBC Container Deployment Guide

## Prerequisites

Your user needs to be in the `incus` group to manage containers.

## Setup Steps

1. **Add your user to the incus group:**
```bash
sudo usermod -aG incus $USER
```

2. **Log out and log back in** for the group changes to take effect.

3. **Verify access:**
```bash
incus list
```

## Deploy AITBC Services

Once you have incus access, run the deployment script:

```bash
python /home/oib/windsurf/aitbc/container-deploy.py
```

## Service URLs (after deployment)

- **Marketplace UI**: http://10.1.223.93:3001
- **Trade Exchange**: http://10.1.223.93:3002
- **Coordinator API**: http://10.1.223.93:8000
- **Blockchain RPC**: http://10.1.223.93:9080

## Managing Services

### Check running services in container:
```bash
incus exec aitbc -- ps aux | grep python
```

### View logs:
```bash
incus exec aitbc -- journalctl -u aitbc-coordinator -f
```

### Restart services:
```bash
incus exec aitbc -- pkill -f uvicorn
incus exec aitbc -- /home/oib/start_aitbc.sh
```

### Stop all services:
```bash
incus exec aitbc -- pkill -f "uvicorn\|server.py"
```

## Configuration Files

Services are started from `/home/oib/aitbc/start_aitbc.sh` inside the container.

## Firewall

Make sure the following ports are open on the container host:
- 3001 (Marketplace UI)
- 3002 (Trade Exchange)
- 8000 (Coordinator API)
- 9080 (Blockchain RPC)

## Public Access

To make services publicly accessible, configure your router or firewall to forward these ports to the container IP (10.1.223.93).
