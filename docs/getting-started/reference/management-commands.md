# Management Commands

## Service Health

```bash
# Check service health
/opt/aitbc/scripts/monitoring/health_check.sh
```

## Service Control

```bash
# Restart all services
/opt/aitbc/start-services.sh

# Systemd control
systemctl status aitbc-wallet
systemctl restart aitbc-coordinator-api
systemctl stop aitbc-exchange-api
```

## Logs

```bash
# View logs (new standard locations)
tail -f /var/lib/aitbc/logs/aitbc-wallet.log
tail -f /var/lib/aitbc/logs/aitbc-coordinator.log
tail -f /var/lib/aitbc/logs/aitbc-exchange.log
```

## Keystore

```bash
# Check keystore
ls -la /var/lib/aitbc/keystore/
```

## See Also

- [Service Endpoints](service-endpoints.md)
- [Troubleshooting](troubleshooting.md)
