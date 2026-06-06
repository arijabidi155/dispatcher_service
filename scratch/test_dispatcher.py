import sys
import os
import time
import threading

# Add dispatcher service root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
import app as dispatcher_app

# Mock the database/logistics evaluation functions to simulate a 2-second computation delay
def mock_auto_complete_driver_runs():
    print("--> [MOCK] Evaluation execution started...")
    time.sleep(2)
    print("--> [MOCK] Evaluation execution finished!")
    return 1

# Apply mocks to prevent actual Firestore calls
dispatcher_app.auto_complete_driver_runs = mock_auto_complete_driver_runs
dispatcher_app.auto_complete_chauffeur_runs = lambda: 0
dispatcher_app.evaluate_pickup_runs = lambda depot_id: 0
dispatcher_app.evaluate_delivery_runs = lambda depot_id: 0
dispatcher_app.evaluate_inter_central_pickup = lambda central_id: 0
dispatcher_app.evaluate_inter_central_delivery = lambda central_id: 0

# Set up test client
client = app.test_client()
results = []

def send_request(req_id):
    print(f"[{req_id}] Sending POST /api/system-tick...")
    response = client.post('/api/system-tick')
    print(f"[{req_id}] Response Code: {response.status_code} | Data: {response.json}")
    results.append((req_id, response.status_code, response.json))

# Launch overlapping requests using threads
t1 = threading.Thread(target=send_request, args=(1,))
t2 = threading.Thread(target=send_request, args=(2,))

print("\nStarting Thread 1...")
t1.start()

# Wait briefly to ensure Thread 1 has acquired the lock
time.sleep(0.5)

print("\nStarting Thread 2 (should be rejected)...")
t2.start()

# Wait for both threads to finish
t1.join()
t2.join()

print("\n--- Concurrency Verification Results ---")
# Thread 1 should succeed with 200
# Thread 2 should fail with 429
code_1 = results[0][1] if results[0][0] == 1 else results[1][1]
code_2 = results[1][1] if results[0][0] == 1 else results[0][1]

print(f"Request 1 Status: {code_1} (Expected 200)")
print(f"Request 2 Status: {code_2} (Expected 429)")

assert code_1 == 200, f"Request 1 failed with status {code_1}"
assert code_2 == 429, f"Request 2 succeeded or returned wrong status {code_2}"
print("\nSUCCESS: Concurrency Lock successfully verified!")
