#!/usr/bin/env python3
"""
Staking Test Data Generator
Generates realistic test data scenarios for staking tests
"""

import json
import random
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Any

# Performance tiers and their properties
PERFORMANCE_TIERS = {
    "BRONZE": {
        "multiplier": 1.0,
        "min_accuracy": 70.0,
        "max_accuracy": 79.9,
        "min_submissions": 5,
        "success_rate_range": (0.70, 0.80)
    },
    "SILVER": {
        "multiplier": 1.25,
        "min_accuracy": 80.0,
        "max_accuracy": 89.9,
        "min_submissions": 10,
        "success_rate_range": (0.80, 0.90)
    },
    "GOLD": {
        "multiplier": 1.5,
        "min_accuracy": 90.0,
        "max_accuracy": 94.9,
        "min_submissions": 20,
        "success_rate_range": (0.90, 0.95)
    },
    "PLATINUM": {
        "multiplier": 2.0,
        "min_accuracy": 95.0,
        "max_accuracy": 97.9,
        "min_submissions": 50,
        "success_rate_range": (0.95, 0.98)
    },
    "DIAMOND": {
        "multiplier": 3.0,
        "min_accuracy": 98.0,
        "max_accuracy": 100.0,
        "min_submissions": 100,
        "success_rate_range": (0.98, 1.00)
    }
}

# Lock period multipliers
LOCK_PERIOD_MULTIPLIERS = {
    "short": {"days": 7, "multiplier": 1.0},
    "medium": {"days": 30, "multiplier": 1.1},
    "long": {"days": 90, "multiplier": 1.5},
    "extended": {"days": 365, "multiplier": 2.0}
}

# Stake amount ranges
STAKE_AMOUNTS = {
    "minimum": 100.0,
    "small": 1000.0,
    "medium": 10000.0,
    "large": 50000.0,
    "maximum": 100000.0
}


def generate_agent_wallet() -> str:
    """Generate a random agent wallet address"""
    return f"0x{''.join(random.choices('0123456789abcdef', k=40))}"


def generate_staker_address() -> str:
    """Generate a random staker address"""
    return f"ait1{''.join(random.choices('0123456789abcdef', k=40))}"


def generate_agent_metrics(tier: str = "GOLD") -> Dict[str, Any]:
    """Generate realistic agent metrics for a given tier"""
    tier_config = PERFORMANCE_TIERS[tier]
    
    total_submissions = random.randint(tier_config["min_submissions"], tier_config["min_submissions"] * 3)
    success_rate = random.uniform(*tier_config["success_rate_range"])
    successful_submissions = int(total_submissions * success_rate)
    
    return {
        "agent_wallet": generate_agent_wallet(),
        "total_submissions": total_submissions,
        "successful_submissions": successful_submissions,
        "average_accuracy": random.uniform(tier_config["min_accuracy"], tier_config["max_accuracy"]),
        "current_tier": tier,
        "tier_score": random.uniform(60.0, 95.0),
        "total_staked": 0.0,
        "staker_count": 0,
        "total_rewards_distributed": 0.0,
        "last_update_time": datetime.now(datetime.UTC).isoformat()
    }


def calculate_expected_apy(tier: str, lock_period_days: int, base_apy: float = 5.0) -> float:
    """Calculate expected APY based on tier and lock period"""
    tier_multiplier = PERFORMANCE_TIERS[tier]["multiplier"]
    
    if lock_period_days >= 365:
        lock_multiplier = 2.0
    elif lock_period_days >= 90:
        lock_multiplier = 1.5
    elif lock_period_days >= 30:
        lock_multiplier = 1.1
    else:
        lock_multiplier = 1.0
    
    apy = base_apy * tier_multiplier * lock_multiplier
    return min(apy, 20.0)  # Cap at 20%


def generate_stake_data(
    agent_wallet: str,
    staker_address: str,
    tier: str = "GOLD",
    amount_category: str = "medium",
    lock_period_category: str = "medium",
    auto_compound: bool = False
) -> Dict[str, Any]:
    """Generate realistic stake data"""
    amount = STAKE_AMOUNTS[amount_category]
    lock_period_days = LOCK_PERIOD_MULTIPLIERS[lock_period_category]["days"]
    expected_apy = calculate_expected_apy(tier, lock_period_days)
    
    start_time = datetime.now(datetime.UTC)
    end_time = start_time + timedelta(days=lock_period_days)
    
    return {
        "stake_id": f"stake_{random.randint(100000, 999999)}",
        "staker_address": staker_address,
        "agent_wallet": agent_wallet,
        "amount": amount,
        "lock_period": lock_period_days,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "status": "ACTIVE",
        "accumulated_rewards": 0.0,
        "last_reward_time": start_time.isoformat(),
        "current_apy": expected_apy,
        "agent_tier": tier,
        "performance_multiplier": PERFORMANCE_TIERS[tier]["multiplier"],
        "auto_compound": auto_compound
    }


