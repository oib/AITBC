# AITBC Website

This folder contains the complete AITBC platform website, updated to reflect the current production-ready state.

## Files Structure

- `index.html` - Main homepage with platform components and achievements
- `docs/` - Documentation folder (moved to container docs directory)
  - `docs-index.html` - Documentation landing page
  - `docs-miners.html` - Miner-specific documentation
  - `docs-clients.html` - Client-specific documentation  
  - `docs-developers.html` - Developer-specific documentation
- `documentation.html` - Legacy full documentation page
- `full-documentation.html` - Comprehensive technical documentation
- `404.html` - Custom error page
- `aitbc-proxy.conf` - Nginx reverse proxy configuration

## Deployment

The website is deployed in the AITBC Incus container at:
- Container IP: 10.1.223.93
- Domain: aitbc.bubuit.net
- Documentation: aitbc.bubuit.net/docs/

## Key Updates Made

1. **Production-Ready Messaging**: Changed from concept to actual platform state
2. **Platform Components**: Showcases 7 live components (Blockchain Node, Coordinator API, Marketplace, Explorer, Wallet, Pool Hub, GPU Services)
3. **Achievements Section**: Real metrics (30+ GPU services, Stages 1-7 complete)
4. **Updated Roadmap**: Reflects current development progress
5. **Documentation Structure**: Split by audience (Miners, Clients, Developers)

## Next Steps

- Configure SSL certificate for HTTPS
- Set up DNS for full domain accessibility
- Consider adding live network statistics dashboard
