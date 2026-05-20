import datetime
from firebase_config import db
from routing import optimize_route
from assignment import select_best_livreur
from firebase_admin import firestore 
from google.cloud.firestore_v1.base_query import FieldFilter

MAX_VOLUME_CM3 = 40000000  # 40 m³ (Capacité maximale du camion)
MAX_WEIGHT_KG = 5000       # 5000 kg (Capacité maximale du camion)

def _get_order_volume(order_data):
    """
    Calcule le volume avec fallback intelligent:
    1. Utilise volumeCm3 si fourni (estimé par l'IA)
    2. Sinon, calcule (length * width * height) manuellement
    """
    if 'volumeCm3' in order_data and order_data['volumeCm3'] is not None:
        return order_data['volumeCm3']
    
    length = order_data.get('length', 0)
    width = order_data.get('width', 0)
    height = order_data.get('height', 0)
    return length * width * height

def evaluate_inter_central_capacity(depot_id):
    """
    Moteur de capacité (Capacity Engine) pour les expéditions Inter-City.
    Déclencheur automatique : 80% du volume ou poids max, ou SLA (120 minutes).
    Comprend un verrou (lock) de 20 minutes pour optimiser le batching.
    """
    if not db:
        return 0
        
    # On cherche les commandes au dépôt d'origine
    orders_ref = db.collection('orders').where(filter=FieldFilter('status', 'in', ['at_origin_depot', 'pending'])).where(filter=FieldFilter('senderGovernorate', '==', depot_id)).order_by('createdAt')
    orders = list(orders_ref.stream())
    
    if not orders:
        return 0
        
    # Groupement par destination
    destinations = {}
    for doc in orders:
        data = doc.to_dict()
        dest = data.get('recipientGovernorate')
        if not dest:
            continue
            
        if dest not in destinations:
            destinations[dest] = []
        destinations[dest].append((doc.id, data))
        
    runs_created = 0
    now = datetime.datetime.now(datetime.timezone.utc)
    
    for dest, dest_orders in destinations.items():
        total_volume = 0
        total_weight = 0
        oldest_time = None
        
        batch_orders = []
        
        for order_id, data in dest_orders:
            vol = _get_order_volume(data)
            weight = data.get('weight', 0)
            
            # Anti-doublon (lock de 20 minutes pour les commandes toutes récentes)
            created_at = data.get('createdAt')
            if created_at:
                age_minutes = (now - created_at).total_seconds() / 60.0
                if age_minutes < 20:
                    # Trop récent, on le laisse s'accumuler pour batching
                    continue
                    
                if oldest_time is None or created_at < oldest_time:
                    oldest_time = created_at
                    
            # Calcul optionnel Urgency Score pour le tri : (Poids/Volume * 0.5) + (Temps d'attente * 0.4)
            urgency_score = (weight / max(vol, 1) * 0.5) + (age_minutes * 0.4 if created_at else 0)
            
            batch_orders.append((order_id, data, vol, weight, urgency_score))
            total_volume += vol
            total_weight += weight
            
        if not batch_orders:
            continue
            
        wait_minutes = 0
        if oldest_time:
            wait_minutes = (now - oldest_time).total_seconds() / 60.0
            
        volume_ratio = total_volume / MAX_VOLUME_CM3
        weight_ratio = total_weight / MAX_WEIGHT_KG
        
        # Trigger si 80% de la capacité volumétrique ou pondérale est atteinte, ou SLA (120 min)
        if volume_ratio >= 0.8 or weight_ratio >= 0.8 or wait_minutes >= 120:
            
            # On crée un Run de type INTER_CENTRAL
            run_ref = db.collection('chauffeur_runs').document()
            order_ids = [item[0] for item in batch_orders]
            
            run_ref.set({
                'type': 'INTER_CENTRAL',
                'triggerType': 'VOLUME' if (volume_ratio >= 0.8 or weight_ratio >= 0.8) else 'SLA',
                'status': 'pending', # En attente de validation par un agent ou assignation
                'stops': [depot_id, dest],
                'orderIds': order_ids,
                'createdAt': firestore.SERVER_TIMESTAMP,
                'totalVolumeCm3': total_volume,
                'totalWeightKg': total_weight
            })
            
            # Mise à jour des commandes
            batch = db.batch()
            for order_id in order_ids:
                order_ref = db.collection('orders').document(order_id)
                batch.update(order_ref, {
                    'status': 'in_transit_inter_city',
                    'currentRunId': run_ref.id
                })
            batch.commit()
            
            runs_created += 1
            print(f"Created INTER_CENTRAL Run {run_ref.id} from {depot_id} to {dest} (Vol: {volume_ratio:.0%}, Weight: {weight_ratio:.0%}, Wait: {wait_minutes:.0f}m)")
            
    return runs_created

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
