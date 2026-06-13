import os
import sys
import datetime

# Add parent directory to path so we can import firebase_config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from firebase_config import db
from google.cloud.firestore_v1.base_query import FieldFilter

VAN_VOLUME_CM3 = 3_000_000
TRIGGER_VOLUME = 0.85 * VAN_VOLUME_CM3  # 2,550,000 cm3

def _get_order_volume(data: dict) -> float:
    if data.get('volumeCm3') is not None:
        return float(data['volumeCm3'])
    return float(data.get('length', 0) * data.get('width', 0) * data.get('height', 0))

def main():
    if not db:
        print("Error: Firestore database not connected.")
        return

    print("Fetching pending orders from Firestore...")
    orders_ref = db.collection('orders').where(filter=FieldFilter('status', '==', 'pending')).stream()
    
    orders_by_depot = {}
    for doc in orders_ref:
        data = doc.to_dict()
        data['id'] = doc.id
        depot_id = data.get('senderGovernorate', 'Unknown')
        orders_by_depot.setdefault(depot_id, []).append(data)

    if not orders_by_depot:
        print("\nNo pending orders found in Firestore.")
        return

    print(f"\nFound pending orders across {len(orders_by_depot)} governorate(s):")
    for depot_id, orders in orders_by_depot.items():
        print(f"\n==========================================")
        print(f"Governorate/Depot: {depot_id}")
        print(f"==========================================")
        
        # Sort by createdAt (ascending) to replicate engine.py logic
        orders.sort(key=lambda o: o.get('createdAt') or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc))
        
        total_volume = 0.0
        print(f"{'Order ID':<22} | {'Created At (UTC)':<20} | {'Volume (cm3)':<12} | {'Weight (kg)':<10}")
        print("-" * 75)
        
        for order in orders:
            vol = _get_order_volume(order)
            total_volume += vol
            created_at = order.get('createdAt')
            created_str = created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else 'N/A'
            weight = order.get('weight', 0.0)
            print(f"{order['id']:<22} | {created_str:<20} | {vol:<12,.1f} | {weight:<10.1f}")
            
        print("-" * 75)
        print(f"Total pending volume: {total_volume:,.1f} cm3 ({total_volume / VAN_VOLUME_CM3 * 100:.2f}% of Van Capacity)")
        print(f"Van capacity trigger: {TRIGGER_VOLUME:,.1f} cm3 (85%)")
        
        # Calculate wait time of the oldest order
        oldest_time = orders[0].get('createdAt')
        if oldest_time:
            now = datetime.datetime.now(datetime.timezone.utc)
            wait_time = now - oldest_time
            wait_minutes = wait_time.total_seconds() / 60.0
            print(f"Oldest order wait time: {wait_minutes:.1f} minutes")
        else:
            wait_minutes = 0.0
            print("Oldest order wait time: N/A (missing createdAt)")
            
        # Evaluation
        vol_trigger = total_volume >= TRIGGER_VOLUME
        time_trigger = wait_minutes >= 60.0
        
        print(f"\nTrigger Status:")
        print(f"  - Volume >= 85%: {'YES' if vol_trigger else 'NO'}")
        print(f"  - Wait Time >= 60 min: {'YES' if time_trigger else 'NO'}")
        
        if vol_trigger or time_trigger:
            print("\nRESULT: WILL TRIGGER a pickup run!")
        else:
            print("\nRESULT: Will NOT trigger a pickup run yet (under capacity and wait time thresholds).")

if __name__ == "__main__":
    main()
