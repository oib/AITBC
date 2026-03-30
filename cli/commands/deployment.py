"""Production deployment guidance for AITBC CLI"""

import click
from utils import output, error, success

@click.group()
def deploy():
    """Production deployment guidance and setup"""
    pass

@deploy.command()
@click.option('--service', default='all', help='Service to deploy (all, coordinator, blockchain, marketplace)')
@click.option('--environment', default='production', help='Deployment environment')
def setup(service, environment):
    """Get deployment setup instructions"""
    output(f"🚀 {environment.title()} Deployment Setup for {service.title()}", None)
    
    instructions = {
        'coordinator': [
            "1. Install dependencies: pip install -r requirements.txt",
            "2. Set environment variables in .env file",
            "3. Run: python -m coordinator.main",
            "4. Configure nginx reverse proxy",
            "5. Set up SSL certificates"
        ],
        'blockchain': [
            "1. Install blockchain node dependencies",
            "2. Initialize genesis block: aitbc genesis init",
            "3. Start node: python -m blockchain.node",
            "4. Configure peer connections",
            "5. Enable mining if needed"
        ],
        'marketplace': [
            "1. Install marketplace dependencies",
            "2. Set up database: postgresql-setup.sh",
            "3. Run migrations: python -m marketplace.migrate",
            "4. Start service: python -m marketplace.main",
            "5. Configure GPU mining nodes"
        ],
        'all': [
            "📋 Complete AITBC Platform Deployment:",
            "",
            "1. Prerequisites:",
            "   - Python 3.13+",
            "   - PostgreSQL 14+", 
            "   - Redis 6+",
            "   - Docker (optional)",
            "",
            "2. Environment Setup:",
            "   - Copy .env.example to .env",
            "   - Configure database URLs",
            "   - Set API keys and secrets",
            "",
            "3. Database Setup:",
            "   - createdb aitbc",
            "   - Run migrations: python manage.py migrate",
            "",
            "4. Service Deployment:",
            "   - Coordinator: python -m coordinator.main",
            "   - Blockchain: python -m blockchain.node", 
            "   - Marketplace: python -m marketplace.main",
            "",
            "5. Frontend Setup:",
            "   - npm install",
            "   - npm run build",
            "   - Configure web server"
        ]
    }
    
    for step in instructions.get(service, instructions['all']):
        output(step, None)
    
    output(f"\n💡 For detailed deployment guides, see: docs/deployment/{environment}.md", None)

@deploy.command()
@click.option('--service', help='Service to check')
def status(service):
    """Check deployment status"""
    output(f"📊 Deployment Status Check for {service or 'All Services'}", None)
    
    checks = [
        "Coordinator API: http://localhost:8000/health",
        "Blockchain Node: http://localhost:8006/status", 
        "Marketplace: http://localhost:8002/health",
        "Wallet Service: http://localhost:8003/status"
    ]
    
    for check in checks:
        output(f"   • {check}", None)
    
    output("\n💡 Use curl or browser to check each endpoint", None)
