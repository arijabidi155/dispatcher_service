import os
from flask import Flask, jsonify, request
from engine import evaluate_pickup_runs, evaluate_delivery_runs
from run_completion import complete_run_logic

app = Flask(__name__)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
