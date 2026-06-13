import os
import sys
import datetime

# Add parent directory to path so we can import firebase_config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from firebase_config import db
from google.cloud.firestore_v1.base_query import FieldFilter

# Constants from engine_chauffeur.py
MAX_VOLUME_CM3 = 40_000_000   # 40 m3
MAX_WEIGHT_KG = 5_000
CAPACITY_TRIGGER_RATIO = 0.80  # 80%
SLA_INTER_CENTRAL_MIN = 120    # 2 hours
BATCHING_LOCK_MIN = 20

def _get_order_volume(data: dict) -> float:
    if data.get('volumeCm3') is not None:
        return float(data['volumeCm3'])
    return float(data.get('length', 0) * data.get('width', 0) * data.get('height', 0))

def main():
    if not db:
        print("Error: Firestore database not connected.")
        return

    print("Fetching 'ready_to_collect' and 'ready_to_deliver' orders from Firestore...")
    
    # Query ready_to_collect orders
    collect_ref = db.collection('orders').where(filter=FieldFilter('status', '==', 'ready_to_collect')).stream()
    collect_orders = []
    for doc in collect_ref:
        data = doc.to_dict()
        data['id'] = doc.id
        collect_orders.append(data)
        
    # Query ready_to_deliver orders
    deliver_ref = db.collection('orders').where(filter=FieldFilter('status', '==', 'ready_to_deliver')).stream()
    deliver_orders = []
    for doc in deliver_ref:
        data = doc.to_dict()
        data['id'] = doc.id
        deliver_orders.append(data)

    print(f"Found {len(collect_orders)} orders ready to collect and {len(deliver_orders)} orders ready to deliver.\n")

    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Evaluate Pickups (originCentral -> ready_to_collect)
    print("=== EVALUATION OF INTER-CENTRAL PICKUPS ===")
    pickups_by_central = {}
    for o in collect_orders:
        central = o.get('originCentral', 'Unknown')
        pickups_by_central.setdefault(central, []).append(o)

    if not pickups_by_central:
        print("No orders ready to collect (no pending inter-central pickups).")
    else:
        for central_id, orders in pickups_by_central.items():
            print(f"\nCentral Hub: {central_id}")
            print("-" * 50)
            
            # Sort by createdAt
            orders.sort(key=lambda x: x.get('createdAt') or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc))
            
            oldest_time = None
            total_vol = 0.0
            total_wt = 0.0
            
            for o in orders:
                created_at = o.get('createdAt')
                vol = _get_order_volume(o)
                wt = o.get('weight', 0.0)
                
                # Check batching lock
                if created_at:
                    age_min = (now - created_at).total_seconds() / 60.0
                    if age_min < BATCHING_LOCK_MIN:
                        print(f"  Order {o['id']}: Under batching lock (age: {age_min:.1f} min)")
                        continue
                    if oldest_time is None or created_at < oldest_time:
                        oldest_time = created_at
                
                total_vol += vol
                total_wt += wt
                print(f"  Order {o['id']} | Vol: {vol:,.1f} cm3 | Wt: {wt:.1f} kg | Created: {created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else 'N/A'}")

            if oldest_time is None:
                print("No orders outside batching lock.")
                continue

            wait_min = (now - oldest_time).total_seconds() / 60.0
            vol_ratio = total_vol / MAX_VOLUME_CM3
            wt_ratio = total_wt / MAX_WEIGHT_KG
            
            print(f"\nSummary for {central_id}:")
            print(f"  - Total Volume: {total_vol:,.1f} cm3 ({vol_ratio*100:.2f}% of capacity)")
            print(f"  - Total Weight: {total_wt:.1f} kg ({wt_ratio*100:.2f}% of capacity)")
            print(f"  - Oldest Wait Time: {wait_min:.1f} minutes")
            
            vol_trigger = vol_ratio >= CAPACITY_TRIGGER_RATIO
            wt_trigger = wt_ratio >= CAPACITY_TRIGGER_RATIO
            sla_trigger = wait_min >= SLA_INTER_CENTRAL_MIN
            
            print(f"Triggers:")
            print(f"  - Volume >= 80%: {'YES' if vol_trigger else 'NO'}")
            print(f"  - Weight >= 80%: {'YES' if wt_trigger else 'NO'}")
            print(f"  - SLA Wait Time >= 120 min: {'YES' if sla_trigger else 'NO'}")
            
            if vol_trigger or wt_trigger or sla_trigger:
                print("RESULT: Chauffeur pickup run WILL BE TRIGGERED!")
            else:
                print("RESULT: Will NOT trigger yet.")

    # 2. Evaluate Deliveries (ready_to_deliver)
    print("\n=== EVALUATION OF INTER-CENTRAL DELIVERIES ===")
    if not deliver_orders:
        print("No orders ready to deliver (no pending inter-central deliveries).")
    else:
        # Group by originCentral
        deliveries_by_central = {}
        for o in deliver_orders:
            central = o.get('originCentral', 'Unknown')
            deliveries_by_central.setdefault(central, []).append(o)
            
        for central_id, orders in deliveries_by_central.items():
            print(f"\nCentral Hub: {central_id}")
            print("-" * 50)
            orders.sort(key=lambda x: x.get('createdAt') or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc))
            
            oldest_time = None
            total_vol = 0.0
            total_wt = 0.0
            
            for o in orders:
                created_at = o.get('createdAt')
                vol = _get_order_volume(o)
                wt = o.get('weight', 0.0)
                
                if created_at:
                    if oldest_time is None or created_at < oldest_time:
                        oldest_time = created_at
                total_vol += vol
                total_wt += wt
                print(f"  Order {o['id']} | Vol: {vol:,.1f} cm3 | Wt: {wt:.1f} kg | Created: {created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else 'N/A'}")

            wait_min = (now - oldest_time).total_seconds() / 60.0 if oldest_time else 0.0
            vol_ratio = total_vol / MAX_VOLUME_CM3
            wt_ratio = total_wt / MAX_WEIGHT_KG
            
            print(f"\nSummary for {central_id} (Delivery):")
            print(f"  - Total Volume: {total_vol:,.1f} cm3 ({vol_ratio*100:.2f}% of capacity)")
            print(f"  - Total Weight: {total_wt:.1f} kg ({wt_ratio*100:.2f}% of capacity)")
            print(f"  - Oldest Wait Time: {wait_min:.1f} minutes")
            
            vol_trigger = vol_ratio >= CAPACITY_TRIGGER_RATIO
            wt_trigger = wt_ratio >= CAPACITY_TRIGGER_RATIO
            sla_trigger = wait_min >= SLA_INTER_CENTRAL_MIN
            
            print(f"Triggers:")
            print(f"  - Volume >= 80%: {'YES' if vol_trigger else 'NO'}")
            print(f"  - Weight >= 80%: {'YES' if wt_trigger else 'NO'}")
            print(f"  - SLA Wait Time >= 120 min: {'YES' if sla_trigger else 'NO'}")
            
            if vol_trigger or wt_trigger or sla_trigger:
                print("RESULT: Chauffeur delivery run WILL BE TRIGGERED!")
            else:
                print("RESULT: Will NOT trigger yet.")

if __name__ == "__main__":
    main()
