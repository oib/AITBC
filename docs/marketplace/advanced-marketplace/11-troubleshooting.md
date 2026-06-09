# Troubleshooting

## Common Issues

### Database Migration Fails
- Check database path in migration script
- Ensure write permissions on database directory
- Use `--reset` flag to recreate tables

### Plugin Hooks Not Executing
- Verify plugin is enabled
- Check hook registration
- Review plugin manager logs

### External Sync Fails
- Verify API credentials
- Check network connectivity
- Review sync status for error messages

## Future Enhancements

### Planned Features
- Real ML model training for pricing
- ~~Advanced auction types (combinatorial, Vickrey)~~ ~~(DEPRECATED v0.4.7)~~
- More sophisticated recommendation algorithms
- Real-time analytics dashboard
- Additional external provider integrations
- Plugin marketplace

### Contributions
Contributions are welcome. Please follow the existing architectural patterns:
- SQLModel for database models
- Session injection for services
- Singleton pattern for shared services
- FastAPI for endpoints
