# Management Commands

## Service Health

```bash
# Check service health
/opt/aitbc/scripts/monitoring/health_check.sh
```

## Service Control

```bash
# Check status / start all services
/opt/aitbc/scripts/service-management/manage-services.sh status
/opt/aitbc/scripts/service-management/manage-services.sh start

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
