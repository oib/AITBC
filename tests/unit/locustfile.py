"""
Load tests for AITBC Marketplace using Locust
"""

from locust import HttpUser, task, between, events
from locust.env import Environment
from locust.stats import stats_printer, stats_history
import json
import random
import time
from datetime import datetime, timedelta
import gevent
from gevent.pool import Pool


class MarketplaceUser(HttpUser):
    """Simulated marketplace user behavior"""
    
    wait_time = between(1, 3)
    weight = 10
    
    def on_start(self):
        """Called when a user starts"""
        # Initialize user session
        self.user_id = f"user_{random.randint(1000, 9999)}"
        self.tenant_id = f"tenant_{random.randint(100, 999)}"
        self.auth_headers = {
            "X-Tenant-ID": self.tenant_id,
            "Authorization": f"Bearer token_{self.user_id}",
        }
        
        # Create user wallet
        self.create_wallet()
        
        # Track user state
        self.offers_created = []
        self.bids_placed = []
        self.balance = 10000.0  # Starting balance in USDC
    
    def create_wallet(self):
        """Create a wallet for the user"""
        wallet_data = {
            "name": f"Wallet_{self.user_id}",
            "password": f"pass_{self.user_id}",
        }
        
        response = self.client.post(
            "/v1/wallets",
            json=wallet_data,
            headers=self.auth_headers
        )
        
        if response.status_code == 201:
            self.wallet_id = response.json()["id"]
        else:
            self.wallet_id = f"wallet_{self.user_id}"
    
    @task(3)
    def browse_offers(self):
        """Browse marketplace offers"""
        params = {
            "limit": 20,
            "offset": random.randint(0, 100),
            "service_type": random.choice([
                "ai_inference",
                "image_generation",
                "video_processing",
                "data_analytics",
            ]),
        }
        
        with self.client.get(
            "/v1/marketplace/offers",
            params=params,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                offers = data.get("items", [])
                # Simulate user viewing offers
                if offers:
                    self.view_offer_details(random.choice(offers)["id"])
                response.success()
            else:
                response.failure(f"Failed to browse offers: {response.status_code}")
    
    def view_offer_details(self, offer_id):
        """View detailed offer information"""
        with self.client.get(
            f"/v1/marketplace/offers/{offer_id}",
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to view offer: {response.status_code}")
    
    @task(2)
    def create_offer(self):
        """Create a new marketplace offer"""
        if self.balance < 100:
            return  # Insufficient balance
        
        offer_data = {
            "service_type": random.choice([
                "ai_inference",
                "image_generation",
                "video_processing",
                "data_analytics",
                "scientific_computing",
            ]),
            "pricing": {
                "per_hour": round(random.uniform(0.1, 5.0), 2),
                "per_unit": round(random.uniform(0.001, 0.1), 4),
            },
            "capacity": random.randint(10, 1000),
            "requirements": {
                "gpu_memory": random.choice(["8GB", "16GB", "32GB", "64GB"]),
                "cpu_cores": random.randint(4, 32),
                "ram": random.choice(["16GB", "32GB", "64GB", "128GB"]),
            },
            "availability": {
                "start_time": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                "end_time": (datetime.utcnow() + timedelta(days=30)).isoformat(),
            },
        }
        
        with self.client.post(
            "/v1/marketplace/offers",
            json=offer_data,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                offer = response.json()
                self.offers_created.append(offer["id"])
                response.success()
            else:
                response.failure(f"Failed to create offer: {response.status_code}")
    
    @task(3)
    def place_bid(self):
        """Place a bid on an existing offer"""
        # First get available offers
        with self.client.get(
            "/v1/marketplace/offers",
            params={"limit": 10, "status": "active"},
            headers=self.auth_headers,
        ) as response:
            if response.status_code != 200:
                return
            
            offers = response.json().get("items", [])
            if not offers:
                return
            
            # Select random offer
            offer = random.choice(offers)
            
            # Calculate bid amount
            max_price = offer["pricing"]["per_hour"]
            bid_price = round(max_price * random.uniform(0.8, 0.95), 2)
            
            if self.balance < bid_price:
                return
            
            bid_data = {
                "offer_id": offer["id"],
                "quantity": random.randint(1, min(10, offer["capacity"])),
                "max_price": bid_price,
                "duration_hours": random.randint(1, 24),
            }
            
            with self.client.post(
                "/v1/marketplace/bids",
                json=bid_data,
                headers=self.auth_headers,
                catch_response=True,
            ) as response:
                if response.status_code == 201:
                    bid = response.json()
                    self.bids_placed.append(bid["id"])
                    self.balance -= bid_price * bid_data["quantity"]
                    response.success()
                else:
                    response.failure(f"Failed to place bid: {response.status_code}")
    
    @task(2)
    def check_bids(self):
        """Check status of placed bids"""
        if not self.bids_placed:
            return
        
        bid_id = random.choice(self.bids_placed)
        
        with self.client.get(
            f"/v1/marketplace/bids/{bid_id}",
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                bid = response.json()
                
                # If bid is accepted, create transaction
                if bid["status"] == "accepted":
                    self.create_transaction(bid)
                
                response.success()
            else:
                response.failure(f"Failed to check bid: {response.status_code}")
    
    def create_transaction(self, bid):
        """Create transaction for accepted bid"""
        tx_data = {
            "bid_id": bid["id"],
            "payment_method": "wallet",
            "confirmations": True,
        }
        
        with self.client.post(
            "/v1/marketplace/transactions",
            json=tx_data,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
            else:
                response.failure(f"Failed to create transaction: {response.status_code}")
    
    @task(1)
    def get_marketplace_stats(self):
        """Get marketplace statistics"""
        with self.client.get(
            "/v1/marketplace/stats",
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to get stats: {response.status_code}")
    
    @task(1)
    def search_services(self):
        """Search for specific services"""
        query = random.choice([
            "AI inference",
            "image generation",
            "video rendering",
            "data processing",
            "machine learning",
        ])
        
        params = {
            "q": query,
            "limit": 20,
            "min_price": random.uniform(0.1, 1.0),
            "max_price": random.uniform(5.0, 10.0),
        }
        
        with self.client.get(
            "/v1/marketplace/search",
            params=params,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to search: {response.status_code}")


class MarketplaceProvider(HttpUser):
    """Simulated service provider behavior"""
    
    wait_time = between(5, 15)
    weight = 3
    
    def on_start(self):
        """Initialize provider"""
        self.provider_id = f"provider_{random.randint(100, 999)}"
        self.tenant_id = f"tenant_{random.randint(100, 999)}"
        self.auth_headers = {
            "X-Tenant-ID": self.tenant_id,
            "Authorization": f"Bearer provider_token_{self.provider_id}",
        }
        
        # Register as provider
        self.register_provider()
        
        # Provider services
        self.services = []
    
    def register_provider(self):
        """Register as a service provider"""
        provider_data = {
            "name": f"Provider_{self.provider_id}",
            "description": "AI/ML computing services provider",
            "endpoint": f"https://provider-{self.provider_id}.aitbc.io",
            "capabilities": [
                "ai_inference",
                "image_generation",
                "video_processing",
            ],
            "infrastructure": {
                "gpu_count": random.randint(10, 100),
                "cpu_cores": random.randint(100, 1000),
                "memory_gb": random.randint(500, 5000),
            },
        }
        
        self.client.post(
            "/v1/marketplace/providers/register",
            json=provider_data,
            headers=self.auth_headers
        )
    
    @task(4)
    def update_service_status(self):
        """Update status of provider services"""
        if not self.services:
            return
        
        service = random.choice(self.services)
        
        status_data = {
            "service_id": service["id"],
            "status": random.choice(["available", "busy", "maintenance"]),
            "utilization": random.uniform(0.1, 0.9),
            "queue_length": random.randint(0, 20),
        }
        
        with self.client.patch(
            f"/v1/marketplace/services/{service['id']}/status",
            json=status_data,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to update status: {response.status_code}")
    
    @task(3)
    def create_bulk_offers(self):
        """Create multiple offers at once"""
        offers = []
        
        for _ in range(random.randint(5, 15)):
            offer_data = {
                "service_type": random.choice([
                    "ai_inference",
                    "image_generation",
                    "video_processing",
                ]),
                "pricing": {
                    "per_hour": round(random.uniform(0.5, 3.0), 2),
                },
                "capacity": random.randint(50, 500),
                "requirements": {
                    "gpu_memory": "16GB",
                    "cpu_cores": 16,
                },
            }
            offers.append(offer_data)
        
        bulk_data = {"offers": offers}
        
        with self.client.post(
            "/v1/marketplace/offers/bulk",
            json=bulk_data,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                created = response.json().get("created", [])
                self.services.extend(created)
                response.success()
            else:
                response.failure(f"Failed to create bulk offers: {response.status_code}")
    
    @task(2)
    def respond_to_bids(self):
        """Respond to incoming bids"""
        with self.client.get(
            "/v1/marketplace/bids",
            params={"provider_id": self.provider_id, "status": "pending"},
            headers=self.auth_headers,
        ) as response:
            if response.status_code != 200:
                return
            
            bids = response.json().get("items", [])
            if not bids:
                return
            
            # Respond to random bid
            bid = random.choice(bids)
            action = random.choice(["accept", "reject", "counter"])
            
            response_data = {
                "bid_id": bid["id"],
                "action": action,
            }
            
            if action == "counter":
                response_data["counter_price"] = round(
                    bid["max_price"] * random.uniform(1.05, 1.15), 2
                )
            
            with self.client.post(
                "/v1/marketplace/bids/respond",
                json=response_data,
                headers=self.auth_headers,
                catch_response=True,
            ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Failed to respond to bid: {response.status_code}")
    
    @task(1)
    def get_provider_analytics(self):
        """Get provider analytics"""
        with self.client.get(
            f"/v1/marketplace/providers/{self.provider_id}/analytics",
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to get analytics: {response.status_code}")


class MarketplaceAdmin(HttpUser):
    """Simulated admin user behavior"""
    
    wait_time = between(10, 30)
    weight = 1
    
    def on_start(self):
        """Initialize admin"""
        self.auth_headers = {
            "Authorization": "Bearer admin_token_123",
            "X-Admin-Access": "true",
        }
    
    @task(3)
    def monitor_marketplace_health(self):
        """Monitor marketplace health metrics"""
        endpoints = [
            "/v1/marketplace/health",
            "/v1/marketplace/metrics",
            "/v1/marketplace/stats",
        ]
        
        endpoint = random.choice(endpoints)
        
        with self.client.get(
            endpoint,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(2)
    def review_suspicious_activity(self):
        """Review suspicious marketplace activity"""
        with self.client.get(
            "/v1/admin/marketplace/activity",
            params={
                "suspicious_only": True,
                "limit": 50,
            },
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                activities = response.json().get("items", [])
                
                # Take action on suspicious activities
                for activity in activities[:5]:  # Limit to 5 actions
                    self.take_action(activity["id"])
                
                response.success()
            else:
                response.failure(f"Failed to review activity: {response.status_code}")
    
    def take_action(self, activity_id):
        """Take action on suspicious activity"""
        action = random.choice(["warn", "suspend", "investigate"])
        
        with self.client.post(
            f"/v1/admin/marketplace/activity/{activity_id}/action",
            json={"action": action},
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Failed to take action: {response.status_code}")
    
    @task(1)
    def generate_reports(self):
        """Generate marketplace reports"""
        report_types = [
            "daily_summary",
            "weekly_analytics",
            "provider_performance",
            "user_activity",
        ]
        
        report_type = random.choice(report_types)
        
        with self.client.post(
            "/v1/admin/marketplace/reports",
            json={
                "type": report_type,
                "format": "json",
                "email": f"admin@aitbc.io",
            },
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 202:
                response.success()
            else:
                response.failure(f"Failed to generate report: {response.status_code}")


# Custom event handlers for monitoring
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Custom request handler for additional metrics"""
    if exception:
        print(f"Request failed: {name} - {exception}")
    elif response_time > 5000:  # Log slow requests
        print(f"Slow request: {name} - {response_time}ms")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts"""
    print("Starting marketplace load test")
    print(f"Target: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops"""
    print("\nLoad test completed")
    
    # Print summary statistics
    stats = environment.stats
    
    print(f"\nTotal requests: {stats.total.num_requests}")
    print(f"Failures: {stats.total.num_failures}")
    print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    print(f"95th percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
    print(f"Requests per second: {stats.total.current_rps:.2f}")


# Custom load shapes
class GradualLoadShape:
    """Gradually increase load over time"""
    
    def __init__(self, max_users=100, spawn_rate=10):
        self.max_users = max_users
        self.spawn_rate = spawn_rate
    
    def tick(self):
        run_time = time.time() - self.start_time
        
        if run_time < 60:  # First minute: ramp up
            return int(self.spawn_rate * run_time / 60)
        elif run_time < 300:  # Next 4 minutes: maintain
            return self.max_users
        else:  # Last minute: ramp down
            remaining = 360 - run_time
            return int(self.max_users * remaining / 60)


class BurstLoadShape:
    """Burst traffic pattern"""
    
    def __init__(self, burst_size=50, normal_size=10):
        self.burst_size = burst_size
        self.normal_size = normal_size
    
    def tick(self):
        run_time = time.time() - self.start_time
        
        # Burst every 30 seconds for 10 seconds
        if int(run_time) % 30 < 10:
            return self.burst_size
        else:
            return self.normal_size


# Performance monitoring
class PerformanceMonitor:
    """Monitor performance during load test"""
    
    def __init__(self):
        self.metrics = {
            "response_times": [],
            "error_rates": [],
            "throughput": [],
        }
    
    def record_request(self, response_time, success):
        """Record request metrics"""
        self.metrics["response_times"].append(response_time)
        self.metrics["error_rates"].append(0 if success else 1)
    
    def get_summary(self):
        """Get performance summary"""
        if not self.metrics["response_times"]:
            return {}
        
        return {
            "avg_response_time": sum(self.metrics["response_times"]) / len(self.metrics["response_times"]),
            "max_response_time": max(self.metrics["response_times"]),
            "error_rate": sum(self.metrics["error_rates"]) / len(self.metrics["error_rates"]),
            "total_requests": len(self.metrics["response_times"]),
        }


# Test configuration
if __name__ == "__main__":
    # Setup environment
    env = Environment(user_classes=[MarketplaceUser, MarketplaceProvider, MarketplaceAdmin])
    
    # Create performance monitor
    monitor = PerformanceMonitor()
    
    # Setup host
    env.host = "http://localhost:8001"
    
    # Setup load shape
    env.create_local_runner()
    
    # Start web UI for monitoring
    env.create_web_ui("127.0.0.1", 8089)
    
    # Start the load test
    print("Starting marketplace load test...")
    print("Web UI available at: http://127.0.0.1:8089")
    
    # Run for 6 minutes
    env.runner.start(100, spawn_rate=10)
    gevent.spawn_later(360, env.runner.stop)
    
    # Print stats
    gevent.spawn(stats_printer(env.stats))
    
    # Wait for test to complete
    env.runner.greenlet.join()
