import json
import urllib.request
import urllib.error
import random
import time

BASE_URL = "http://localhost:8080/v1"

def send_post(endpoint, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}{endpoint}", data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            return response.status
    except urllib.error.HTTPError as e:
        return e.code

def simulate_spike():
    gate7_id = "d59ac1f9-6323-4623-b9cc-ffadf35449a4"

    print(f"Starting simulated stampede at Gate 7 ({gate7_id})...")
    
    # Normal traffic for a few seconds
    for _ in range(3):
        payload = {
            "zone_id": gate7_id,
            "density": random.randint(300, 600),
            "flow_rate": random.randint(10, 30),
            "source": "cctv"
        }
        send_post("/ingest/density", payload)
        print("Sent normal traffic.")
        time.sleep(1)

    # Huge spike (approaching capacity limit 2000)
    print("INJECTING DENSITY SPIKE...")
    for _ in range(3):
        payload = {
            "zone_id": gate7_id,
            "density": random.randint(3800, 3900),
            "flow_rate": random.randint(250, 300),
            "source": "cctv"
        }
        status = send_post("/ingest/density", payload)
        print(f"Spike event accepted: {status}")
        time.sleep(0.5)

    print("Simulator finished. Check Command Console (http://localhost:8080) for the agent's reaction!")

if __name__ == "__main__":
    simulate_spike()
