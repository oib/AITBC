# AITBC Miner Dashboard

A real-time monitoring dashboard for GPU mining operations in the AITBC network.

## Features

### 🎯 GPU Monitoring
- Real-time GPU utilization
- Temperature monitoring
- Power consumption tracking
- Memory usage display
- Performance state indicators

### ⛏️ Mining Operations
- Active job tracking
- Job progress visualization
- Success/failure statistics
- Average job time metrics

### 📊 Performance Analytics
- GPU utilization charts (last hour)
- Hash rate performance tracking
- Mining statistics dashboard
- Service capability overview

### 🔧 Available Services
- GPU Computing (CUDA cores)
- Parallel Processing (multi-threaded)
- Hash Generation (proof-of-work)
- AI Model Training (ML operations)
- Blockchain Validation
- Data Processing

## Quick Start

### 1. Deploy the Dashboard
```bash
cd /home/oib/windsurf/aitbc/apps/miner-dashboard
sudo ./deploy.sh
```

### 2. Access the Dashboard
- Local: http://localhost:8080
- Remote: http://[SERVER_IP]:8080

### 3. Monitor Mining
- View real-time GPU status
- Track active mining jobs
- Monitor hash rates
- Check service availability

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Browser   │◄──►│ Dashboard Server │◄──►│  GPU Miner      │
│  (Dashboard UI) │    │   (Port 8080)    │    │  (Background)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  nvidia-smi     │
                       │  (GPU Metrics)  │
                       └─────────────────┘
```

## API Endpoints

- `GET /api/gpu-status` - Real-time GPU metrics
- `GET /api/mining-jobs` - Active mining jobs
- `GET /api/statistics` - Mining statistics
- `GET /api/services` - Available services

## Service Management

### Start Services
```bash
sudo systemctl start aitbc-miner
sudo systemctl start aitbc-miner-dashboard
```

### Stop Services
```bash
sudo systemctl stop aitbc-miner
sudo systemctl stop aitbc-miner-dashboard
```

### View Logs
```bash
sudo journalctl -u aitbc-miner -f
sudo journalctl -u aitbc-miner-dashboard -f
```

## GPU Requirements

- NVIDIA GPU with CUDA support
- nvidia-smi utility installed
- GPU memory: 4GB+ recommended
- CUDA drivers up to date

## Troubleshooting

### Dashboard Not Loading
```bash
# Check service status
sudo systemctl status aitbc-miner-dashboard

# Check logs
sudo journalctl -u aitbc-miner-dashboard -n 50
```

### GPU Not Detected
```bash
# Verify nvidia-smi
nvidia-smi

# Check GPU permissions
ls -l /dev/nvidia*
```

### No Mining Jobs
```bash
# Check miner service
sudo systemctl status aitbc-miner

# Restart if needed
sudo systemctl restart aitbc-miner
```

## Configuration

### GPU Monitoring
The dashboard automatically detects NVIDIA GPUs using nvidia-smi.

### Mining Performance
Adjust mining parameters in `miner_service.py`:
- Job frequency
- Processing duration
- Success rates

### Dashboard Port
Change port in `dashboard_server.py` (default: 8080).

## Security

- Dashboard runs on localhost by default
- No external database required
- Minimal dependencies
- Read-only GPU monitoring

## Development

### Extend Services
Add new mining services in the `get_services()` method.

### Customize UI
Modify `index.html` to change the dashboard appearance.

### Add Metrics
Extend the API with new endpoints for additional metrics.

## License

AITBC Project - Internal Use Only
