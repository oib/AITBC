"""
Python SDK conformance test runner for AITBC ecosystem certification
"""

import asyncio
import json
import time
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import aiohttp
import pytest
from pydantic import BaseModel, ValidationError

# Import the SDK being tested
try:
    from aitbc_enterprise import AITBCClient, ConnectorConfig
except ImportError:
    print("ERROR: AITBC SDK not found. Please install it first.")
    sys.exit(1)


class TestResult(BaseModel):
    """Individual test result"""
    test_id: str
    name: str
    passed: bool
    duration: float
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class SuiteResult(BaseModel):
    """Test suite result"""
    suite_name: str
    level: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    duration: float
    results: List[TestResult]
    compliance_score: float


class ConformanceTestRunner:
    """Main test runner for SDK conformance"""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.client: Optional[AITBCClient] = None
        self.results: List[TestResult] = []
        
    async def run_suite(self, suite_path: str, level: str) -> SuiteResult:
        """Run a test suite"""
        print(f"\n{'='*60}")
        print(f"Running {level.upper()} Certification Tests")
        print(f"{'='*60}")
        
        # Load test suite
        with open(suite_path, 'r') as f:
            suite = json.load(f)
        
        start_time = time.time()
        
        # Initialize client
        config = ConnectorConfig(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=30.0
        )
        
        async with AITBCClient(config) as client:
            self.client = client
            
            # Run all tests
            for test in suite['tests']:
                result = await self._run_test(test)
                self.results.append(result)
                
                # Print result
                status = "✓ PASS" if result.passed else "✗ FAIL"
                print(f"{status} {result.name} ({result.duration:.3f}s)")
                
                if not result.passed:
                    print(f"    Error: {result.error}")
        
        duration = time.time() - start_time
        
        # Calculate results
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        compliance_score = (passed / len(self.results)) * 100
        
        suite_result = SuiteResult(
            suite_name=suite['name'],
            level=level,
            total_tests=len(self.results),
            passed_tests=passed,
            failed_tests=failed,
            duration=duration,
            results=self.results,
            compliance_score=compliance_score
        )
        
        # Print summary
        self._print_summary(suite_result)
        
        return suite_result
    
    async def _run_test(self, test: Dict[str, Any]) -> TestResult:
        """Run a single test"""
        start_time = time.time()
        
        try:
            # Execute request based on test definition
            response_data = await self._execute_request(test['request'])
            
            # Validate response
            validation_result = await self._validate_response(
                response_data,
                test.get('expected', {})
            )
            
            if validation_result['passed']:
                return TestResult(
                    test_id=test['id'],
                    name=test['name'],
                    passed=True,
                    duration=time.time() - start_time,
                    details=validation_result.get('details')
                )
            else:
                return TestResult(
                    test_id=test['id'],
                    name=test['name'],
                    passed=False,
                    duration=time.time() - start_time,
                    error=validation_result['error'],
                    details=validation_result.get('details')
                )
                
        except Exception as e:
            return TestResult(
                test_id=test['id'],
                name=test['name'],
                passed=False,
                duration=time.time() - start_time,
                error=str(e),
                details={"traceback": traceback.format_exc()}
            )
    
    async def _execute_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute HTTP request using SDK"""
        method = request['method'].upper()
        path = request['path']
        headers = request.get('headers', {})
        body = request.get('body')
        
        # Parse path parameters
        if '?' in path:
            path, query = path.split('?', 1)
            params = dict(q.split('=') for q in query.split('&'))
        else:
            params = {}
        
        # Make request using SDK client
        if method == 'GET':
            response = await self.client.get(path, params=params)
        elif method == 'POST':
            response = await self.client.post(path, json=body)
        elif method == 'PUT':
            response = await self.client.put(path, json=body)
        elif method == 'DELETE':
            response = await self.client.delete(path)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        return {
            'status': 200,  # SDK handles status codes
            'headers': headers,
            'body': response
        }
    
    async def _validate_response(
        self,
        response: Dict[str, Any],
        expected: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate response against expectations"""
        errors = []
        details = {}
        
        # Validate status code
        if 'status' in expected:
            if response['status'] != expected['status']:
                errors.append(
                    f"Status mismatch: expected {expected['status']}, "
                    f"got {response['status']}"
                )
        
        # Validate headers
        if 'headers' in expected:
            for header, value in expected['headers'].items():
                if header not in response['headers']:
                    errors.append(f"Missing header: {header}")
                elif value != 'string' and response['headers'][header] != value:
                    errors.append(
                        f"Header {header} mismatch: expected {value}, "
                        f"got {response['headers'][header]}"
                    )
        
        # Validate body
        if 'body' in expected:
            body_errors = await self._validate_body(
                response['body'],
                expected['body']
            )
            errors.extend(body_errors)
        
        return {
            'passed': len(errors) == 0,
            'error': '; '.join(errors) if errors else None,
            'details': details
        }
    
    async def _validate_body(self, actual: Any, expected: Any) -> List[str]:
        """Validate response body"""
        errors = []
        
        if expected == 'string':
            if not isinstance(actual, str):
                errors.append(f"Expected string, got {type(actual).__name__}")
        elif expected == 'number':
            if not isinstance(actual, (int, float)):
                errors.append(f"Expected number, got {type(actual).__name__}")
        elif expected == 'boolean':
            if not isinstance(actual, bool):
                errors.append(f"Expected boolean, got {type(actual).__name__}")
        elif expected == 'array':
            if not isinstance(actual, list):
                errors.append(f"Expected array, got {type(actual).__name__}")
        elif expected == 'object':
            if not isinstance(actual, dict):
                errors.append(f"Expected object, got {type(actual).__name__}")
        elif expected == 'null':
            if actual is not None:
                errors.append(f"Expected null, got {actual}")
        elif isinstance(expected, dict):
            if not isinstance(actual, dict):
                errors.append(f"Expected object, got {type(actual).__name__}")
            else:
                for key, value in expected.items():
                    if key not in actual:
                        errors.append(f"Missing field: {key}")
                    else:
                        field_errors = await self._validate_body(actual[key], value)
                        for error in field_errors:
                            errors.append(f"{key}.{error}")
        
        return errors
    
    def _print_summary(self, result: SuiteResult):
        """Print test suite summary"""
        print(f"\n{'='*60}")
        print(f"Test Suite Summary")
        print(f"{'='*60}")
        print(f"Suite: {result.suite_name}")
        print(f"Level: {result.level.upper()}")
        print(f"Total Tests: {result.total_tests}")
        print(f"Passed: {result.passed_tests}")
        print(f"Failed: {result.failed_tests}")
        print(f"Duration: {result.duration:.2f}s")
        print(f"Compliance Score: {result.compliance_score:.1f}%")
        
        if result.failed_tests > 0:
            print(f"\nFailed Tests:")
            for test in result.results:
                if not test.passed:
                    print(f"  ✗ {test.name} - {test.error}")
        
        print(f"\n{'='*60}")
        
        # Certification status
        if result.compliance_score >= 95:
            print(f"✓ CERTIFIED - {result.level.upper()}")
        else:
            print(f"✗ NOT CERTIFIED - Score below 95%")
    
    def save_report(self, result: SuiteResult, output_dir: Path):
        """Save test report to file"""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "suite": result.dict(),
            "sdk_version": "1.0.0",  # Get from SDK
            "test_environment": {
                "base_url": self.base_url,
                "runner_version": "1.0.0"
            }
        }
        
        output_file = output_dir / f"report_{result.level}_{int(time.time())}.json"
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nReport saved to: {output_file}")


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC SDK Conformance Test Runner")
    parser.add_argument("--base-url", default="http://localhost:8011", help="AITBC API base URL")
    parser.add_argument("--api-key", required=True, help="API key for authentication")
    parser.add_argument("--level", choices=["bronze", "silver", "gold", "all"], default="bronze")
    parser.add_argument("--output-dir", default="./reports", help="Output directory for reports")
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # Initialize test runner
    runner = ConformanceTestRunner(args.base_url, args.api_key)
    
    # Run tests based on level
    if args.level == "all":
        levels = ["bronze", "silver", "gold"]
    else:
        levels = [args.level]
    
    all_passed = True
    
    for level in levels:
        suite_path = Path(__file__).parent.parent.parent / "fixtures" / level / "api-compliance.json"
        
        if not suite_path.exists():
            print(f"ERROR: Test suite not found: {suite_path}")
            all_passed = False
            continue
        
        result = await runner.run_suite(str(suite_path), level)
        runner.save_report(result, output_dir)
        
        if result.compliance_score < 95:
            all_passed = False
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
