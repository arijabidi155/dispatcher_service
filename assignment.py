from firebase_config import db
import math
from google.cloud.firestore_v1.base_query import FieldFilter

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points on the earth (specified in decimal degrees)."""
    # math.radians is used to convert degrees to radians.
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 0.0
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    # haversine formula 
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371 # Radius of earth in kilometers
    return c * r

def select_best_livreur(depot_lat, depot_lng):
    """
    Finds all AVAILABLE drivers and scores them based on:
    distance_to_depot * 0.4 + idle_time * 0.3 + workload * 0.2 + rating * 0.1
    Returns the driver ID with the lowest score.
    """
    if not db:
        return None

    # Fetch available drivers
    drivers_ref = db.collection('users')\
        .where(filter=FieldFilter('role', '==', 'livreur'))\
        .where(filter=FieldFilter('status', '==', 'approved'))\
        .where(filter=FieldFilter('livreurState', '==', 'AVAILABLE')).stream()
    
    drivers = []
    for doc in drivers_ref:
        driver_data = doc.to_dict()
        driver_data['id'] = doc.id
        drivers.append(driver_data)

    if not drivers:
        return None

    # Constants for normalization (min-max scaling)
    # Assumed reasonable max values to scale metrics to 0-1 range
    MAX_DISTANCE_KM = 50.0 
    MAX_IDLE_MINUTES = 240.0 # 4 hours
    MAX_WORKLOAD = 20.0
    MAX_RATING = 5.0
    
    best_driver = None
    lowest_score = float('inf')

    for driver in drivers:
        # 1. Distance
        d_lat = driver.get('lastLat') # Assuming driver app updates location
        d_lng = driver.get('lastLng')
        if d_lat and d_lng:
            dist = calculate_distance(depot_lat, depot_lng, d_lat, d_lng)
        else:
            dist = MAX_DISTANCE_KM # Penalty for missing location

        # 2. Idle Time
        # Simplification: we might track `lastActiveTime`. 
        # If not available, we assume 0 idle time (penalty in reverse? usually we want drivers who waited longest).
        # To reward long idle time (so they get picked), we should invert it if we want the lowest score to win.
        # Let's say: idle_penalty = MAX_IDLE_MINUTES - idle_minutes (so long wait = low penalty).
        idle_minutes = 60.0 # Placeholder: fetch actual idle time
        idle_penalty = max(0, MAX_IDLE_MINUTES - idle_minutes)
        
        # 3. Workload
        workload = driver.get('completedRunsSession', 0)
        
        # 4. Rating (Invert rating because we want lowest score to win, so 5.0 rating = 0.0 penalty)
        rating = driver.get('rating', 3.0)
        rating_penalty = MAX_RATING - rating
        
        # Normalize to 0.0 - 1.0
        norm_dist = min(1.0, dist / MAX_DISTANCE_KM)
        norm_idle = min(1.0, idle_penalty / MAX_IDLE_MINUTES)
        norm_work = min(1.0, workload / MAX_WORKLOAD)
        norm_rating = min(1.0, rating_penalty / MAX_RATING)
        
        # Calculate score (Lowest is better)
        score = (norm_dist * 0.4) + (norm_idle * 0.3) + (norm_work * 0.2) + (norm_rating * 0.1)
        
        if score < lowest_score:
            lowest_score = score
            best_driver = driver['id']

    return best_driver
