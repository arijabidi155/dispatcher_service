import datetime
from firebase_config import db
from routing import optimize_route
from assignment import select_best_livreur
from firebase_admin import firestore 
from google.cloud.firestore_v1.base_query import FieldFilter

def evaluate_pickup_runs(depot_id):
    """
    Evaluates if a PICKUP Run should be created based on the 'pending' queue.
    Conditions: count >= 6 OR wait_time >= 60 min.
    """
    if not db:
        return 0
        
    orders_ref = db.collection('orders').where(filter=FieldFilter('status', '==', 'pending')).where(filter=FieldFilter('senderGovernorate', '==', depot_id)).order_by('createdAt').limit(20)
    orders = list(orders_ref.stream())
    
    if not orders:
        return 0
        
    count = len(orders)
    oldest_order = orders[0].to_dict()
    oldest_time = oldest_order.get('createdAt')
    
    # Calculate wait time in minutes
    wait_minutes = 0
    if oldest_time:
        now = datetime.datetime.now(datetime.timezone.utc)
        wait_time = now - oldest_time
        wait_minutes = wait_time.total_seconds() / 60.0
        
    runs_created = 0
    
    # Check conditions
    if count >= 6 or wait_minutes >= 60:
        # Create a Run
        # Get depot location (placeholder, should fetch from depot collection)
        depot_lat, depot_lng = 36.8, 10.1 
        
        # Find best driver
        best_driver_id = select_best_livreur(depot_lat, depot_lng)
        
        if not best_driver_id:
            print("No available drivers for Pickup Run.")
            return 0
            
        # Optimize route using OSRM
        stops = []
        for doc in orders:
            data = doc.to_dict()
            stops.append({
                'id': doc.id,
                'lat': data.get('senderLat', 0.0),
                'lng': data.get('senderLng', 0.0)
            })
            
        ordered_stop_ids = optimize_route((depot_lat, depot_lng), stops)
        
        # Create Run document
        run_ref = db.collection('runs').document()
        run_ref.set({
            'type': 'PICKUP',
            'status': 'ASSIGNED',
            'orderIds': ordered_stop_ids,
            'livreurId': best_driver_id,
            'depotId': depot_id,
            'routePlan': ordered_stop_ids,
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        # Update driver state
        db.collection('users').document(best_driver_id).update({
            'livreurState': 'PICKUP_RUN'
        })
        
        # Update orders state
        batch = db.batch()
        for order_id in ordered_stop_ids:
            order_ref = db.collection('orders').document(order_id)
            batch.update(order_ref, {
                'status': 'assigned',
                'currentRunId': run_ref.id,
                'assignedDriverId': best_driver_id
            })
        batch.commit()
        
        runs_created += 1
        print(f"Created PICKUP Run {run_ref.id} assigned to {best_driver_id}.")
        
    return runs_created


def evaluate_delivery_runs(depot_id):
    """
    Evaluates if a DELIVERY Run should be created based on the 'at_destination_depot' queue.
    Conditions: count >= 6 OR wait_time >= 60 min.
    """
    if not db:
        return 0
        
    orders_ref = db.collection('orders').where(filter=FieldFilter('status', '==', 'at_destination_depot')).where(filter=FieldFilter('recipientGovernorate', '==', depot_id)).order_by('createdAt').limit(20)
    orders = list(orders_ref.stream())
    
    if not orders:
        return 0
        
    count = len(orders)
    oldest_order = orders[0].to_dict()
    oldest_time = oldest_order.get('createdAt')
    
    wait_minutes = 0
    if oldest_time:
        now = datetime.datetime.now(datetime.timezone.utc)
        wait_time = now - oldest_time
        wait_minutes = wait_time.total_seconds() / 60.0
        
    runs_created = 0
    
    if count >= 6 or wait_minutes >= 60:
        depot_lat, depot_lng = 36.8, 10.1 # Should fetch actual depot coordinates
        
        best_driver_id = select_best_livreur(depot_lat, depot_lng)
        
        if not best_driver_id:
            print("No available drivers for Delivery Run.")
            return 0
            
        stops = []
        for doc in orders:
            data = doc.to_dict()
            stops.append({
                'id': doc.id,
                'lat': data.get('recipientLat', 0.0),
                'lng': data.get('recipientLng', 0.0)
            })
            
        ordered_stop_ids = optimize_route((depot_lat, depot_lng), stops)
        
        run_ref = db.collection('runs').document()
        run_ref.set({
            'type': 'DELIVERY',
            'status': 'ASSIGNED',
            'orderIds': ordered_stop_ids,
            'livreurId': best_driver_id,
            'depotId': depot_id,
            'routePlan': ordered_stop_ids,
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        db.collection('users').document(best_driver_id).update({
            'livreurState': 'DELIVERY_RUN'
        })
        
        batch = db.batch()
        for order_id in ordered_stop_ids:
            order_ref = db.collection('orders').document(order_id)
            batch.update(order_ref, {
                'status': 'out_for_delivery',
                'currentRunId': run_ref.id,
                'assignedDriverId': best_driver_id
            })
        batch.commit()
        
        runs_created += 1
        print(f"Created DELIVERY Run {run_ref.id} assigned to {best_driver_id}.")
        
    return runs_created
