#!/usr/bin/env python3
import requests
import time

print("Waiting for portal to start...")
time.sleep(3)

print("\n=== Testing API Endpoints ===\n")

# Test models
try:
    r = requests.get("http://localhost:5001/api/models", timeout=5)
    print(f"✓ Models endpoint: {r.status_code}")
    data = r.json()
    print(f"  - Success: {data.get('success')}")
    print(f"  - Models count: {len(data.get('models', []))}")
    print(f"  - Models: {data.get('models', [])[:3]}")
except Exception as e:
    print(f"✗ Models endpoint failed: {e}")

# Test tools
try:
    r = requests.get("http://localhost:5001/api/tools", timeout=5)
    print(f"\n✓ Tools endpoint: {r.status_code}")
    data = r.json()
    print(f"  - Success: {data.get('success')}")
    print(f"  - Tools count: {len(data.get('tools', []))}")
    for tool in data.get('tools', []):
        print(f"  - {tool.get('name')}")
except Exception as e:
    print(f"✗ Tools endpoint failed: {e}")

# Test status
try:
    r = requests.get("http://localhost:5001/api/status", timeout=5)
    print(f"\n✓ Status endpoint: {r.status_code}")
    data = r.json()
    print(f"  - MCP connected: {data.get('mcp_connected')}")
    print(f"  - Ollama available: {data.get('ollama_available')}")
except Exception as e:
    print(f"✗ Status endpoint failed: {e}")

print("\n=== Test Complete ===")
print("Open http://localhost:5001 in your browser")
