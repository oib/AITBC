# AITBC End-to-End Tests

This directory contains end-to-end tests for the AITBC GPU Marketplace platform.

## Tests

### test_aitbc_e2e.py
Complete end-to-end test covering:
- User registration/authentication
- GPU marketplace browsing
- GPU booking
- Task submission
- Result retrieval
- Cleanup

## Usage

```bash
# Run the E2E test
python3 tests/e2e/test_aitbc_e2e.py

# Specify custom URL
python3 tests/e2e/test_aitbc_e2e.py --url http://your-aitbc-instance:8000

# Verbose output
python3 tests/e2e/test_aitbc_e2e.py -v
```

## Prerequisites

- AITBC services running (coordinator API, blockchain node)
- Python 3.7+
- requests library (`pip install requests`)

## What This Tests

This E2E test validates the core user workflow:
1. **Authentication** - Register/login to the platform
2. **Marketplace** - Browse and book available GPU resources
3. **Compute** - Submit a task to the booked GPU
4. **Validation** - Verify the system responds correctly at each step
5. **Cleanup** - Release resources after test completion

The test is designed to be safe and non-disruptive, using short-duration bookings and cleaning up after itself.
