from firebase_config import db

orders_ref = db.collection('orders').limit(5).stream()
for doc in orders_ref:
    print(f"=== ORDER {doc.id} ===")
    d = doc.to_dict()
    for k, v in sorted(d.items()):
        print(f"  {k}: {v}")
