from firebase_config import db
from google.cloud.firestore_v1.base_query import FieldFilter
import datetime

print("--- Querying all orders ---")
orders_ref = db.collection('orders').stream()
orders_list = []
for doc in orders_ref:
    d = doc.to_dict()
    d['id'] = doc.id
    orders_list.append(d)

print(f"Total orders in Firestore: {len(orders_list)}")

print("\n--- Orders matching 'ready_to_collect' or 'ready_to_deliver' or 'in_transit_inter_city' ---")
relevant_statuses = ['ready_to_collect', 'ready_to_deliver', 'in_transit_inter_city', 'at_origin_depot', 'at_central_hub']
for o in orders_list:
    if o.get('status') in relevant_statuses:
        created_at = o.get('createdAt')
        created_str = created_at.isoformat() if created_at else "None"
        try:
            print(f"ID: {o['id']} | Status: {o.get('status')} | OriginCentral: {o.get('originCentral')} | DestCentral: {o.get('destCentral')} | SenderGov: {o.get('senderGovernorate')} | RecipientGov: {o.get('recipientGovernorate')} | NextStop: {o.get('nextTransitStop')} | CreatedAt: {created_str}")
        except Exception as e:
            # Fallback if there are encoding issues with governorate names (like Bja / Béja)
            print(f"ID: {o['id']} | Status: {o.get('status')} | OriginCentral: {o.get('originCentral')} | DestCentral: {o.get('destCentral')} | Error printing full: {str(e)}")

print("\n--- Running evaluation for Tunis Central Hub ---")
from engine_chauffeur import evaluate_inter_central_pickup, evaluate_inter_central_delivery, evaluate_central_tour

print("\nEvaluating inter-central pickup for Tunis Central Hub:")
pickup_runs = evaluate_inter_central_pickup("Tunis Central Hub")
print(f"Result: {pickup_runs} runs created")

print("\nEvaluating inter-central delivery for Tunis Central Hub:")
delivery_runs = evaluate_inter_central_delivery("Tunis Central Hub")
print(f"Result: {delivery_runs} runs created")

print("\nEvaluating central tour for Tunis Central Hub:")
tour_runs = evaluate_central_tour("Tunis Central Hub")
print(f"Result: {tour_runs} runs created")
