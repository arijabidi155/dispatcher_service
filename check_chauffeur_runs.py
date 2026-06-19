from firebase_config import db

print("--- Querying all chauffeur runs ---")
runs = db.collection('chauffeur_runs').stream()
for r in runs:
    data = r.to_dict()
    print(f"ID: {r.id} | Status: {data.get('status')} | DriverId: {data.get('driverId') or data.get('chauffeurId')} | Type: {data.get('type')} | CreatedAt: {data.get('createdAt')}")
