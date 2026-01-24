#!/usr/bin/env python3
"""
Quick job submission and payment
Usage: python3 quick_job.py "your prompt"
"""

import subprocess
import sys
import time

if len(sys.argv) < 2:
    print("Usage: python3 quick_job.py \"your prompt\"")
    sys.exit(1)

prompt = sys.argv[1]

print(f"🚀 Submitting job: '{prompt}'")

# Submit job
result = subprocess.run(
    f'cd ../cli && python3 client.py submit inference --prompt "{prompt}"',
    shell=True,
    capture_output=True,
    text=True
)

# Extract job ID
job_id = None
for line in result.stdout.split('\n'):
    if "Job ID:" in line:
        job_id = line.split()[-1]
        break

if job_id:
    print(f"✅ Job submitted: {job_id}")
    print("\n💡 Next steps:")
    print(f"   1. Start miner: python3 cli/miner.py mine")
    print(f"   2. Check status: python3 cli/client.py status {job_id}")
    print(f"   3. After completion, pay with:")
    print(f"      cd home/client && python3 wallet.py send 25.0 $(cd home/miner && python3 wallet.py address | grep Address | cut -d' ' -f4) 'Payment for {job_id}'")
else:
    print("❌ Failed to submit job")
