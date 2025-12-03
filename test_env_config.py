#!/usr/bin/env python3
"""
Test script to verify cloud and local environment configurations.
"""
import requests
import json

def test_environment(base_url, env_name):
    """Test the debug endpoint of an API."""
    print(f"\n{'='*60}")
    print(f"Testing {env_name} Environment")
    print(f"{'='*60}\n")
    
    # Test health endpoint
    try:
        health_url = f"{base_url}/health"
        print(f"Checking health: {health_url}")
        response = requests.get(health_url, timeout=10)
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.json()}")
    except Exception as e:
        print(f"  ❌ Health check failed: {e}")
        return
    
    # Test debug endpoint
    try:
        debug_url = f"{base_url}/debug-env"
        print(f"\nChecking debug info: {debug_url}")
        response = requests.get(debug_url, timeout=10)
        
        if response.status_code == 200:
            debug_info = response.json()
            print(f"\n  Platform: {debug_info.get('platform')}")
            print(f"  Python: {debug_info.get('python_version')}")
            print(f"\n  Environment Variables:")
            for key, value in debug_info.get('environment_variables', {}).items():
                print(f"    {key}: {value}")
            print(f"\n  Chrome Available: {debug_info.get('chrome_available')}")
            if debug_info.get('chrome_path'):
                print(f"    Path: {debug_info.get('chrome_path')}")
            print(f"  ChromeDriver Available: {debug_info.get('chromedriver_available')}")
            if debug_info.get('chromedriver_path'):
                print(f"    Path: {debug_info.get('chromedriver_path')}")
        else:
            print(f"  ❌ Debug endpoint returned {response.status_code}")
            print(f"  Response: {response.text}")
    except Exception as e:
        print(f"  ❌ Debug check failed: {e}")

def main():
    """Main function."""
    print("="*60)
    print("Environment Configuration Test")
    print("="*60)
    
    # Test local environment
    local_url = "http://localhost:8000"
    test_environment(local_url, "LOCAL")
    
    # Test cloud environment
    cloud_url = "https://gujrat-tsr-agent-642363716512.asia-south1.run.app"
    test_environment(cloud_url, "CLOUD")
    
    print(f"\n{'='*60}")
    print("Test Complete")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
