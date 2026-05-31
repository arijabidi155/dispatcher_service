import requests
from firebase_admin import firestore
from firebase_config import db

RENDER_NOTIFY_URL = "https://notify-server-repo.onrender.com/send-notification"

def update_order_status_and_index(batch, order_ref, order_data, new_status, location_name=None):
    """
    Helper to update an order's status and automatically synchronize the currentNodeIndex based on routePlan.
    """
    update_data = {'status': new_status}
    route_plan = order_data.get('routePlan', [])
    
    if route_plan:
        if location_name:
            try:
                # Direct match by name
                idx = route_plan.index(location_name)
                update_data['currentNodeIndex'] = idx
            except ValueError:
                pass
                
        if 'currentNodeIndex' not in update_data:
            # Fallback/dynamic matching based on the new status
            if new_status in ['pending', 'assigned']:
                update_data['currentNodeIndex'] = 0
            elif new_status == 'at_origin_depot':
                update_data['currentNodeIndex'] = 0
            elif new_status == 'at_central_hub':
                # Map to the first occurrence of a central hub in the routePlan
                hub_indices = [i for i, node in enumerate(route_plan) if 'Hub' in node or 'Central' in node]
                if hub_indices:
                    update_data['currentNodeIndex'] = hub_indices[0]
                else:
                    # Fallback to step 1
                    update_data['currentNodeIndex'] = min(1, len(route_plan) - 1)
            elif new_status in ['at_destination_depot', 'out_for_delivery', 'delivered']:
                update_data['currentNodeIndex'] = len(route_plan) - 1

    batch.update(order_ref, update_data)
    # Return updated fields so calling functions can see the new index
    return update_data.get('currentNodeIndex', order_data.get('currentNodeIndex', 0))

def send_customer_notification(user_id, title, body, order_id=None):
    """
    Saves the notification in-app for the user on Firestore and triggers FCM pushes via the Render notifications service.
    """
    if not user_id:
        return
        
    try:
        # 1. Save in-app notification history
        notif_ref = db.collection('users').document(user_id).collection('notifications').document()
        notif_ref.set({
            'title': title,
            'body': body,
            'orderId': order_id,
            'read': False,
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        # 2. Fetch FCM tokens
        tokens_ref = db.collection('users').document(user_id).collection('tokens')
        tokens = [doc.to_dict().get('token') for doc in tokens_ref.stream() if doc.to_dict().get('token')]
        
        # 3. Call Render notification endpoint
        for token in tokens:
            try:
                response = requests.post(
                    RENDER_NOTIFY_URL,
                    json={
                        'token': token,
                        'title': title,
                        'body': body
                    },
                    timeout=5
                )
                if response.status_code != 200:
                    print(f"⚠️ [Logistics Helper] Render Push Error: {response.text}")
            except Exception as e:
                print(f"⚠️ [Logistics Helper] Failed sending HTTP push to Render: {e}")
                
    except Exception as e:
        print(f"🔔 [Logistics Helper] Error executing notification: {e}")
