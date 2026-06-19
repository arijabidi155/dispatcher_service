import datetime
from firebase_config import db
from google.cloud.firestore_v1.base_query import FieldFilter
from engine_chauffeur import CENTRAL_REGISTRY, CENTRAL_SATELLITES, DEPOT_REGISTRY, BATCHING_LOCK_MIN, _get_order_volume, _fill_capacity, _osrm_optimize, select_best_chauffeur

print("=== DRY RUN: evaluate_inter_central_delivery WITH destCentral FIX ===")

central_id = "Tunis Central Hub"
central_info = CENTRAL_REGISTRY.get(central_id)
satellites = set(CENTRAL_SATELLITES.get(central_id, []))
now = datetime.datetime.now(datetime.timezone.utc)

# ── Fetch delivery orders at this central waiting to go to satellite depots (using destCentral instead of destinationCentral) ─
orders_ref = (
    db.collection('orders')
    .where(filter=FieldFilter('status', '==', 'ready_to_deliver'))
    .where(filter=FieldFilter('destCentral', '==', central_id))
)
docs = list(orders_ref.stream())
# Sort by createdAt in Python to avoid Firestore composite index requirement
docs.sort(key=lambda d: d.to_dict().get('createdAt') or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
print(f"Found {len(docs)} orders with destCentral == '{central_id}' and status == 'ready_to_deliver'")

raw_by_depot = {}
oldest_time = None

for doc in docs:
    data = doc.to_dict()
    dest_dep = data.get('recipientGovernorate')
    if dest_dep not in satellites:
        print(f"  Order {doc.id} recipientGov '{dest_dep}' not in satellites {satellites}")
        continue

    created_at = data.get('createdAt')
    if created_at:
        if (now - created_at).total_seconds() / 60.0 < BATCHING_LOCK_MIN:
            print(f"  Order {doc.id} locked by batching lock (< {BATCHING_LOCK_MIN} min old)")
            continue
        if oldest_time is None or created_at < oldest_time:
            oldest_time = created_at

    raw_by_depot.setdefault(dest_dep, []).append((doc.id, data))

print(f"Grouped into {len(raw_by_depot)} depots: {list(raw_by_depot.keys())}")

if raw_by_depot:
    wait_min = (now - oldest_time).total_seconds() / 60.0 if oldest_time else 0.0
    depots_with_colis = len(raw_by_depot)
    print(f"Wait minutes: {wait_min:.1f}, Depots with colis: {depots_with_colis}")
    
    # Trigger condition
    if depots_with_colis < 3 and wait_min < 120:
        print("Trigger conditions NOT met (depots < 3 and wait < 120 min)")
    else:
        print("Trigger conditions MET!")
