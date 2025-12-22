#!/usr/bin/env python3
"""
Generate OpenAPI specifications from FastAPI services
"""

import json
import sys
import subprocess
import requests
from pathlib import Path

def extract_openapi_spec(service_name: str, base_url: str, output_file: str):
    """Extract OpenAPI spec from a running FastAPI service"""
    try:
        # Get OpenAPI spec from the service
        response = requests.get(f"{base_url}/openapi.json")
        response.raise_for_status()
        
        spec = response.json()
        
        # Add service-specific metadata
        spec["info"]["title"] = f"AITBC {service_name} API"
        spec["info"]["description"] = f"OpenAPI specification for AITBC {service_name} service"
        spec["info"]["version"] = "1.0.0"
        
        # Add servers configuration
        spec["servers"] = [
            {
                "url": "https://api.aitbc.io",
                "description": "Production server"
            },
            {
                "url": "https://staging-api.aitbc.io",
                "description": "Staging server"
            },
            {
                "url": "http://localhost:8011",
                "description": "Development server"
            }
        ]
        
        # Save the spec
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(spec, f, indent=2)
        
        print(f"✓ Generated {service_name} OpenAPI spec: {output_file}")
        return True
        
    except Exception as e:
        print(f"✗ Failed to generate {service_name} spec: {e}")
        return False

def main():
    """Generate OpenAPI specs for all AITBC services"""
    services = [
        {
            "name": "Coordinator API",
            "base_url": "http://127.0.0.2:8011",
            "output": "api/coordinator/openapi.json"
        },
        {
            "name": "Blockchain Node API",
            "base_url": "http://127.0.0.2:8080",
            "output": "api/blockchain/openapi.json"
        },
        {
            "name": "Wallet Daemon API",
            "base_url": "http://127.0.0.2:8071",
            "output": "api/wallet/openapi.json"
        }
    ]
    
    print("Generating OpenAPI specifications...")
    
    all_success = True
    for service in services:
        success = extract_openapi_spec(
            service["name"],
            service["base_url"],
            service["output"]
        )
        if not success:
            all_success = False
    
    if all_success:
        print("\n✓ All OpenAPI specifications generated successfully!")
        print("\nNext steps:")
        print("1. Review the generated specs")
        print("2. Commit them to the documentation repository")
        print("3. Update the API reference documentation")
    else:
        print("\n✗ Some specifications failed to generate")
        sys.exit(1)

if __name__ == "__main__":
    main()
