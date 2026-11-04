# Management Commands

## Service Health

```bash
# Check service health
/opt/aitbc/scripts/monitoring/health_check.sh
```

## Service Control

```bash
# Check status / start all services
systemctl status 'aitbc-*'
systemctl start aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p aitbc-exchange aitbc-market aitbc-trading aitbc-wallet

# Systemd control
systemctl status aitbc-wallet
systemctl restart aitbc-coordinator-api
systemctl stop aitbc-exchange
```

## Logs

```bash
# View logs (services log to the journal)
journalctl -f -u aitbc-wallet
journalctl -f -u aitbc-coordinator-api
journalctl -f -u aitbc-exchange
```

## Keystore

```bash
# Check keystore
ls -la /var/lib/aitbc/keystore/
```

## See Also

- [Service Endpoints](service-endpoints.md)
- [Troubleshooting](troubleshooting.md)
