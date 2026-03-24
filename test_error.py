import sys
import asyncio
from sqlmodel import Session, create_engine
from app.services.marketplace_enhanced_simple import EnhancedMarketplaceService
from app.database import engine
from app.domain.marketplace import MarketplaceBid

async def run():
    with Session(engine) as session:
        # insert a bid to test amount vs price
        bid = MarketplaceBid(provider="prov", capacity=10, price=1.0)
        session.add(bid)
        session.commit()
        
        service = EnhancedMarketplaceService(session)
        try:
            res = await service.get_marketplace_analytics(period_days=30, metrics=["volume", "revenue"])
            print(res)
        except Exception as e:
            import traceback
            traceback.print_exc()

asyncio.run(run())
