#!/usr/bin/env python3
"""
Direct database cleanup for fake GPU entries
"""

import sys
import os
sys.path.insert(0, '/home/oib/windsurf/aitbc/apps/coordinator-api/src')

from sqlmodel import Session, select
from app.database import engine, create_db_and_tables
from app.domain.gpu_marketplace import GPURegistry

def cleanup_fake_gpus():
    """Clean up fake GPU entries from database"""
    print("=== DIRECT DATABASE CLEANUP ===")
    
    # Create tables if they don't exist
    create_db_and_tables()
    
    fake_gpus = [
        "gpu_1bdf8e86",
        "gpu_1b7da9e0", 
        "gpu_9cff5bc2",
        "gpu_ebef80a5",
        "gpu_979b24b8",
        "gpu_e5ab817d"
    ]
    
    with Session(engine) as session:
        deleted_count = 0
        
        for gpu_id in fake_gpus:
            gpu = session.exec(select(GPURegistry).where(GPURegistry.id == gpu_id)).first()
            if gpu:
                print(f"🗑️  Deleting fake GPU: {gpu_id} - {gpu.model}")
                session.delete(gpu)
                deleted_count += 1
            else:
                print(f"❓ GPU not found: {gpu_id}")
        
        try:
            session.commit()
            print(f"✅ Successfully deleted {deleted_count} fake GPUs")
        except Exception as e:
            print(f"❌ Error committing changes: {e}")
            session.rollback()
            return False
    
    return True

def show_remaining_gpus():
    """Show remaining GPUs after cleanup"""
    print("\n📋 Remaining GPUs in marketplace:")
    
    with Session(engine) as session:
        gpus = session.exec(select(GPURegistry)).all()
        
        if gpus:
            for gpu in gpus:
                print(f"  🎮 {gpu.id}: {gpu.model} - {gpu.status} - {gpu.price_per_hour} AITBC/hr")
        else:
            print("  No GPUs found")
    
    return len(gpus)

if __name__ == "__main__":
    if cleanup_fake_gpus():
        remaining = show_remaining_gpus()
        print(f"\n🎉 Cleanup complete! {remaining} GPUs remaining in marketplace")
    else:
        print("\n❌ Cleanup failed!")
        sys.exit(1)