def generate_staking_pool(agent_wallet: str, total_staked: float) -> Dict[str, Any]:
    """Generate staking pool data"""
    return {
        "agent_wallet": agent_wallet,
        "total_staked": total_staked,
        "total_rewards": 0.0,
        "pool_apy": 5.0,
        "staker_count": 0,
        "active_stakers": [],
        "last_distribution_time": datetime.now(datetime.UTC).isoformat(),
        "distribution_frequency": 1
    }


def generate_test_scenario(num_agents: int = 5, num_stakes_per_agent: int = 3) -> Dict[str, Any]:
    """Generate a complete test scenario with multiple agents and stakes"""
    scenario = {
        "scenario_id": f"scenario_{random.randint(1000, 9999)}",
        "generated_at": datetime.now(datetime.UTC).isoformat(),
        "agents": [],
        "stakes": [],
        "pools": []
    }
    
    # Generate agents with different tiers
    tier_distribution = ["BRONZE", "SILVER", "GOLD", "GOLD", "PLATINUM"]
    for i in range(num_agents):
        tier = tier_distribution[i % len(tier_distribution)]
        agent_metrics = generate_agent_metrics(tier)
        scenario["agents"].append(agent_metrics)
        
        # Generate staking pool
        pool = generate_staking_pool(agent_metrics["agent_wallet"], 0.0)
        scenario["pools"].append(pool)
        
        # Generate stakes for this agent
        for j in range(num_stakes_per_agent):
            staker_address = generate_staker_address()
            amount_category = random.choice(["small", "medium", "large"])
            lock_period_category = random.choice(["short", "medium", "long", "extended"])
            auto_compound = random.choice([True, False])
            
            stake = generate_stake_data(
                agent_wallet=agent_metrics["agent_wallet"],
                staker_address=staker_address,
                tier=tier,
                amount_category=amount_category,
                lock_period_category=lock_period_category,
                auto_compound=auto_compound
            )
            scenario["stakes"].append(stake)
            
            # Update pool totals
            pool["total_staked"] += stake["amount"]
            pool["staker_count"] += 1
            if staker_address not in pool["active_stakers"]:
                pool["active_stakers"].append(staker_address)
    
    return scenario


def generate_edge_case_scenarios() -> List[Dict[str, Any]]:
    """Generate edge case test scenarios"""
    scenarios = []
    
    # Scenario 1: Minimum stake amount
    scenarios.append({
        "name": "Minimum Stake Amount",
        "description": "Test with minimum valid stake amount (100 AIT)",
        "stake": generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            amount_category="minimum",
            lock_period_category="medium"
        )
    })
    
    # Scenario 2: Maximum stake amount
    scenarios.append({
        "name": "Maximum Stake Amount",
        "description": "Test with maximum valid stake amount (100,000 AIT)",
        "stake": generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            amount_category="maximum",
            lock_period_category="medium"
        )
    })
    
    # Scenario 3: Short lock period
    scenarios.append({
        "name": "Short Lock Period",
        "description": "Test with minimum lock period (7 days)",
        "stake": generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            lock_period_category="short"
        )
    })
    
    # Scenario 4: Extended lock period
    scenarios.append({
        "name": "Extended Lock Period",
        "description": "Test with maximum lock period (365 days)",
        "stake": generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            lock_period_category="extended"
        )
    })
    
    # Scenario 5: Diamond tier with extended lock
    scenarios.append({
        "name": "Diamond Tier Extended Lock",
        "description": "Test maximum APY scenario (Diamond tier + 365 days)",
        "stake": generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            tier="DIAMOND",
            lock_period_category="extended"
        )
    })
    
    # Scenario 6: Auto-compound enabled
    scenarios.append({
        "name": "Auto-Compound Enabled",
        "description": "Test stake with auto-compound enabled",
        "stake": generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            auto_compound=True
        )
    })
    
    return scenarios


