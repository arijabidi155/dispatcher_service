from firebase_config import db
import math
import datetime
from google.cloud.firestore_v1.base_query import FieldFilter


def _haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two (lat, lng) points."""
    if any(v is None for v in (lat1, lon1, lat2, lon2)):
        return 0.0
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * math.asin(math.sqrt(a)) * 6371


def select_best_chauffeur(origin_lat: float, origin_lng: float, run_type: str = None):
    """
    Finds the best available chauffeur using a weighted scoring model:

        Total Score = (Norm_Distance × 0.5)
                    + (Norm_Idle_Time  × 0.3)   ← lower idle penalty = waited longer = preferred
                    + (Norm_Workload   × 0.2)

    Lowest score wins.

    Args:
        origin_lat:  Latitude of the departure point (central or depot).
        origin_lng:  Longitude of the departure point.
        run_type:    Optional filter – 'CENTRAL_TOUR' or 'DEPOT_TOUR'.
                     Pass None to ignore vehicle-type filtering.

    Returns:
        The Firestore document ID of the best chauffeur, or None if none available.
    """
    if not db:
        return None

    # ── Fetch AVAILABLE chauffeurs ────────────────────────────────────────────
    query = (
        db.collection('users')
        .where(filter=FieldFilter('role',          '==', 'chauffeur_interville'))
        .where(filter=FieldFilter('status',        '==', 'approved'))
        .where(filter=FieldFilter('chauffeurState','==', 'AVAILABLE'))
    )

    # Optional: filter by vehicle type suitability
    # CENTRAL_TOUR requires a heavy truck; DEPOT_TOUR can use a lighter van.
    if run_type == 'CENTRAL_TOUR':
        query = query.where(filter=FieldFilter('vehicleType', '==', 'TRUCK'))
    elif run_type == 'DEPOT_TOUR':
        query = query.where(filter=FieldFilter('vehicleType', 'in', ['TRUCK', 'VAN']))

    chauffeurs = [
        {**doc.to_dict(), 'id': doc.id}
        for doc in query.stream()
    ]

    if not chauffeurs:
        return None

    # ── Normalization ceilings ────────────────────────────────────────────────
    MAX_DISTANCE_KM    = 400.0   # Tunisia is ~500 km north-south; inter-central max ~300 km
    MAX_IDLE_MINUTES   = 480.0   # 8-hour shift cap
    MAX_WORKLOAD_RUNS  = 10.0    # max runs per session before mandatory rest

    now = datetime.datetime.now(datetime.timezone.utc)

    best_id    = None
    best_score = float('inf')

    for c in chauffeurs:
        # 1. Distance from current position to origin ─────────────────────────
        c_lat = c.get('lastLat')
        c_lng = c.get('lastLng')
        dist_km = (
            _haversine(origin_lat, origin_lng, c_lat, c_lng)
            if (c_lat and c_lng)
            else MAX_DISTANCE_KM          # penalty for missing GPS
        )

        # 2. Idle time (how long they've been waiting) ─────────────────────────
        # We want drivers who waited the LONGEST to be preferred (low penalty).
        # idle_penalty = MAX - idle  →  long wait → low penalty → lower score.
        last_active = c.get('lastActiveAt')   # Firestore Timestamp expected
        if last_active:
            idle_minutes = (now - last_active).total_seconds() / 60.0
        else:
            idle_minutes = 0.0                # unknown → assume just became available

        idle_penalty = max(0.0, MAX_IDLE_MINUTES - idle_minutes)

        # 3. Session workload (fewer completed runs = preferred) ───────────────
        workload = c.get('completedRunsSession', 0)

        # ── Normalize to [0, 1] ───────────────────────────────────────────────
        norm_dist    = min(1.0, dist_km      / MAX_DISTANCE_KM)
        norm_idle    = min(1.0, idle_penalty / MAX_IDLE_MINUTES)
        norm_workload= min(1.0, workload     / MAX_WORKLOAD_RUNS)

        # ── Weighted score (lower = better) ───────────────────────────────────
        score = (norm_dist * 0.5) + (norm_idle * 0.3) + (norm_workload * 0.2)

        if score < best_score:
            best_score = score
            best_id    = c['id']

    return best_id
