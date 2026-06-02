#!/usr/bin/env python3
"""
Migration script to create Hermes autonomy feature database tables.
Run this script to create the tables in the database.
"""

import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apps/coordinator-api/src'))

from app.storage.db_pg import Base, engine
from app.models.hermes import (
    DecisionModel,
    VoteModel,
    HealthCheckModel,
    ErrorReportModel,
    RecoveryResultModel,
    ResourceModel,
    ResourceAllocationModel,
    PricingAdjustmentModel,
)


def create_tables():
    """Create all Hermes database tables."""
    print("Creating Hermes database tables...")
    
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ All Hermes tables created successfully")
        print("\nCreated tables:")
        print("  - hermes_decisions")
        print("  - hermes_votes")
        print("  - hermes_health_checks")
        print("  - hermes_error_reports")
        print("  - hermes_recovery_results")
        print("  - hermes_resources")
        print("  - hermes_resource_allocations")
        print("  - hermes_pricing_adjustments")
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        sys.exit(1)


if __name__ == "__main__":
    create_tables()
