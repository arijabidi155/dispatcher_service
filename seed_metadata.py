import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase Admin SDK
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# 1. Central Hub Blueprint Definitions
hubs = {
    'Tunis Central Hub': firestore.GeoPoint(36.8065, 10.1815),
    'Sousse Central Hub': firestore.GeoPoint(35.8256, 10.6369),
    'Sfax Central Hub': firestore.GeoPoint(34.7406, 10.7603),
}

# 2. Local Governorate Configuration Mappings
governorate_to_hub = {
    'Tunis': 'Tunis Central Hub', 'Ariana': 'Tunis Central Hub', 
    'Ben Arous': 'Tunis Central Hub', 'Manouba': 'Tunis Central Hub', 
    'Bizerte': 'Tunis Central Hub', 'Béja': 'Tunis Central Hub', 
    'Jendouba': 'Tunis Central Hub', 'Le Kef': 'Tunis Central Hub',
    'Sousse': 'Sousse Central Hub', 'Monastir': 'Sousse Central Hub', 
    'Mahdia': 'Sousse Central Hub', 'Kairouan': 'Sousse Central Hub', 
    'Kassérine': 'Sousse Central Hub', 'Zaghouan': 'Tunis Central Hub', 
    'Nabeul': 'Tunis Central Hub', 'Siliana': 'Sousse Central Hub',
    'Sfax': 'Sfax Central Hub', 'Gabès': 'Sfax Central Hub', 
    'Médenine': 'Sfax Central Hub', 'Tataouine': 'Sfax Central Hub', 
    'Gafsa': 'Sfax Central Hub', 'Tozeur': 'Sfax Central Hub', 
    'Kébili': 'Sfax Central Hub', 'Sidi Bouzid': 'Sfax Central Hub'
}

governorate_locations = {
    'Tunis': firestore.GeoPoint(36.8065, 10.1815), 'Ariana': firestore.GeoPoint(36.8625, 10.1956),
    'Ben Arous': firestore.GeoPoint(36.7531, 10.2228), 'Manouba': firestore.GeoPoint(36.8078, 10.0864),
    'Bizerte': firestore.GeoPoint(37.2744, 9.8739), 'Béja': firestore.GeoPoint(36.7256, 9.1817),
    'Jendouba': firestore.GeoPoint(36.5011, 8.7802), 'Le Kef': firestore.GeoPoint(36.1680, 8.7096),
    'Sousse': firestore.GeoPoint(35.8256, 10.6369), 'Monastir': firestore.GeoPoint(35.7833, 10.8333),
    'Mahdia': firestore.GeoPoint(35.5047, 11.0622), 'Kairouan': firestore.GeoPoint(35.6781, 10.0963),
    'Kassérine': firestore.GeoPoint(35.1676, 8.8358), 'Zaghouan': firestore.GeoPoint(36.4029, 10.1429),
    'Nabeul': firestore.GeoPoint(36.4561, 10.7376), 'Siliana': firestore.GeoPoint(36.0844, 9.3708),
    'Sfax': firestore.GeoPoint(34.7406, 10.7603), 'Gabès': firestore.GeoPoint(33.8814, 10.0982),
    'Médenine': firestore.GeoPoint(33.3549, 10.4958), 'Tataouine': firestore.GeoPoint(32.9297, 10.4518),
    'Gafsa': firestore.GeoPoint(34.4250, 8.7842), 'Tozeur': firestore.GeoPoint(33.9198, 8.1336),
    'Kébili': firestore.GeoPoint(33.7044, 8.9690), 'Sidi Bouzid': firestore.GeoPoint(35.0382, 9.4849)
}

print("🚀 Starting data migration initialization...")

# Push Macro Centrals
for hub_name, geo in hubs.items():
    db.collection('centrals').document(hub_name).set({
        'name': hub_name,
        'geoPoint': geo,
        'status': 'active'
    })
print("✅ Centrals updated successfully.")

# Push Regional Depots Linked to Centrals
for gov, hub_link in governorate_to_hub.items():
    loc = governorate_locations.get(gov)
    db.collection('depots').document(gov).set({
        'name': gov,
        'governorate': gov,
        'parentHubId': hub_link,
        'location': loc,
        'status': 'active'
    }, merge=True) # Merges to preserve fields if the document exists

print("🎉 Database successfully fully populated!")