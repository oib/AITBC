# Production Deployment Checklist

For production deployment, ensure the following items are completed:

## Configuration

1. Configure `/etc/aitbc/blockchain.env` with proper environment variables
2. Configure `/etc/aitbc/node.env` with node-specific settings

## Security

3. Set up reverse proxy (nginx)
4. Configure SSL certificates manually outside `scripts/deployment/setup.sh`

## Operations

5. Set up log rotation
6. Configure monitoring and alerts
7. Use proper database setup (PostgreSQL/Redis)

## See Also

- [Service Endpoints](service-endpoints.md)
- [Management Commands](management-commands.md)
- [Security Notes](security-notes.md)
