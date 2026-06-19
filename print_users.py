from firebase_config import db

print("--- Querying all users ---")
users_ref = db.collection('users').stream()
for doc in users_ref:
    u = doc.to_dict()
    print(f"ID: {doc.id} | Name: {u.get('prenom')} {u.get('nom')} | Role: {u.get('role')} | Status: {u.get('status')} | chauffeurState: {u.get('chauffeurState')} | livreurState: {u.get('livreurState')} | VehicleType: {u.get('vehicleType')}")
