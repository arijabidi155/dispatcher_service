import datetime
from firebase_config import db
from firebase_admin import firestore
from logistics_helper import update_order_status_and_index, send_customer_notification
# Importation mte3 l-moteurs mte3ek bésh l-camionét dima tal9a khédma toul
from engine_chauffeur import (
    evaluate_inter_central_pickup,
    evaluate_inter_central_delivery,
    evaluate_depot_tour
)

def complete_chauffeur_run_logic(run_id, chauffeur_id):
    """
    Handles the termination logic for Inter-City Chauffeurs.
    1. Updates Run status to COMPLETED (or RETURNING if intermediate).
    2. Updates status for all associated orders (Deliveries & Pickups).
    3. Triggers next routing cycles automatically if session limit not reached.
    """
    if not db:
        return False, "Database not connected"
        
    run_ref = db.collection('chauffeur_runs').document(run_id)
    chauffeur_ref = db.collection('users').document(chauffeur_id)
    
    run_doc = run_ref.get()
    chauffeur_doc = chauffeur_ref.get()
    
    if not run_doc.exists or not chauffeur_doc.exists:
        return False, "Run or Chauffeur not found"
        
    run_data = run_doc.to_dict()
    chauffeur_data = chauffeur_doc.to_dict()
    run_type = run_data.get('type')
    
    # ── 1. UPDATE RUN TO COMPLETED ───────────────────────────────────────────
    run_ref.update({
        'status': 'COMPLETED',
        'actualEndTime': firestore.SERVER_TIMESTAMP
    })
    
    # ── 2. UPDATE ORDERS STATUS DEPENDING ON RUN TYPE ───────────────────────
    batch = db.batch()
    notifications_to_send = []
    
    # A. Case: INTER_CENTRAL_PICKUP (Milk Run kamal w-wsal lel-central)
    if run_type == 'INTER_CENTRAL_PICKUP':
        for order_id in run_data.get('orderIds', []):
            order_ref = db.collection('orders').document(order_id)
            order_doc = order_ref.get()
            if order_doc.exists:
                order_data = order_doc.to_dict()
                update_order_status_and_index(batch, order_ref, order_data, 'at_central_hub')
                batch.update(order_ref, {
                    'currentRunId': None,
                    'assignedDriverId': None
                })
                client_id = order_data.get('clientId')
                if client_id:
                    notifications_to_send.append((
                        client_id,
                        'Mise à jour logistique',
                        'Votre colis est arrivé au centre de tri.',
                        order_id
                    ))
            
    # B. Case: INTER_CENTRAL_DELIVERY (Tawzi3 lel dépôts satellites)
    elif run_type == 'INTER_CENTRAL_DELIVERY':
        # 1. Update Deliveries (Colis elli hbathom fl-les dépôts)
        delivery_payloads = run_data.get('deliveryPayloads', {})
        for depot_id, order_ids in delivery_payloads.items():
            for oid in order_ids:
                order_ref = db.collection('orders').document(oid)
                order_doc = order_ref.get()
                if order_doc.exists:
                    order_data = order_doc.to_dict()
                    update_order_status_and_index(batch, order_ref, order_data, 'at_destination_depot', depot_id)
                    batch.update(order_ref, {
                        'currentRunId': None,
                        'assignedDriverId': None
                    })
                    client_id = order_data.get('clientId')
                    if client_id:
                        notifications_to_send.append((
                            client_id,
                            'Mise à jour logistique',
                            f"Votre colis est arrivé au dépôt de destination ({depot_id}).",
                            oid
                        ))
        # 2. Update Opportunistic Pickups (Ken lamm hājat fi thniwto)
        pickup_payloads = run_data.get('pickupPayloads', {})
        for depot_id, order_ids in pickup_payloads.items():
            for oid in order_ids:
                order_ref = db.collection('orders').document(oid)
                order_doc = order_ref.get()
                if order_doc.exists:
                    order_data = order_doc.to_dict()
                    update_order_status_and_index(batch, order_ref, order_data, 'at_central_hub')
                    batch.update(order_ref, {
                        'currentRunId': None,
                        'assignedDriverId': None
                    })
                    client_id = order_data.get('clientId')
                    if client_id:
                        notifications_to_send.append((
                            client_id,
                            'Mise à jour logistique',
                            'Votre colis est arrivé au centre de tri.',
                            oid
                        ))

    # C. Case: CENTRAL_TOUR (Ligne principale Tunis <-> Sousse e.g. avec Backhaul)
    elif run_type == 'CENTRAL_TOUR':
        # Si le chauffeur vient de terminer le retour (Backhaul cargo)
        if run_data.get('status') == 'RETURNING' or run_data.get('backhaulLoaded') == True:
            # 1. Colis mte3 l-Outbound (Aller) -> wslo lel-central destination
            for oid in run_data.get('orderIds', []):
                order_ref = db.collection('orders').document(oid)
                order_doc = order_ref.get()
                if order_doc.exists:
                    order_data = order_doc.to_dict()
                    update_order_status_and_index(batch, order_ref, order_data, 'at_central_hub')
                    batch.update(order_ref, {
                        'currentRunId': None,
                        'assignedDriverId': None
                    })
                    client_id = order_data.get('clientId')
                    if client_id:
                        notifications_to_send.append((
                            client_id,
                            'Mise à jour logistique',
                            'Votre colis est arrivé au centre de tri.',
                            oid
                        ))
            # 2. Colis mte3 l-Backhaul (Retour) -> wslo lel-central origin
            for oid in run_data.get('backhaulOrderIds', []):
                order_ref = db.collection('orders').document(oid)
                order_doc = order_ref.get()
                if order_doc.exists:
                    order_data = order_doc.to_dict()
                    update_order_status_and_index(batch, order_ref, order_data, 'at_central_hub')
                    batch.update(order_ref, {
                        'currentRunId': None,
                        'assignedDriverId': None
                    })
                    client_id = order_data.get('clientId')
                    if client_id:
                        notifications_to_send.append((
                            client_id,
                            'Mise à jour logistique',
                            'Votre colis est arrivé au centre de tri.',
                            oid
                        ))
                
    # D. Case: DEPOT_TOUR (Smart Hybrid circuit)
    elif run_type == 'DEPOT_TOUR':
        delivery_payloads = run_data.get('deliveryPayloads', {})
        for depot_id, order_ids in delivery_payloads.items():
            for oid in order_ids:
                order_ref = db.collection('orders').document(oid)
                order_doc = order_ref.get()
                if order_doc.exists:
                    order_data = order_doc.to_dict()
                    update_order_status_and_index(batch, order_ref, order_data, 'at_destination_depot', depot_id)
                    batch.update(order_ref, {
                        'currentRunId': None,
                        'assignedDriverId': None
                    })
                    client_id = order_data.get('clientId')
                    if client_id:
                        notifications_to_send.append((
                            client_id,
                            'Mise à jour logistique',
                            f"Votre colis est arrivé au dépôt de destination ({depot_id}).",
                            oid
                        ))
        pickup_payloads = run_data.get('pickupPayloads', {})
        for depot_id, order_ids in pickup_payloads.items():
            for oid in order_ids:
                order_ref = db.collection('orders').document(oid)
                order_doc = order_ref.get()
                if order_doc.exists:
                    order_data = order_doc.to_dict()
                    update_order_status_and_index(batch, order_ref, order_data, 'at_central_hub')
                    batch.update(order_ref, {
                        'currentRunId': None,
                        'assignedDriverId': None
                    })
                    client_id = order_data.get('clientId')
                    if client_id:
                        notifications_to_send.append((
                            client_id,
                            'Mise à jour logistique',
                            'Votre colis est arrivé au centre de tri.',
                            oid
                        ))

    batch.commit()
    
    # Dispatch all customer notifications asynchronously or in loop
    for client_id, title, body, order_id in notifications_to_send:
        send_customer_notification(client_id, title, body, order_id=order_id)

    
    # ── 3. SMART OPTIMIZATION & WORKLOAD BALANCE ────────────────────────────
    completed_runs = chauffeur_data.get('completedRunsSession', 0) + 1
    MAX_CHAUFFEUR_RUNS = 2  # Long-haul drivers limit per shift (inter-gouvernorats)
    
    central_id = run_data.get('centralId') or run_data.get('originCentral')
    
    if completed_runs < MAX_CHAUFFEUR_RUNS:
        # Chauffeur l-wa9t hadha dima narj3oh AVAILABLE bésh ykonéoti fard wa9t
        chauffeur_ref.update({
            'completedRunsSession': completed_runs,
            'chauffeurState': 'AVAILABLE',
            'livreurState': 'AVAILABLE'
        })
        
        # Chain Reaction: Auto-trigger de l'algorithme suivant pour maximiser le camion
        runs_created = 0
        if run_type == 'INTER_CENTRAL_PICKUP':
            # Kamel lamm colis? Tawa khalli nchoufo za7ma fama chkoun y7eb iwaza3 (Delivery)
            runs_created = evaluate_inter_central_delivery(central_id)
        elif run_type == 'INTER_CENTRAL_DELIVERY':
            # Kamel waza3? Khalli nchoufo za7ma fama chkoun y7eb ilamm (Pickup / Milk run)
            runs_created = evaluate_inter_central_pickup(central_id)
        else:
            # Pour les grands tours ou depot tour, check hybrid auto-matching
            runs_created = evaluate_depot_tour(central_id)
            
        if runs_created > 0:
            return True, "Mission terminée. Nouvelle tournée inter-central affectée automatiquement !"
        else:
            return True, "Mission terminée. Aucun colis en attente, vous êtes maintenant AVAILABLE."
            
    else:
        # Reached safety shift limit for inter-city (Sécurité routière)
        chauffeur_ref.update({
            'completedRunsSession': completed_runs,
            'chauffeurState': 'OFFLINE',
            'livreurState': 'OFFLINE'
        })
        return True, "Fin de session de travail (Limite atteinte). Camion sécurisé, vous êtes OFFLINE."
