#!/usr/bin/env python3
"""
AITBC Agent SDK Example: Oracle Agent
Demonstrates how to create an agent that provides external data to the blockchain
"""

import asyncio
import logging
import requests
from typing import Dict, Any, List
from datetime import datetime, UTC
from aitbc_agent_sdk import Agent, AgentConfig
from aitbc_agent_sdk.blockchain import BlockchainClient
from aitbc_agent_sdk.oracle import OracleProvider

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OracleAgentExample:
    """Example oracle agent implementation"""
    
    def __init__(self):
        # Configure agent
        self.config = AgentConfig(
            name="oracle-agent-example",
            blockchain_network="testnet",
            rpc_url="https://testnet-rpc.aitbc.net",
            max_cpu_cores=2,
            max_memory_gb=4
        )
        
        # Initialize components
        self.agent = Agent(self.config)
        self.blockchain_client = BlockchainClient(self.config)
        self.oracle_provider = OracleProvider(self.config)
        
        # Agent state
        self.is_running = False
        self.data_sources = {
            "price": self.get_price_data,
            "weather": self.get_weather_data,
            "sports": self.get_sports_data,
            "news": self.get_news_data
        }
        
    async def start(self):
        """Start the oracle agent"""
        logger.info("Starting oracle agent...")
        
        # Register with network
        agent_address = await self.agent.register_with_network()
        logger.info(f"Agent registered at address: {agent_address}")
        
        # Register oracle services
        await self.register_oracle_services()
        
        # Start data collection loop
        self.is_running = True
        asyncio.create_task(self.data_collection_loop())
        
        logger.info("Oracle agent started successfully!")
        
    async def stop(self):
        """Stop the oracle agent"""
        logger.info("Stopping oracle agent...")
        self.is_running = False
        await self.agent.stop()
        logger.info("Oracle agent stopped")
        
    async def register_oracle_services(self):
        """Register oracle data services with the network"""
        services = [
            {
                "type": "price_oracle",
                "description": "Real-time cryptocurrency and stock prices",
                "update_interval": 60,  # seconds
                "data_types": ["BTC", "ETH", "AAPL", "GOOGL"]
            },
            {
                "type": "weather_oracle",
                "description": "Weather data from major cities",
                "update_interval": 300,  # seconds
                "data_types": ["temperature", "humidity", "pressure"]
            },
            {
                "type": "sports_oracle",
                "description": "Sports scores and match results",
                "update_interval": 600,  # seconds
                "data_types": ["scores", "standings", "statistics"]
            }
        ]
        
        for service in services:
            service_id = await self.blockchain_client.register_oracle_service(service)
            logger.info(f"Registered oracle service: {service['type']} (ID: {service_id})")
            
    async def data_collection_loop(self):
        """Main loop for collecting and submitting oracle data"""
        while self.is_running:
            try:
                # Collect data from all sources
                for data_type, data_func in self.data_sources.items():
                    try:
                        data = await data_func()
                        await self.submit_oracle_data(data_type, data)
                    except Exception as e:
                        logger.error(f"Error collecting {data_type} data: {e}")
                        
                # Sleep before next collection
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in data collection loop: {e}")
                await asyncio.sleep(30)
                
    async def submit_oracle_data(self, data_type: str, data: Dict[str, Any]):
        """Submit oracle data to blockchain"""
        try:
            # Prepare oracle data package
            oracle_data = {
                "data_type": data_type,
                "timestamp": datetime.now(datetime.UTC).isoformat(),
                "data": data,
                "agent_address": self.agent.address,
                "signature": await self.oracle_provider.sign_data(data)
            }
            
            # Submit to blockchain
            tx_hash = await self.blockchain_client.submit_oracle_data(oracle_data)
            logger.info(f"Submitted {data_type} data: {tx_hash}")
            
        except Exception as e:
            logger.error(f"Error submitting {data_type} data: {e}")
            
    async def get_price_data(self) -> Dict[str, Any]:
        """Get real-time price data from external APIs"""
        logger.info("Collecting price data...")
        
        prices = {}
        
        # Get cryptocurrency prices (using CoinGecko API)
        try:
            crypto_response = requests.get(
                "https://api.coingecko.com/api/v1/simple/price",
                params={
                    "ids": "bitcoin,ethereum",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true"
                },
                timeout=10
            )
            
            if crypto_response.status_code == 200:
                crypto_data = crypto_response.json()
                prices["cryptocurrency"] = {
                    "BTC": {
                        "price": crypto_data["bitcoin"]["usd"],
                        "change_24h": crypto_data["bitcoin"]["usd_24h_change"]
                    },
                    "ETH": {
                        "price": crypto_data["ethereum"]["usd"],
                        "change_24h": crypto_data["ethereum"]["usd_24h_change"]
                    }
                }
        except Exception as e:
            logger.error(f"Error getting crypto prices: {e}")
            
        # Get stock prices (using Alpha Vantage API - would need API key)
        try:
            # This is a mock implementation
            prices["stocks"] = {
                "AAPL": {"price": 150.25, "change": "+2.50"},
                "GOOGL": {"price": 2800.75, "change": "-15.25"}
            }
        except Exception as e:
            logger.error(f"Error getting stock prices: {e}")
            
        return prices
        
    async def get_weather_data(self) -> Dict[str, Any]:
        """Get weather data from external APIs"""
        logger.info("Collecting weather data...")
        
        weather = {}
        
        # Major cities (mock implementation)
        cities = ["New York", "London", "Tokyo", "Singapore"]
        
        for city in cities:
            try:
                # This would use a real weather API like OpenWeatherMap
                weather[city] = {
                    "temperature": 20.5,  # Celsius
                    "humidity": 65,      # Percentage
                    "pressure": 1013.25, # hPa
                    "conditions": "Partly Cloudy",
                    "wind_speed": 10.5   # km/h
                }
            except Exception as e:
                logger.error(f"Error getting weather for {city}: {e}")
                
        return weather
        
    async def get_sports_data(self) -> Dict[str, Any]:
        """Get sports data from external APIs"""
        logger.info("Collecting sports data...")
        
        sports = {}
        
        # Mock sports data
        sports["basketball"] = {
            "NBA": {
                "games": [
                    {
                        "teams": ["Lakers", "Warriors"],
                        "score": [105, 98],
                        "status": "Final"
                    },
                    {
                        "teams": ["Celtics", "Heat"],
                        "score": [112, 108],
                        "status": "Final"
                    }
                ],
                "standings": {
                    "Lakers": {"wins": 45, "losses": 20},
                    "Warriors": {"wins": 42, "losses": 23}
                }
            }
        }
        
        return sports
        
    async def get_news_data(self) -> Dict[str, Any]:
        """Get news data from external APIs"""
        logger.info("Collecting news data...")
        
        news = {}
        
        # Mock news data
        news["headlines"] = [
            {
                "title": "AI Technology Breakthrough Announced",
                "source": "Tech News",
                "timestamp": datetime.now(datetime.UTC).isoformat(),
                "sentiment": "positive"
            },
            {
                "title": "Cryptocurrency Market Sees Major Movement",
                "source": "Financial Times",
                "timestamp": datetime.now(datetime.UTC).isoformat(),
                "sentiment": "neutral"
            }
        ]
        
        return news
        
    async def handle_oracle_request(self, request):
        """Handle specific oracle data requests"""
        data_type = request.data_type
        parameters = request.parameters
        
        if data_type in self.data_sources:
            data = await self.data_sources[data_type](**parameters)
            return {
                "success": True,
                "data": data,
                "timestamp": datetime.now(datetime.UTC).isoformat()
            }
        else:
            return {
                "success": False,
                "error": f"Unknown data type: {data_type}"
            }
            
    async def get_agent_status(self) -> Dict[str, Any]:
        """Get current agent status"""
        balance = await self.agent.get_balance()
        
        return {
            "name": self.config.name,
            "address": self.agent.address,
            "is_running": self.is_running,
            "balance": balance,
            "data_sources": list(self.data_sources.keys()),
            "last_update": datetime.now(datetime.UTC).isoformat()
        }

async def main():
    """Main function to run the oracle agent example"""
    # Create agent
    agent = OracleAgentExample()
    
    try:
        # Start agent
        await agent.start()
        
        # Keep running
        while True:
            # Print status every 60 seconds
            status = await agent.get_agent_status()
            logger.info(f"Oracle agent status: {status}")
            await asyncio.sleep(60)
            
    except KeyboardInterrupt:
        logger.info("Shutting down oracle agent...")
        await agent.stop()
    except Exception as e:
        logger.error(f"Oracle agent error: {e}")
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