def generate_unbonding_scenarios() -> List[Dict[str, Any]]:
    """Generate unbonding test scenarios"""
    scenarios = []
    
    # Scenario 1: Unbonding before lock period (should fail)
    scenarios.append({
        "name": "Unbond Before Lock Period",
        "description": "Test unbonding before lock period ends (should fail)",
        "stake": generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            lock_period_category="medium"
        ),
        "action": "unbond",
        "expected_result": "failure",
        "expected_error": "Lock period has not ended"
    })
    
    # Scenario 2: Unbonding after lock period (should succeed)
    stake = generate_stake_data(
        generate_agent_wallet(),
        generate_staker_address(),
        lock_period_category="medium"
    )
    stake["end_time"] = (datetime.now(datetime.UTC) - timedelta(days=1)).isoformat()
    scenarios.append({
        "name": "Unbond After Lock Period",
        "description": "Test unbonding after lock period ends (should succeed)",
        "stake": stake,
        "action": "unbond",
        "expected_result": "success",
        "expected_status": "UNBONDING"
    })
    
    # Scenario 3: Complete unbonding with penalty
    stake = generate_stake_data(
        generate_agent_wallet(),
        generate_staker_address(),
        lock_period_category="medium"
    )
    stake["end_time"] = (datetime.now(datetime.UTC) - timedelta(days=1)).isoformat()
    stake["status"] = "UNBONDING"
    stake["unbonding_time"] = (datetime.now(datetime.UTC) - timedelta(days=10)).isoformat()
    scenarios.append({
        "name": "Complete Unbonding With Penalty",
        "description": "Test completing unbonding within 30 days (10% penalty)",
        "stake": stake,
        "action": "complete_unbonding",
        "expected_result": "success",
        "expected_penalty": 0.10
    })
    
    # Scenario 4: Complete unbonding without penalty
    stake = generate_stake_data(
        generate_agent_wallet(),
        generate_staker_address(),
        lock_period_category="medium"
    )
    stake["end_time"] = (datetime.now(datetime.UTC) - timedelta(days=1)).isoformat()
    stake["status"] = "UNBONDING"
    stake["unbonding_time"] = (datetime.now(datetime.UTC) - timedelta(days=35)).isoformat()
    scenarios.append({
        "name": "Complete Unbonding No Penalty",
        "description": "Test completing unbonding after 30 days (no penalty)",
        "stake": stake,
        "action": "complete_unbonding",
        "expected_result": "success",
        "expected_penalty": 0.0
    })
    
    return scenarios


def save_test_data(data: Dict[str, Any], output_file: str):
    """Save test data to JSON file"""
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Test data saved to: {output_file}")


def main():
    """Main function to generate test data"""
    print("🔧 Generating Staking Test Data")
    print("=" * 50)
    
    # Generate comprehensive test scenario
    print("\nGenerating comprehensive test scenario...")
    scenario = generate_test_scenario(num_agents=5, num_stakes_per_agent=3)
    save_test_data(scenario, "/var/lib/aitbc/data/test_staking_scenario.json")
    
    # Generate edge case scenarios
    print("\nGenerating edge case scenarios...")
    edge_cases = generate_edge_case_scenarios()
    save_test_data(edge_cases, "/var/lib/aitbc/data/test_staking_edge_cases.json")
    
    # Generate unbonding scenarios
    print("\nGenerating unbonding scenarios...")
    unbonding_scenarios = generate_unbonding_scenarios()
    save_test_data(unbonding_scenarios, "/var/lib/aitbc/data/test_staking_unbonding.json")
    
    # Generate individual test data files
    print("\nGenerating individual test data files...")
    
    # Agent metrics for each tier
    for tier in PERFORMANCE_TIERS.keys():
        metrics = generate_agent_metrics(tier)
        save_test_data(metrics, f"/var/lib/aitbc/data/test_agent_metrics_{tier.lower()}.json")
    
    # Stake data for each amount category
    for amount_cat in STAKE_AMOUNTS.keys():
        stake = generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            amount_category=amount_cat
        )
        save_test_data(stake, f"/var/lib/aitbc/data/test_stake_{amount_cat}.json")
    
    # Stake data for each lock period
    for lock_cat in LOCK_PERIOD_MULTIPLIERS.keys():
        stake = generate_stake_data(
            generate_agent_wallet(),
            generate_staker_address(),
            lock_period_category=lock_cat
        )
        save_test_data(stake, f"/var/lib/aitbc/data/test_stake_lock_{lock_cat}.json")
    
    print("\n✅ Test data generation complete!")
    print("\nGenerated files:")
    print("  - /var/lib/aitbc/data/test_staking_scenario.json")
    print("  - /var/lib/aitbc/data/test_staking_edge_cases.json")
    print("  - /var/lib/aitbc/data/test_staking_unbonding.json")
    print("  - Agent metrics for each tier")
    print("  - Stake data for each amount category")
    print("  - Stake data for each lock period")


if __name__ == "__main__":
    main()
