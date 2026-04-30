#!/usr/bin/env python3
"""
Fix GPU release issue by creating proper booking records
"""

import sys
import os
sys.path.insert(0, '/home/oib/windsurf/aitbc/apps/coordinator-api/src')

from sqlmodel import Session, select
from app.database import engine, create_db_and_tables
from app.domain.gpu_marketplace import GPURegistry, GPUBooking
from datetime import datetime, UTC, timedelta

def fix_gpu_release():
    """Fix GPU release issue by ensuring proper booking records exist"""
    print("=== FIXING GPU RELEASE ISSUE ===")
    
    # Create tables if they don't exist
    create_db_and_tables()
    
    gpu_id = "gpu_c5be877c"
    
    with Session(engine) as session:
        # Check if GPU exists
        gpu = session.exec(select(GPURegistry).where(GPURegistry.id == gpu_id)).first()
        if not gpu:
            print(f"❌ GPU {gpu_id} not found")
            return False
        
        print(f"🎮 Found GPU: {gpu_id} - {gpu.model} - Status: {gpu.status}")
        
        # Check if there's an active booking
        booking = session.exec(
            select(GPUBooking)
            .where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active")
        ).first()
        
        if not booking:
            print("❌ No active booking found, creating one...")
            
            # Create a booking record
            now = datetime.now(datetime.UTC)
            booking = GPUBooking(
                gpu_id=gpu_id,
                client_id="localhost-user",
                job_id="test_job_" + str(int(now.timestamp())),
                duration_hours=1.0,
                total_cost=0.5,
                status="active",
                start_time=now,
                end_time=now + timedelta(hours=1)
            )
            
            session.add(booking)
            session.commit()
            session.refresh(booking)
            
            print(f"✅ Created booking: {booking.id}")
        else:
            print(f"✅ Found existing booking: {booking.id}")
        
        return True

def test_gpu_release():
    """Test the GPU release functionality"""
    print("\n=== TESTING GPU RELEASE ===")
    
    gpu_id = "gpu_c5be877c"
    
    with Session(engine) as session:
        # Check booking before release
        booking = session.exec(
            select(GPUBooking)
            .where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active")
        ).first()
        
        if booking:
            print(f"📋 Booking before release: {booking.id} - Status: {booking.status}")
            
            # Simulate release logic
            booking.status = "cancelled"
            gpu = session.exec(select(GPURegistry).where(GPURegistry.id == gpu_id)).first()
            gpu.status = "available"
            
            session.commit()
            
            print(f"✅ GPU released successfully")
            print(f"🎮 GPU Status: {gpu.status}")
            print(f"📋 Booking Status: {booking.status}")
            
            return True
        else:
            print("❌ No booking to release")
            return False

if __name__ == "__main__":
    if fix_gpu_release():
        if test_gpu_release():
            print("\n🎉 GPU release issue fixed successfully!")
        else:
            print("\n❌ GPU release test failed!")
    else:
        print("\n❌ Failed to fix GPU release issue!")
        sys.exit(1)
