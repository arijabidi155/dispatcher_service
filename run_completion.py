from firebase_config import db
from engine import evaluate_delivery_runs

def complete_run_logic(run_id, driver_id):
    """
    Handles the logic when a driver completes a run (arrives at depot).
    Implements the Smart Optimization logic:
    1. Check if completedRunsSession < 3.
    2. If yes, check for delivery runs.
    3. If no, set state to AVAILABLE (or require break).
    """
    if not db:
        return False, "Database not connected"
        
    run_ref = db.collection('runs').document(run_id)
    driver_ref = db.collection('users').document(driver_id)
    
    run_doc = run_ref.get()
    driver_doc = driver_ref.get()
    
    if not run_doc.exists or not driver_doc.exists:
        return False, "Run or Driver not found"
        
    run_data = run_doc.to_dict()
    driver_data = driver_doc.to_dict()
    
    # Update Run to COMPLETED
    run_ref.update({'status': 'COMPLETED'})
    
    # Update orders to at_destination_depot if it was a PICKUP run
    batch = db.batch()
    if run_data.get('type') == 'PICKUP':
        for order_id in run_data.get('orderIds', []):
            order_ref = db.collection('orders').document(order_id)
            batch.update(order_ref, {'status': 'at_destination_depot', 'assignedDriverId': None, 'currentRunId': None})
    elif run_data.get('type') == 'DELIVERY':
        for order_id in run_data.get('orderIds', []):
            order_ref = db.collection('orders').document(order_id)
            batch.update(order_ref, {'status': 'delivered'})
    batch.commit()
    
    # Increment completed runs
    completed_runs = driver_data.get('completedRunsSession', 0) + 1
    
    # Smart Optimization & Safety Rule
    MAX_RUNS_PER_SESSION = 3
    
    if completed_runs < MAX_RUNS_PER_SESSION and run_data.get('type') == 'PICKUP':
        # Driver is eligible for a delivery run instantly
        # Update state temporarily so evaluate_delivery_runs can pick them up if needed
        driver_ref.update({
            'completedRunsSession': completed_runs,
            'livreurState': 'AVAILABLE'
        })
        
        # Trigger delivery evaluation
        runs_created = evaluate_delivery_runs(run_data.get('depotId'))
        
        if runs_created > 0:
            return True, "Run completed. Automatically assigned to a Delivery Run."
        else:
            return True, "Run completed. No deliveries waiting, you are now AVAILABLE."
    else:
        # Reached limit or it was already a delivery run (so they might need to go back or rest)
        driver_ref.update({
            'completedRunsSession': completed_runs,
            'livreurState': 'AVAILABLE' if completed_runs < MAX_RUNS_PER_SESSION else 'OFFLINE'
        })
        
        msg = "Run completed. You are now AVAILABLE." if completed_runs < MAX_RUNS_PER_SESSION else "Session limit reached. You are now OFFLINE."
        return True, msg
