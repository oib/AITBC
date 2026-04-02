#!/usr/bin/env python3
"""
Run all phase tests for agent systems implementation
"""

import subprocess
import sys
import os
from pathlib import Path

def run_phase_tests():
    """Run tests for all phases"""
    base_dir = Path(__file__).parent
    phases = ['phase1', 'phase2', 'phase3', 'phase4', 'phase5']
    
    results = {}
    
    for phase in phases:
        phase_dir = base_dir / phase
        print(f"\n{'='*60}")
        print(f"Running {phase.upper()} Tests")
        print(f"{'='*60}")
        
        if not phase_dir.exists():
            print(f"❌ {phase} directory not found")
            results[phase] = {'status': 'skipped', 'reason': 'directory_not_found'}
            continue
        
        # Find test files
        test_files = list(phase_dir.glob('test_*.py'))
        
        if not test_files:
            print(f"❌ No test files found in {phase}")
            results[phase] = {'status': 'skipped', 'reason': 'no_test_files'}
            continue
        
        # Run tests for this phase
        phase_results = {}
        for test_file in test_files:
            print(f"\n🔹 Running {test_file.name}")
            try:
                result = subprocess.run([
                    sys.executable, '-m', 'pytest', 
                    str(test_file), 
                    '-v', 
                    '--tb=short'
                ], capture_output=True, text=True, cwd=base_dir)
                
                phase_results[test_file.name] = {
                    'returncode': result.returncode,
                    'stdout': result.stdout,
                    'stderr': result.stderr
                }
                
                if result.returncode == 0:
                    print(f"✅ {test_file.name} - PASSED")
                else:
                    print(f"❌ {test_file.name} - FAILED")
                    print(f"Error: {result.stderr}")
                    
            except Exception as e:
                print(f"❌ Error running {test_file.name}: {e}")
                phase_results[test_file.name] = {
                    'returncode': -1,
                    'stdout': '',
                    'stderr': str(e)
                }
        
        results[phase] = {
            'status': 'completed',
            'tests': phase_results,
            'total_tests': len(test_files)
        }
    
    # Print summary
    print(f"\n{'='*60}")
    print("PHASE TEST SUMMARY")
    print(f"{'='*60}")
    
    total_phases = len(phases)
    completed_phases = sum(1 for phase in results.values() if phase['status'] == 'completed')
    skipped_phases = sum(1 for phase in results.values() if phase['status'] == 'skipped')
    
    print(f"Total Phases: {total_phases}")
    print(f"Completed: {completed_phases}")
    print(f"Skipped: {skipped_phases}")
    
    for phase, result in results.items():
        print(f"\n{phase.upper()}:")
        if result['status'] == 'completed':
            passed = sum(1 for test in result['tests'].values() if test['returncode'] == 0)
            failed = sum(1 for test in result['tests'].values() if test['returncode'] != 0)
            print(f"  Tests: {result['total_tests']} (✅ {passed}, ❌ {failed})")
        else:
            print(f"  Status: {result['status']} ({result.get('reason', 'unknown')})")
    
    return results

if __name__ == '__main__':
    run_phase_tests()
