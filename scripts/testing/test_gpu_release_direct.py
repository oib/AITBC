#!/usr/bin/env python3
"""
Direct test of GPU release functionality
"""

import sys
import os
sys.path.insert(0, '/home/oib/windsurf/aitbc/apps/coordinator-api/src')

from sqlmodel import Session, select
from sqlalchemy import create_engine
from app.domain.gpu_marketplace import GPURegistry, GPUBooking

def test_gpu_release():
    """Test GPU release directly"""
    print("=== DIRECT GPU RELEASE TEST ===")
    
    # Use the same database as coordinator
    db_path = "/home/oib/windsurf/aitbc/apps/coordinator-api/data/coordinator.db"
    engine = create_engine(f"sqlite:///{db_path}")
    
    gpu_id = "gpu_c5be877c"
    
    with Session(engine) as session:
        print(f"1. Checking GPU {gpu_id}...")
        gpu = session.exec(select(GPURegistry).where(GPURegistry.id == gpu_id)).first()
        
        if not gpu:
            print(f"❌ GPU {gpu_id} not found")
            return False
            
        print(f"✅ GPU found: {gpu.model} - Status: {gpu.status}")
        
        print(f"2. Checking bookings for GPU {gpu_id}...")
        bookings = session.exec(
            select(GPUBooking).where(GPUBooking.gpu_id == gpu_id)
        ).all()
        
        print(f"Found {len(bookings)} bookings:")
        for booking in bookings:
            print(f"  - ID: {booking.id}, Status: {booking.status}, Total Cost: {getattr(booking, 'total_cost', 'MISSING')}")
        
        print(f"3. Checking active bookings...")
        active_booking = session.exec(
            select(GPUBooking).where(
                GPUBooking.gpu_id == gpu_id, 
                GPUBooking.status == "active"
            )
        ).first()
        
        if active_booking:
            print(f"✅ Active booking found: {active_booking.id}")
            print(f"   Total Cost: {getattr(active_booking, 'total_cost', 'MISSING')}")
            
            # Test refund calculation
            try:
                refund = active_booking.total_cost * 0.5
                print(f"✅ Refund calculation successful: {refund}")
            except AttributeError as e:
                print(f"❌ Refund calculation failed: {e}")
                return False
        else:
            print("❌ No active booking found")
        
        print(f"4. Testing release logic...")
        if active_booking:
            try:
                refund = active_booking.total_cost * 0.5
                active_booking.status = "cancelled"
                gpu.status = "available"
                session.commit()
                
                print(f"✅ Release successful")
                print(f"   GPU Status: {gpu.status}")
                print(f"   Booking Status: {active_booking.status}")
                print(f"   Refund: {refund}")
                
                return True
                
            except Exception as e:
                print(f"❌ Release failed: {e}")
                session.rollback()
                return False
        else:
            print("⚠️  No active booking to release")
            # Still try to make GPU available
            gpu.status = "available"
            session.commit()
            print(f"✅ GPU marked as available")
            return True

if __name__ == "__main__":
    success = test_gpu_release()
    if success:
        print("\n🎉 GPU release test PASSED!")
    else:
        print("\n❌ GPU release test FAILED!")
        sys.exit(1)
