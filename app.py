import os
from flask import Flask, jsonify, request
from firebase_config import db
from google.cloud.firestore_v1.base_query import FieldFilter
from engine import evaluate_pickup_runs, evaluate_delivery_runs
from run_completion import complete_run_logic
from engine_chauffeur import (
    evaluate_inter_central_pickup, 
    evaluate_inter_central_delivery, 
    DEPOT_REGISTRY, 
    CENTRAL_REGISTRY
)
from complete_run_chauffeurs import complete_chauffeur_run_logic

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home_ping():
    return "OK", 200

@app.route('/api/trigger-pickup-evaluation', methods=['POST'])
def trigger_pickup():
    try:
        data = request.json or {}
        depot_id = data.get('depotId', 'default_depot')
        runs_created = evaluate_pickup_runs(depot_id)
        return jsonify({"success": True, "runs_created": runs_created}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/trigger-delivery-evaluation', methods=['POST'])
def trigger_delivery():
    try:
        data = request.json or {}
        depot_id = data.get('depotId', 'default_depot')
        runs_created = evaluate_delivery_runs(depot_id)
        return jsonify({"success": True, "runs_created": runs_created}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/complete-run', methods=['POST'])
def complete_run():
    try:
        data = request.json or {}
        run_id = data.get('runId')
        driver_id = data.get('driverId')
        
        if not run_id or not driver_id:
            return jsonify({"success": False, "error": "Missing runId or driverId"}), 400
            
        success, message = complete_run_logic(run_id, driver_id)
        return jsonify({"success": success, "message": message}), 200 if success else 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/trigger-chauffeur-pickup', methods=['POST'])
def trigger_chauffeur_pickup():
    try:
        data = request.json or {}
        central_id = data.get('centralId', 'tunis')
        runs_created = evaluate_inter_central_pickup(central_id)
        return jsonify({"success": True, "runs_created": runs_created}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/trigger-chauffeur-delivery', methods=['POST'])
def trigger_chauffeur_delivery():
    try:
        data = request.json or {}
        central_id = data.get('centralId', 'tunis')
        runs_created = evaluate_inter_central_delivery(central_id)
        return jsonify({"success": True, "runs_created": runs_created}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/complete-chauffeur-run', methods=['POST'])
def complete_chauffeur_run():
    try:
        data = request.json or {}
        run_id = data.get('runId')
        chauffeur_id = data.get('chauffeurId')
        
        if not run_id or not chauffeur_id:
            return jsonify({"success": False, "error": "Missing runId or chauffeurId"}), 400
            
        success, message = complete_chauffeur_run_logic(run_id, chauffeur_id)
        return jsonify({"success": success, "message": message}), 200 if success else 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
def auto_complete_driver_runs() -> int:
    """
    Scanne les tournées actives (IN_PROGRESS) des Livreurs et les clôture
    s'il n'y a plus aucun colis en attente de traitement (assigned/out_for_delivery).
    """
    completed_count = 0
    active_runs = db.collection('runs').where(filter=FieldFilter('status', '==', 'IN_PROGRESS')).stream()
    
    for run in active_runs:
        run_data = run.to_dict()
        run_type = run_data.get('type')
        driver_id = run_data.get('livreurId') or run_data.get('driverId')
        
        if not driver_id:
            continue
            
        # Requête O(1) ultra-optimisée pour vérifier s'il reste des colis non traités
        target_status = 'assigned' if run_type == 'PICKUP' else 'out_for_delivery'
        unprocessed_query = (
            db.collection('orders')
            .where(filter=FieldFilter('currentRunId', '==', run.id))
            .where(filter=FieldFilter('status', '==', target_status))
            .limit(1)
        )
        unprocessed_docs = list(unprocessed_query.stream())
        
        # S'il ne reste plus aucun colis à traiter dans le run -> Clôture automatique !
        if not unprocessed_docs:
            success, _ = complete_run_logic(run.id, driver_id)
            if success:
                completed_count += 1
                
    return completed_count


def auto_complete_chauffeur_runs() -> int:
    """
    Scanne les tournées actives (active) des Chauffeurs et les clôture
    s'il n'y a plus aucun colis en transit inter-ville (in_transit_inter_city).
    """
    completed_count = 0
    active_runs = db.collection('chauffeur_runs').where(filter=FieldFilter('status', '==', 'active')).stream()
    
    for run in active_runs:
        run_data = run.to_dict()
        chauffeur_id = run_data.get('chauffeurId') or run_data.get('driverId')
        
        if not chauffeur_id:
            continue
            
        # Requête O(1) ultra-optimisée : Reste-t-il des colis en cours de transport ?
        in_transit_query = (
            db.collection('orders')
            .where(filter=FieldFilter('currentRunId', '==', run.id))
            .where(filter=FieldFilter('status', '==', 'in_transit_inter_city'))
            .limit(1)
        )
        in_transit_docs = list(in_transit_query.stream())
        
        # S'il n'y a plus aucun colis en cours de transit -> Destination finale atteinte et validée !
        if not in_transit_docs:
            success, _ = complete_chauffeur_run_logic(run.id, chauffeur_id)
            if success:
                completed_count += 1
                
    return completed_count


@app.route('/api/system-tick', methods=['POST'])
def system_tick():
    """
    [ORCHESTRATEUR LOGISTIQUE GLOBAL]
    Déclenché toutes les 15 min par cron.
    1. Clôture automatique sécurisée O(1) des tournées terminées.
    2. Lancement des optimisations IA sur tous les dépôts et hubs (Livreurs et Chauffeurs).
    """
    try:
        # 1. Clôture automatique
        drivers_completed = auto_complete_driver_runs()
        chauffeurs_completed = auto_complete_chauffeur_runs()

        # 2. IA Dépôts (Livreurs)
        pickup_created = 0
        delivery_created = 0
        depot_errors = []
        
        for depot_id in DEPOT_REGISTRY.keys():
            try:
                pickup_created += evaluate_pickup_runs(depot_id)
            except Exception as e:
                depot_errors.append(f"Pickup {depot_id}: {str(e)}")
                
            try:
                delivery_created += evaluate_delivery_runs(depot_id)
            except Exception as e:
                depot_errors.append(f"Delivery {depot_id}: {str(e)}")

        # 3. IA Hubs (Chauffeurs)
        ch_pickup_created = 0
        ch_delivery_created = 0
        central_errors = []
        
        for central_id in CENTRAL_REGISTRY.keys():
            try:
                ch_pickup_created += evaluate_inter_central_pickup(central_id)
            except Exception as e:
                central_errors.append(f"Chauffeur Pickup {central_id}: {str(e)}")
                
            try:
                ch_delivery_created += evaluate_inter_central_delivery(central_id)
            except Exception as e:
                central_errors.append(f"Chauffeur Delivery {central_id}: {str(e)}")

        total_runs_created = pickup_created + delivery_created + ch_pickup_created + ch_delivery_created

        return jsonify({
            "success": True,
            "auto_completions": {
                "drivers_completed": drivers_completed,
                "chauffeurs_completed": chauffeurs_completed
            },
            "runs_created": {
                "total": total_runs_created,
                "livreur_pickup": pickup_created,
                "livreur_delivery": delivery_created,
                "chauffeur_pickup": ch_pickup_created,
                "chauffeur_delivery": ch_delivery_created
            },
            "errors": {
                "depots": depot_errors,
                "centrals": central_errors
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
