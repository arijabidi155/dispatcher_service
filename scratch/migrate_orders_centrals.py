import os
import sys

# Add parent directory to path so we can import firebase_config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from firebase_config import db
from engine_chauffeur import DEPOT_REGISTRY

def main():
    if not db:
        print("Error: Firestore database not connected.")
        return

    print("Fetching all orders from Firestore to check for missing central hubs...")
    orders_ref = db.collection('orders').stream()
    
    updated_count = 0
    total_count = 0
    
    batch = db.batch()
    
    for doc in orders_ref:
        total_count += 1
        data = doc.to_dict()
        order_id = doc.id
        
        sender_gov = data.get('senderGovernorate')
        recipient_gov = data.get('recipientGovernorate')
        
        origin_central = data.get('originCentral')
        dest_central = data.get('destCentral')
        
        updated_fields = {}
        
        if not origin_central and sender_gov:
            mapped_central = DEPOT_REGISTRY.get(sender_gov, {}).get('central')
            if mapped_central:
                updated_fields['originCentral'] = mapped_central
                
        if not dest_central and recipient_gov:
            mapped_central = DEPOT_REGISTRY.get(recipient_gov, {}).get('central')
            if mapped_central:
                updated_fields['destCentral'] = mapped_central
                
        if updated_fields:
            batch.update(db.collection('orders').document(order_id), updated_fields)
            updated_count += 1
            print(f"Order {order_id}: Mapping {sender_gov} -> {updated_fields.get('originCentral', origin_central)} | {recipient_gov} -> {updated_fields.get('destCentral', dest_central)}")
            
            # Commit in batches of 400
            if updated_count % 400 == 0:
                batch.commit()
                batch = db.batch()

    if updated_count > 0:
        batch.commit()
        
    print(f"\nMigration complete! Checked {total_count} orders, updated {updated_count} orders with central hub fields.")

if __name__ == "__main__":
    main()
