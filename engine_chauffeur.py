"""
engine_chauffeur.py  ·  v3
══════════════════════════
Smart logistics engine for CHAUFFEURS (inter-central & depot-level operations).

Run types
─────────
  INTER_CENTRAL_PICKUP   – central → satellite depots → collect colis → return to central
  INTER_CENTRAL_DELIVERY – central → satellite depots → deliver colis  → return (or loop)
  CENTRAL_TOUR           – central A → central B  (with backhaul on return)
  DEPOT_TOUR             – Smart Hybrid: deliver + pickup + opportunistic in one circuit

Tunisia geography  (24 governorates · 3 centrals · 3 zones of 8)
─────────────────────────────────────────────────────────────────
  TUNIS  → Ariana, Ben Arous, Manouba, Zaghouan, Bizerte, Nabeul, Béja, Jendouba
  SOUSSE → Monastir, Mahdia, Kairouan, Kasserine, Sidi Bouzid, Siliana, Le Kef
  SFAX   → Gabès, Médenine, Tataouine, Tozeur, Kébili, Gafsa, Skhira
"""

import math
import datetime
import requests
from firebase_config import db
from chauffeur_assignment import select_best_chauffeur
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

# ═══════════════════════════════════════════════════════════════════════════════
# Geography
# ═══════════════════════════════════════════════════════════════════════════════

CENTRAL_REGISTRY = {
    'Tunis Central Hub':  {'lat': 36.8065, 'lng': 10.1815, 'name': 'Tunis Central'},
    'Sousse Central Hub': {'lat': 35.8256, 'lng': 10.6369, 'name': 'Sousse Central'},
    'Sfax Central Hub':   {'lat': 34.7406, 'lng': 10.7603, 'name': 'Sfax Central'},
}

DEPOT_REGISTRY = {
    # Zone Tunis
    'Tunis':       {'lat': 36.8065, 'lng': 10.1815, 'central': 'Tunis Central Hub',  'name': 'Tunis'},
    'Ariana':      {'lat': 36.8625, 'lng': 10.1956, 'central': 'Tunis Central Hub',  'name': 'Ariana'},
    'Ben Arous':   {'lat': 36.7531, 'lng': 10.2228, 'central': 'Tunis Central Hub',  'name': 'Ben Arous'},
    'Manouba':     {'lat': 36.8078, 'lng': 10.0864, 'central': 'Tunis Central Hub',  'name': 'Manouba'},
    'Zaghouan':    {'lat': 36.4029, 'lng': 10.1429, 'central': 'Tunis Central Hub',  'name': 'Zaghouan'},
    'Bizerte':     {'lat': 37.2744, 'lng':  9.8739, 'central': 'Tunis Central Hub',  'name': 'Bizerte'},
    'Nabeul':      {'lat': 36.4561, 'lng': 10.7376, 'central': 'Tunis Central Hub',  'name': 'Nabeul'},
    'Béja':        {'lat': 36.7256, 'lng':  9.1817, 'central': 'Tunis Central Hub',  'name': 'Béja'},
    'Jendouba':    {'lat': 36.5011, 'lng':  8.7802, 'central': 'Tunis Central Hub',  'name': 'Jendouba'},
    # Zone Sousse
    'Sousse':      {'lat': 35.8256, 'lng': 10.6369, 'central': 'Sousse Central Hub', 'name': 'Sousse'},
    'Monastir':    {'lat': 35.7833, 'lng': 10.8333, 'central': 'Sousse Central Hub', 'name': 'Monastir'},
    'Mahdia':      {'lat': 35.5047, 'lng': 11.0622, 'central': 'Sousse Central Hub', 'name': 'Mahdia'},
    'Kairouan':    {'lat': 35.6781, 'lng': 10.0963, 'central': 'Sousse Central Hub', 'name': 'Kairouan'},
    'Kassérine':   {'lat': 35.1676, 'lng':  8.8358, 'central': 'Sousse Central Hub', 'name': 'Kassérine'},
    'Sidi Bouzid': {'lat': 35.0382, 'lng':  9.4849, 'central': 'Sousse Central Hub', 'name': 'Sidi Bouzid'},
    'Siliana':     {'lat': 36.0844, 'lng':  9.3708, 'central': 'Sousse Central Hub', 'name': 'Siliana'},
    'Le Kef':      {'lat': 36.1680, 'lng':  8.7096, 'central': 'Sousse Central Hub', 'name': 'Le Kef'},
    # Zone Sfax
    'Sfax':        {'lat': 34.7406, 'lng': 10.7603, 'central': 'Sfax Central Hub',   'name': 'Sfax'},
    'Gabès':       {'lat': 33.8814, 'lng': 10.0982, 'central': 'Sfax Central Hub',   'name': 'Gabès'},
    'Médenine':    {'lat': 33.3549, 'lng': 10.4958, 'central': 'Sfax Central Hub',   'name': 'Médenine'},
    'Tataouine':   {'lat': 32.9297, 'lng': 10.4518, 'central': 'Sfax Central Hub',   'name': 'Tataouine'},
    'Tozeur':      {'lat': 33.9198, 'lng':  8.1336, 'central': 'Sfax Central Hub',   'name': 'Tozeur'},
    'Kébili':      {'lat': 33.7044, 'lng':  8.9690, 'central': 'Sfax Central Hub',   'name': 'Kébili'},
    'Gafsa':       {'lat': 34.4250, 'lng':  8.7842, 'central': 'Sfax Central Hub',   'name': 'Gafsa'},
} 

HUB_DEPOTS = {'Tunis', 'Sousse', 'Sfax'}

CENTRAL_SATELLITES = {
    cid: [did for did, d in DEPOT_REGISTRY.items() if d['central'] == cid and did != cid and did not in HUB_DEPOTS]
    for cid in CENTRAL_REGISTRY
}

# ═══════════════════════════════════════════════════════════════════════════════
# Thresholds
# ═══════════════════════════════════════════════════════════════════════════════

MAX_VOLUME_CM3         = 40_000_000   # 40 m³
MAX_WEIGHT_KG          = 5_000
CAPACITY_TRIGGER_RATIO = 0.80         # 80 % → dispatch
SLA_INTER_CENTRAL_MIN  = 120          # minutes before SLA dispatch (inter-central)
SLA_INTRA_CENTRAL_MIN  = 90           # minutes before SLA dispatch (depot tour)
GREEDY_FILL_DETOUR_KM  = 40.0         # max extra km for greedy fill (pickup engine)
OPP_PICKUP_DETOUR_KM   = 30.0         # max detour for opportunistic pickup on delivery run
BATCHING_LOCK_MIN      = 20           # orders younger than this are not batched yet
SLA_URGENT_MIN         = 75           # opportunistic injection urgency threshold
OPPORTUNISTIC_PROX_KM  = 20.0         # proximity threshold for rerouting


# ═══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _haversine(lat1, lon1, lat2, lon2) -> float:
    if any(v is None for v in (lat1, lon1, lat2, lon2)):
        return 0.0
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * math.asin(math.sqrt(a)) * 6371


def _get_order_volume(data: dict) -> float:
    if data.get('volumeCm3') is not None:
        return float(data['volumeCm3'])
    return float(data.get('length', 0) * data.get('width', 0) * data.get('height', 0))


def _get_central_for_depot(depot_id: str):
    return DEPOT_REGISTRY.get(depot_id, {}).get('central')


def _osrm_optimize(origin_coords: tuple, stops: list) -> list:
    """OSRM Trip API → ordered stop IDs. Falls back to original order."""
    if not stops:
        return []
    parts = [f"{origin_coords[1]},{origin_coords[0]}"]
    for s in stops:
        parts.append(f"{s['lng']},{s['lat']}")
    url = (
        "http://router.project-osrm.org/trip/v1/driving/"
        + ";".join(parts)
        + "?source=first&destination=last&roundtrip=true&steps=false"
    )
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('code') == 'Ok':
                wps = data['waypoints'][1:]
                indexed = [(wps[i]['waypoint_index'], s) for i, s in enumerate(stops)]
                indexed.sort(key=lambda x: x[0])
                return [x[1]['id'] for x in indexed]
    except Exception as e:
        print(f"[OSRM] {e}")
    return [s['id'] for s in stops]


def _route_distance_km(origin: tuple, ordered_coords: list) -> float:
    """Haversine chain: origin → stops → origin."""
    pts = [origin] + ordered_coords + [origin]
    return sum(_haversine(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
               for i in range(len(pts) - 1))


def _cheapest_insertion_detour(route_coords: list, new_coord: tuple) -> float:
    """Min detour cost (km) to insert new_coord anywhere in route_coords list."""
    best = float('inf')
    for i in range(len(route_coords) - 1):
        A, B = route_coords[i], route_coords[i + 1]
        via = (_haversine(A[0], A[1], new_coord[0], new_coord[1])
               + _haversine(new_coord[0], new_coord[1], B[0], B[1]))
        direct = _haversine(A[0], A[1], B[0], B[1])
        best = min(best, max(0.0, via - direct))
    return best


def _fill_capacity(orders_by_depot: dict, max_vol: float, max_wt: float,
                   now, sort_by_urgency: bool = True) -> tuple:
    """
    Greedy fill: accept orders from depots sorted by urgency (oldest first).
    Returns (accepted: {depot_id: [(order_id, data)]}, used_vol, used_wt).
    """
    if sort_by_urgency:
        def _depot_age(depot_id):
            ages = []
            for _, d in orders_by_depot[depot_id]:
                ca = d.get('createdAt')
                if ca:
                    ages.append((now - ca).total_seconds() / 60.0)
            return max(ages) if ages else 0.0
        sorted_depots = sorted(orders_by_depot.keys(), key=_depot_age, reverse=True)
    else:
        sorted_depots = list(orders_by_depot.keys())

    accepted = {}
    used_vol, used_wt = 0.0, 0.0
    for depot_id in sorted_depots:
        for oid, data in orders_by_depot[depot_id]:
            v = _get_order_volume(data)
            w = data.get('weight', 0.0)
            if used_vol + v <= max_vol and used_wt + w <= max_wt:
                accepted.setdefault(depot_id, []).append((oid, data))
                used_vol += v
                used_wt  += w
    return accepted, used_vol, used_wt


# ═══════════════════════════════════════════════════════════════════════════════
# ① INTER-CENTRAL PICKUP ENGINE
#    central → satellite depots → collect colis → return to central
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_inter_central_pickup(central_id: str) -> int:
    """
    Dispatches INTER_CENTRAL_PICKUP runs.

    Triggers:
      • ≥ 1 satellite depot has colis with status 'ready_to_collect', AND
        volume_ratio ≥ 80 %  OR  weight_ratio ≥ 80 %  OR  wait ≥ SLA_INTER_CENTRAL_MIN

    Greedy fill (Smart Capacity Rule):
      If the truck is not full after adding all primary stops, the engine
      extends the route to nearby depots (by detour cost ≤ GREEDY_FILL_DETOUR_KM)
      that also have pickups, to avoid returning half-empty.

    Run always returns to the origin central.

    Firestore doc:
      type           : 'INTER_CENTRAL_PICKUP'
      centralId      : origin central
      stops          : [central_id, d1, d2, …, central_id]
      pickupPayloads : { depot_id: [order_id, …] }
      orderIds       : flat list
      status orders  : 'in_transit_to_central'
    """
    if not db:
        return 0

    central_info = CENTRAL_REGISTRY.get(central_id)
    if not central_info:
        return 0

    satellites = set(CENTRAL_SATELLITES.get(central_id, []))
    now = datetime.datetime.now(datetime.timezone.utc)

    # ── Fetch all 'ready_to_collect' orders in satellite depots ──────────────
    orders_ref = (
        db.collection('orders')
        .where(filter=FieldFilter('status', '==', 'ready_to_collect'))
        .where(filter=FieldFilter('originCentral', '==', central_id))
        .order_by('createdAt')
    )
    docs = list(orders_ref.stream())
    if not docs:
        return 0

    raw_by_depot: dict[str, list] = {}
    oldest_time = None

    for doc in docs:
        data = doc.to_dict()
        depot_id = data.get('senderGovernorate')
        if depot_id not in satellites:
            continue

        # Batching lock
        created_at = data.get('createdAt')
        if created_at:
            if (now - created_at).total_seconds() / 60.0 < BATCHING_LOCK_MIN:
                continue
            if oldest_time is None or created_at < oldest_time:
                oldest_time = created_at

        raw_by_depot.setdefault(depot_id, []).append((doc.id, data))

    if not raw_by_depot:
        return 0

    # ── Compute metrics ───────────────────────────────────────────────────────
    total_vol = sum(_get_order_volume(d) for items in raw_by_depot.values()
                    for _, d in items)
    total_wt  = sum(d.get('weight', 0.0) for items in raw_by_depot.values()
                    for _, d in items)
    wait_min  = (now - oldest_time).total_seconds() / 60.0 if oldest_time else 0.0
    vol_ratio = total_vol / MAX_VOLUME_CM3
    wt_ratio  = total_wt  / MAX_WEIGHT_KG

    if vol_ratio < CAPACITY_TRIGGER_RATIO and wt_ratio < CAPACITY_TRIGGER_RATIO \
            and wait_min < SLA_INTER_CENTRAL_MIN:
        return 0

    trigger = ('CAPACITY' if (vol_ratio >= CAPACITY_TRIGGER_RATIO
                              or wt_ratio >= CAPACITY_TRIGGER_RATIO)
               else 'SLA')

    # ── Greedy capacity fill ──────────────────────────────────────────────────
    accepted, used_vol, used_wt = _fill_capacity(
        raw_by_depot, MAX_VOLUME_CM3, MAX_WEIGHT_KG, now
    )

    # If truck not full → look for nearby depots (greedy fill)
    remaining_vol = MAX_VOLUME_CM3 - used_vol
    remaining_wt  = MAX_WEIGHT_KG  - used_wt
    greedy_extras: list[str] = []

    if remaining_vol / MAX_VOLUME_CM3 > 0.2:   # still > 20 % free space
        current_route_coords = (
            [(central_info['lat'], central_info['lng'])]
            + [(DEPOT_REGISTRY[d]['lat'], DEPOT_REGISTRY[d]['lng']) for d in accepted]
            + [(central_info['lat'], central_info['lng'])]
        )

        for candidate in satellites - set(accepted.keys()):
            # Check for pickups not yet triggered
            extra_ref = (
                db.collection('orders')
                .where(filter=FieldFilter('status', '==', 'ready_to_collect'))
                .where(filter=FieldFilter('senderGovernorate', '==', candidate))
                .limit(10)
            )
            extra_docs = list(extra_ref.stream())
            if not extra_docs:
                continue

            cdep       = DEPOT_REGISTRY[candidate]
            detour     = _cheapest_insertion_detour(
                current_route_coords, (cdep['lat'], cdep['lng'])
            )
            if detour > GREEDY_FILL_DETOUR_KM:
                continue

            for edoc in extra_docs:
                edata = edoc.to_dict()
                v = _get_order_volume(edata)
                w = edata.get('weight', 0.0)
                if remaining_vol - v >= 0 and remaining_wt - w >= 0:
                    accepted.setdefault(candidate, []).append((edoc.id, edata))
                    remaining_vol -= v
                    remaining_wt  -= w
                    used_vol      += v
                    used_wt       += w

            if candidate in accepted:
                greedy_extras.append(candidate)

    if not accepted:
        return 0

    # ── OSRM route optimisation ───────────────────────────────────────────────
    stops_for_osrm = [
        {'id': did, 'lat': DEPOT_REGISTRY[did]['lat'], 'lng': DEPOT_REGISTRY[did]['lng']}
        for did in accepted
    ]
    central_coords    = (central_info['lat'], central_info['lng'])
    ordered_depot_ids = _osrm_optimize(central_coords, stops_for_osrm)

    # ── Assign chauffeur ──────────────────────────────────────────────────────
    chauffeur_id = select_best_chauffeur(
        central_info['lat'], central_info['lng'], run_type='INTER_CENTRAL_PICKUP'
    )
    if not chauffeur_id:
        print(f"[ICP] No chauffeur available for central {central_id}")
        return 0

    # ── Build payloads & order list ───────────────────────────────────────────
    pickup_payloads = {did: [oid for oid, _ in items] for did, items in accepted.items()}
    all_order_ids   = [oid for ids in pickup_payloads.values() for oid in ids]

    # ── Write Firestore ───────────────────────────────────────────────────────
    run_ref = db.collection('chauffeur_runs').document()
    run_ref.set({
        'type':              'INTER_CENTRAL_PICKUP',
        'triggerType':       trigger,
        'status':            'pending',
        'currentStopIndex':  0,
        'centralId':         central_id,
        'chauffeurId':       chauffeur_id,
        'driverId':          chauffeur_id,
        'stops':             [central_id] + ordered_depot_ids + [central_id],
        'pickupPayloads':  pickup_payloads,
        'orderIds':        all_order_ids,
        'totalOrders':     len(all_order_ids),
        'totalVolumeCm3':  used_vol,
        'totalWeightKg':   used_wt,
        'greedyFillStops': greedy_extras,
        'waitMinutes':     round(wait_min, 1),
        'createdAt':       firestore.SERVER_TIMESTAMP,
    })

    db.collection('users').document(chauffeur_id).update({
        'chauffeurState': 'ON_INTER_CENTRAL_PICKUP',
        'currentRunId':   run_ref.id,
    })

    batch = db.batch()
    for oid in all_order_ids:
        batch.update(db.collection('orders').document(oid), {
            'status':              'in_transit_inter_city',
            'currentRunId':        run_ref.id,
            'assignedDriverId': chauffeur_id,
        })
    batch.commit()

    print(f"[ICP] {run_ref.id} | {central_id} -> {ordered_depot_ids} -> {central_id} "
          f"| {len(all_order_ids)} orders | vol:{used_vol/MAX_VOLUME_CM3:.0%} "
          f"wt:{used_wt/MAX_WEIGHT_KG:.0%} | greedy:{greedy_extras}")
    return 1


# ═══════════════════════════════════════════════════════════════════════════════
# ② INTER-CENTRAL DELIVERY ENGINE
#    central → satellite depots → deliver colis → opportunistic pickup → return
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_inter_central_delivery(central_id: str) -> int:
    """
    Dispatches INTER_CENTRAL_DELIVERY runs.

    Triggers:
      • ≥ N depots have pending deliveries (at_central) OR wait ≥ SLA

    Opportunistic pickup (Smart Capacity Rule):
      After loading delivery parcels, if remaining capacity exists AND a depot
      on the route has pickups with detour ≤ OPP_PICKUP_DETOUR_KM → add them.
      If truck is already full → skip all opportunistic pickups.

    Smart return rule:
      Returns to central ONLY IF all delivery parcels have been assigned.
      If not triggered (partial), loop continues on next call — this function
      always creates an atomic run and sets returnToBase: True/False in the doc,
      allowing the driver app to act accordingly.

    Firestore doc:
      type              : 'INTER_CENTRAL_DELIVERY'
      centralId         : origin central
      stops             : [central_id, d1, d2, …, central_id]
      deliveryPayloads  : { depot_id: [order_id, …] }
      pickupPayloads    : { depot_id: [order_id, …] }  (opportunistic)
      orderIds          : flat list (delivery + pickup)
      returnToBase      : True/False
      status orders (delivery) : 'in_transit_to_depot'
      status orders (pickup)   : 'in_transit_to_central'
    """
    if not db:
        return 0

    central_info = CENTRAL_REGISTRY.get(central_id)
    if not central_info:
        return 0

    satellites = set(CENTRAL_SATELLITES.get(central_id, []))
    now = datetime.datetime.now(datetime.timezone.utc)

    # ── Fetch delivery orders at this central waiting to go to satellite depots ─
    orders_ref = (
        db.collection('orders')
        .where(filter=FieldFilter('status', '==', 'ready_to_deliver'))
        .where(filter=FieldFilter('destCentral', '==', central_id))
    )
    docs = list(orders_ref.stream())
    docs.sort(key=lambda d: d.to_dict().get('createdAt') or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
    if not docs:
        return 0

    raw_by_depot: dict[str, list] = {}
    oldest_time = None

    for doc in docs:
        data     = doc.to_dict()
        dest_dep = data.get('recipientGovernorate')
        if dest_dep not in satellites:
            continue

        created_at = data.get('createdAt')
        if created_at:
            if (now - created_at).total_seconds() / 60.0 < BATCHING_LOCK_MIN:
                continue
            if oldest_time is None or created_at < oldest_time:
                oldest_time = created_at

        raw_by_depot.setdefault(dest_dep, []).append((doc.id, data))

    if not raw_by_depot:
        return 0

    wait_min          = (now - oldest_time).total_seconds() / 60.0 if oldest_time else 0.0
    depots_with_colis = len(raw_by_depot)

    # Trigger: ≥ 3 depots have deliveries OR SLA
    if depots_with_colis < 3 and wait_min < SLA_INTER_CENTRAL_MIN:
        return 0

    trigger = 'COVERAGE' if depots_with_colis >= 3 else 'SLA'

    # ── Load delivery orders within capacity ──────────────────────────────────
    accepted_delivery, used_vol, used_wt = _fill_capacity(
        raw_by_depot, MAX_VOLUME_CM3, MAX_WEIGHT_KG, now
    )

    if not accepted_delivery:
        return 0

    # ── Opportunistic pickup on same route ────────────────────────────────────
    remaining_vol = MAX_VOLUME_CM3 - used_vol
    remaining_wt  = MAX_WEIGHT_KG  - used_wt
    accepted_pickup: dict[str, list] = {}
    opp_stops: list[str] = []

    # Only attempt if truck isn't full (Smart Capacity Rule)
    if remaining_vol / MAX_VOLUME_CM3 > 0.05:
        route_coords = (
            [(central_info['lat'], central_info['lng'])]
            + [(DEPOT_REGISTRY[d]['lat'], DEPOT_REGISTRY[d]['lng'])
               for d in accepted_delivery]
            + [(central_info['lat'], central_info['lng'])]
        )

        # Check each delivery stop AND nearby non-delivery satellites
        candidates = set(accepted_delivery.keys()) | (satellites - set(accepted_delivery.keys()))

        for candidate in candidates:
            pickup_ref = (
                db.collection('orders')
                .where(filter=FieldFilter('status', '==', 'ready_to_collect'))
                .where(filter=FieldFilter('senderGovernorate', '==', candidate))
                .limit(10)
            )
            pickup_docs = list(pickup_ref.stream())
            if not pickup_docs:
                continue

            cdep   = DEPOT_REGISTRY[candidate]
            detour = _cheapest_insertion_detour(
                route_coords, (cdep['lat'], cdep['lng'])
            )
            if detour > OPP_PICKUP_DETOUR_KM:
                continue

            for pdoc in pickup_docs:
                pdata = pdoc.to_dict()
                v = _get_order_volume(pdata)
                w = pdata.get('weight', 0.0)
                if remaining_vol - v >= 0 and remaining_wt - w >= 0:
                    accepted_pickup.setdefault(candidate, []).append((pdoc.id, pdata))
                    remaining_vol -= v
                    remaining_wt  -= w
                    used_vol      += v
                    used_wt       += w

            if candidate in accepted_pickup and candidate not in accepted_delivery:
                opp_stops.append(candidate)

    # ── Union of all stops ────────────────────────────────────────────────────
    all_stop_depots = set(accepted_delivery.keys()) | set(accepted_pickup.keys())

    # ── OSRM ─────────────────────────────────────────────────────────────────
    stops_for_osrm = [
        {'id': did, 'lat': DEPOT_REGISTRY[did]['lat'], 'lng': DEPOT_REGISTRY[did]['lng']}
        for did in all_stop_depots
    ]
    central_coords    = (central_info['lat'], central_info['lng'])
    ordered_depot_ids = _osrm_optimize(central_coords, stops_for_osrm)

    # ── Smart return rule ─────────────────────────────────────────────────────
    # Return to base only if ALL pending delivery orders are covered in this run
    all_delivery_ids = [oid for ids in
                        {did: [o for o, _ in items]
                         for did, items in accepted_delivery.items()}.values()
                        for oid in ids]
    return_to_base   = (len(all_delivery_ids) >= sum(len(v) for v in raw_by_depot.values()))

    # ── Assign chauffeur ──────────────────────────────────────────────────────
    chauffeur_id = select_best_chauffeur(
        central_info['lat'], central_info['lng'], run_type='INTER_CENTRAL_DELIVERY'
    )
    if not chauffeur_id:
        print(f"[ICD] No chauffeur for {central_id}")
        return 0

    # ── Build payloads ────────────────────────────────────────────────────────
    delivery_payloads = {did: [o for o, _ in items]
                         for did, items in accepted_delivery.items()}
    pickup_payloads   = {did: [o for o, _ in items]
                         for did, items in accepted_pickup.items()}

    all_delivery_oids = [o for ids in delivery_payloads.values() for o in ids]
    all_pickup_oids   = [o for ids in pickup_payloads.values()   for o in ids]
    all_order_ids     = list(set(all_delivery_oids + all_pickup_oids))

    # ── stopManifest ──────────────────────────────────────────────────────────
    stop_manifest = []
    for did in ordered_depot_ids:
        has_del = did in delivery_payloads
        has_pk  = did in pickup_payloads
        if not has_del and not has_pk:
            continue
        stop_manifest.append({
            'depotId':         did,
            'depotName':       DEPOT_REGISTRY[did]['name'],
            'lat':             DEPOT_REGISTRY[did]['lat'],
            'lng':             DEPOT_REGISTRY[did]['lng'],
            'action':          ('BOTH' if has_del and has_pk
                                else 'DELIVERY' if has_del else 'PICKUP'),
            'deliverOrderIds': delivery_payloads.get(did, []),
            'pickupOrderIds':  pickup_payloads.get(did, []),
            'isOpportunistic': did in opp_stops,
        })

    # ── Write Firestore ───────────────────────────────────────────────────────
    run_ref = db.collection('chauffeur_runs').document()
    run_ref.set({
        'type':               'INTER_CENTRAL_DELIVERY',
        'triggerType':        trigger,
        'status':             'pending',
        'currentStopIndex':   0,
        'centralId':          central_id,
        'chauffeurId':        chauffeur_id,
        'driverId':           chauffeur_id,
        'stops':              [central_id] + ordered_depot_ids + ([central_id] if return_to_base else []),
        'stopManifest':       stop_manifest,
        'deliveryPayloads':   delivery_payloads,
        'pickupPayloads':     pickup_payloads,
        'orderIds':           all_order_ids,
        'totalDeliveries':    len(all_delivery_oids),
        'totalPickups':       len(all_pickup_oids),
        'totalVolumeCm3':     used_vol,
        'totalWeightKg':      used_wt,
        'returnToBase':       return_to_base,
        'opportunisticStops': opp_stops,
        'waitMinutes':        round(wait_min, 1),
        'createdAt':          firestore.SERVER_TIMESTAMP,
    })

    db.collection('users').document(chauffeur_id).update({
        'chauffeurState': 'ON_INTER_CENTRAL_DELIVERY',
        'currentRunId':   run_ref.id,
    })

    batch = db.batch()
    for oid in all_delivery_oids:
        batch.update(db.collection('orders').document(oid), {
            'status':              'in_transit_inter_city',
            'currentRunId':        run_ref.id,
            'assignedDriverId': chauffeur_id,
        })
    for oid in all_pickup_oids:
        batch.update(db.collection('orders').document(oid), {
            'status':              'in_transit_inter_city',
            'currentRunId':        run_ref.id,
            'assignedDriverId': chauffeur_id,
        })
    batch.commit()

    print(f"[ICD] {run_ref.id} | {central_id} -> {ordered_depot_ids} "
          f"| del:{len(all_delivery_oids)} pk:{len(all_pickup_oids)} "
          f"| opp:{opp_stops} returnToBase:{return_to_base}")
    return 1


# ═══════════════════════════════════════════════════════════════════════════════
# ③ CENTRAL TOUR ENGINE  (A → B with Backhaul Check on return)
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_central_tour(origin_central_id: str) -> int:
    """
    Dispatches CENTRAL_TOUR runs from origin_central_id to each other central.

    Trigger: volume ≥ 80 % OR weight ≥ 80 % OR wait ≥ 120 min (20-min batching lock).

    Backhaul logic (never return empty):
      After arriving at dest_central, the chauffeur checks for orders that go
      from dest_central back to origin_central (status 'at_central',
      senderCentral == dest_central, destinationCentral == origin_central_id).
      These are added to backhaulPayloads and the run doc is updated so the
      driver app can load them before departing.

    Firestore doc:
      type              : 'CENTRAL_TOUR'
      originCentral     : origin
      destCentral       : destination
      chauffeurId
      stops             : [origin, dest]
      orderIds          : outbound order ids
      backhaulPayloads  : { dest_central_id: [order_id, …] }   (filled at arrival)
      backhaulOrderIds  : flat list  (filled at arrival via complete_central_tour())
      status            : 'ASSIGNED' → 'AT_DESTINATION' → 'RETURNING' → 'COMPLETED'
    """
    if not db:
        return 0

    origin_info = CENTRAL_REGISTRY.get(origin_central_id)
    if not origin_info:
        print(f"[CT] Unknown central: {origin_central_id}")
        return 0

    orders_ref = (
        db.collection('orders')
        .where(filter=FieldFilter('status', 'in', ['ready_to_collect', 'ready_to_deliver']))
        .where(filter=FieldFilter('originCentral', '==', origin_central_id))
        .order_by('createdAt')
    )
    orders = list(orders_ref.stream())
    if not orders:
        return 0

    now = datetime.datetime.now(datetime.timezone.utc)
    by_dest: dict[str, list] = {}

    for doc in orders:
        data         = doc.to_dict()
        dest_depot   = data.get('recipientGovernorate')
        dest_central = _get_central_for_depot(dest_depot)
        if not dest_central or dest_central == origin_central_id:
            continue
        by_dest.setdefault(dest_central, []).append((doc.id, data))

    runs_created = 0

    for dest_central_id, dest_orders in by_dest.items():
        batch_orders, total_vol, total_wt, oldest = [], 0.0, 0.0, None

        for order_id, data in dest_orders:
            ca = data.get('createdAt')
            if ca:
                if (now - ca).total_seconds() / 60.0 < BATCHING_LOCK_MIN:
                    continue
                if oldest is None or ca < oldest:
                    oldest = ca
            v = _get_order_volume(data)
            w = data.get('weight', 0.0)
            total_vol += v
            total_wt  += w
            batch_orders.append((order_id, v, w))

        if not batch_orders:
            continue

        wait_m  = (now - oldest).total_seconds() / 60.0 if oldest else 0.0
        vol_r   = total_vol / MAX_VOLUME_CM3
        wt_r    = total_wt  / MAX_WEIGHT_KG
        trigger = ('CAPACITY' if (vol_r >= CAPACITY_TRIGGER_RATIO
                                  or wt_r >= CAPACITY_TRIGGER_RATIO)
                   else 'SLA' if wait_m >= SLA_INTER_CENTRAL_MIN else None)
        if not trigger:
            continue

        chauffeur_id = select_best_chauffeur(
            origin_info['lat'], origin_info['lng'], run_type='CENTRAL_TOUR'
        )
        if not chauffeur_id:
            print(f"[CT] No chauffeur: {origin_central_id}->{dest_central_id}")
            continue

        order_ids = [o[0] for o in batch_orders]

        # ── Pre-check backhaul availability (snapshot at dispatch time) ───────
        backhaul_ref = (
            db.collection('orders')
            .where(filter=FieldFilter('status', '==', 'ready_to_deliver'))
            .where(filter=FieldFilter('senderCentral',      '==', dest_central_id))
            .where(filter=FieldFilter('destCentral',        '==', origin_central_id))
            .limit(50)
        )
        backhaul_docs       = list(backhaul_ref.stream())
        backhaul_available  = len(backhaul_docs)
        backhaul_order_ids  = [d.id for d in backhaul_docs]

        run_ref = db.collection('chauffeur_runs').document()
        run_ref.set({
            'type':                 'CENTRAL_TOUR',
            'triggerType':          trigger,
            'status':               'pending',
            'currentStopIndex':     0,
            'originCentral':        origin_central_id,
            'destCentral':          dest_central_id,
            'stops':                [origin_central_id, dest_central_id],
            'chauffeurId':          chauffeur_id,
            'driverId':             chauffeur_id,
            'orderIds':             order_ids,
            'totalVolumeCm3':       total_vol,
            'totalWeightKg':        total_wt,
            # Backhaul — will be confirmed/loaded when chauffeur arrives
            'backhaulAvailable':    backhaul_available,
            'backhaulOrderIds':     [],          # filled by complete_central_tour_outbound()
            'backhaulPayloads':     {},
            'backhaulLoaded':       False,
            'waitMinutes':          round(wait_m, 1),
            'createdAt':            firestore.SERVER_TIMESTAMP,
        })

        db.collection('users').document(chauffeur_id).update({
            'chauffeurState': 'ON_CENTRAL_TOUR',
            'currentRunId':   run_ref.id,
        })

        batch = db.batch()
        for oid in order_ids:
            batch.update(db.collection('orders').document(oid), {
                'status':              'in_transit_inter_city',
                'currentRunId':        run_ref.id,
                'assignedDriverId': chauffeur_id,
            })
        batch.commit()

        runs_created += 1
        print(f"[CT] {run_ref.id} | {origin_central_id}->{dest_central_id} "
              f"| vol:{vol_r:.0%} wt:{wt_r:.0%} wait:{wait_m:.0f}m "
              f"| backhaul_available:{backhaul_available}")

    return runs_created


def complete_central_tour_outbound(run_id: str) -> dict:
    """
    Called when the chauffeur confirms arrival at dest_central (AT_DESTINATION).
    Executes the Backhaul Check: loads return orders into the run so the driver
    doesn't return empty.

    Steps:
      1. Mark run status → 'AT_DESTINATION'
      2. Query orders: status='at_central', senderCentral=dest, destCentral=origin
      3. Fill reverse load within remaining capacity
      4. Update run: backhaulOrderIds, backhaulPayloads, backhaulLoaded=True
      5. Set backhaul orders → 'in_transit_inter_central'

    Returns { 'backhaulLoaded': bool, 'count': int, 'message': str }
    """
    if not db:
        return {'backhaulLoaded': False, 'count': 0, 'message': 'DB not connected'}

    run_ref = db.collection('chauffeur_runs').document(run_id)
    run_doc = run_ref.get()
    if not run_doc.exists:
        return {'backhaulLoaded': False, 'count': 0, 'message': 'Run not found'}

    run_data       = run_doc.to_dict()
    origin_central = run_data.get('originCentral')
    dest_central   = run_data.get('destCentral')
    used_vol       = run_data.get('totalVolumeCm3', 0.0)
    used_wt        = run_data.get('totalWeightKg',  0.0)

    # After delivering, truck is now empty — full capacity for backhaul
    # (conservative: assume delivery unloaded, so remaining = MAX)
    remaining_vol  = MAX_VOLUME_CM3
    remaining_wt   = MAX_WEIGHT_KG

    # Update run status
    run_ref.update({'status': 'AT_DESTINATION'})

    # ── Fetch return orders ───────────────────────────────────────────────────
    backhaul_ref = (
        db.collection('orders')
        .where(filter=FieldFilter('status',               '==', 'ready_to_deliver'))
        .where(filter=FieldFilter('senderCentral',        '==', dest_central))
        .where(filter=FieldFilter('destCentral',          '==', origin_central))
    )
    backhaul_docs = list(backhaul_ref.stream())
    backhaul_docs.sort(key=lambda d: d.to_dict().get('createdAt') or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))

    if not backhaul_docs:
        run_ref.update({'status': 'RETURNING', 'backhaulLoaded': False})
        return {'backhaulLoaded': False, 'count': 0,
                'message': 'No backhaul orders. Returning empty.'}

    now = datetime.datetime.now(datetime.timezone.utc)

    # ── Fill reverse capacity ─────────────────────────────────────────────────
    raw_reverse: dict[str, list] = {}
    for doc in backhaul_docs:
        data       = doc.to_dict()
        dest_depot = data.get('recipientGovernorate', 'unknown')
        raw_reverse.setdefault(dest_depot, []).append((doc.id, data))

    accepted_backhaul, bk_vol, bk_wt = _fill_capacity(
        raw_reverse, remaining_vol, remaining_wt, now
    )

    backhaul_order_ids = [oid for ids in accepted_backhaul.values() for oid, _ in ids]
    backhaul_payloads  = {did: [oid for oid, _ in items]
                          for did, items in accepted_backhaul.items()}

    # ── Update run doc ────────────────────────────────────────────────────────
    run_ref.update({
        'status':           'RETURNING',
        'backhaulLoaded':   True,
        'backhaulOrderIds': backhaul_order_ids,
        'backhaulPayloads': backhaul_payloads,
        'backhaulVolumeCm3':bk_vol,
        'backhaulWeightKg': bk_wt,
    })

    # ── Update backhaul orders ────────────────────────────────────────────────
    batch = db.batch()
    for oid in backhaul_order_ids:
        batch.update(db.collection('orders').document(oid), {
            'status':              'in_transit_inter_city',
            'currentRunId':        run_id,
            'assignedDriverId': run_data.get('chauffeurId'),
        })
    batch.commit()

    print(f"[CT-Backhaul] {run_id} | {dest_central}->{origin_central} "
          f"| {len(backhaul_order_ids)} orders loaded "
          f"| vol:{bk_vol/MAX_VOLUME_CM3:.0%}")
    return {
        'backhaulLoaded': True,
        'count':          len(backhaul_order_ids),
        'message':        f"Loaded {len(backhaul_order_ids)} return orders for {origin_central}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ④ SMART HYBRID DEPOT TOUR ENGINE  (unchanged from v2)
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_depot_tour(central_id: str) -> int:
    """
    Smart Hybrid Depot Routing Engine.
    Combines delivery (central→depots) + pickup (depots→central) in one circuit.
    Includes opportunistic stop injection and capacity-aware filling.
    See full docstring in v2.
    """
    if not db:
        return 0

    central_info = CENTRAL_REGISTRY.get(central_id)
    if not central_info:
        return 0

    satellites = set(CENTRAL_SATELLITES.get(central_id, []))
    now        = datetime.datetime.now(datetime.timezone.utc)

    # Delivery orders
    delivery_docs = list(
        db.collection('orders')
        .where(filter=FieldFilter('status', '==', 'ready_to_deliver'))
        .where(filter=FieldFilter('destCentral', '==', central_id))
        .stream()
    )
    # Sort in memory by createdAt
    delivery_docs.sort(key=lambda d: d.to_dict().get('createdAt') or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
    delivery_by_depot: dict[str, list] = {}
    oldest_time = None
    for doc in delivery_docs:
        data     = doc.to_dict()
        dest_dep = data.get('recipientGovernorate')
        if dest_dep not in satellites:
            continue
        delivery_by_depot.setdefault(dest_dep, []).append((doc.id, data))
        ca = data.get('createdAt')
        if ca and (oldest_time is None or ca < oldest_time):
            oldest_time = ca

    # Pickup orders
    pickup_docs = list(
        db.collection('orders')
        .where(filter=FieldFilter('status', '==', 'ready_to_collect'))
        .where(filter=FieldFilter('originCentral', '==', central_id))
        .order_by('createdAt')
        .stream()
    )
    pickup_by_depot: dict[str, list] = {}
    for doc in pickup_docs:
        data        = doc.to_dict()
        origin_dep  = data.get('senderGovernorate')
        if origin_dep not in satellites:
            continue
        pickup_by_depot.setdefault(origin_dep, []).append((doc.id, data))
        ca = data.get('createdAt')
        if ca and (oldest_time is None or ca < oldest_time):
            oldest_time = ca

    if not delivery_by_depot and not pickup_by_depot:
        return 0

    wait_min = (now - oldest_time).total_seconds() / 60.0 if oldest_time else 0.0

    if len(delivery_by_depot) < 4 and len(pickup_by_depot) < 2 and wait_min < SLA_INTRA_CENTRAL_MIN:
        return 0

    trigger = ('COVERAGE' if (len(delivery_by_depot) >= 4 or len(pickup_by_depot) >= 2)
               else 'SLA')

    # Merge and fill
    all_raw: dict[str, list] = {}
    for did, items in delivery_by_depot.items():
        all_raw.setdefault(did, []).extend(items)
    for did, items in pickup_by_depot.items():
        all_raw.setdefault(did, []).extend(items)

    accepted_del, used_vol, used_wt = _fill_capacity(
        delivery_by_depot, MAX_VOLUME_CM3, MAX_WEIGHT_KG, now
    )
    remaining_vol = MAX_VOLUME_CM3 - used_vol
    remaining_wt  = MAX_WEIGHT_KG  - used_wt

    accepted_pk, pk_vol, pk_wt = _fill_capacity(
        pickup_by_depot, remaining_vol, remaining_wt, now
    )
    used_vol += pk_vol
    used_wt  += pk_wt
    remaining_vol -= pk_vol
    remaining_wt  -= pk_wt

    confirmed_depots = set(accepted_del.keys()) | set(accepted_pk.keys())

    # Opportunistic injection
    opportunistic: list[str] = []
    non_active = [did for did in satellites if did not in confirmed_depots]
    if non_active and confirmed_depots:
        base_coords = (
            [(central_info['lat'], central_info['lng'])]
            + [(DEPOT_REGISTRY[d]['lat'], DEPOT_REGISTRY[d]['lng']) for d in confirmed_depots]
            + [(central_info['lat'], central_info['lng'])]
        )
        for candidate in non_active:
            cand_ref = (
                db.collection('orders')
                .where(filter=FieldFilter('status', '==', 'ready_to_collect'))
                .where(filter=FieldFilter('senderGovernorate', '==', candidate))
                .order_by('createdAt').limit(1)
            )
            cdocs = list(cand_ref.stream())
            if not cdocs:
                continue
            ca = cdocs[0].to_dict().get('createdAt')
            if not ca or (now - ca).total_seconds() / 60.0 < SLA_URGENT_MIN:
                continue
            cdep    = DEPOT_REGISTRY[candidate]
            detour  = _cheapest_insertion_detour(base_coords, (cdep['lat'], cdep['lng']))
            if detour > OPP_PICKUP_DETOUR_KM:
                continue
            for odoc in db.collection('orders')\
                    .where(filter=FieldFilter('status', '==', 'ready_to_collect'))\
                    .where(filter=FieldFilter('senderGovernorate', '==', candidate)).stream():
                odata = odoc.to_dict()
                v = _get_order_volume(odata)
                w = odata.get('weight', 0.0)
                if remaining_vol - v >= 0 and remaining_wt - w >= 0:
                    accepted_pk.setdefault(candidate, []).append((odoc.id, odata))
                    remaining_vol -= v
                    remaining_wt  -= w
                    used_vol      += v
                    used_wt       += w
            if candidate in accepted_pk:
                confirmed_depots.add(candidate)
                opportunistic.append(candidate)

    stops_for_osrm = [
        {'id': did, 'lat': DEPOT_REGISTRY[did]['lat'], 'lng': DEPOT_REGISTRY[did]['lng']}
        for did in confirmed_depots
    ]
    ordered_depot_ids = _osrm_optimize(
        (central_info['lat'], central_info['lng']), stops_for_osrm
    )

    chauffeur_id = select_best_chauffeur(
        central_info['lat'], central_info['lng'], run_type='DEPOT_TOUR'
    )
    if not chauffeur_id:
        print(f"[DT] No chauffeur for {central_id}")
        return 0

    delivery_payloads = {did: [o for o, _ in items] for did, items in accepted_del.items()}
    pickup_payloads   = {did: [o for o, _ in items] for did, items in accepted_pk.items()}

    all_del_ids = [o for ids in delivery_payloads.values() for o in ids]
    all_pk_ids  = [o for ids in pickup_payloads.values()   for o in ids]
    all_oids    = list(set(all_del_ids + all_pk_ids))

    stop_manifest = []
    for did in ordered_depot_ids:
        has_del = did in delivery_payloads
        has_pk  = did in pickup_payloads
        if not has_del and not has_pk:
            continue
        stop_manifest.append({
            'depotId':         did,
            'depotName':       DEPOT_REGISTRY[did]['name'],
            'lat':             DEPOT_REGISTRY[did]['lat'],
            'lng':             DEPOT_REGISTRY[did]['lng'],
            'action':          ('BOTH' if has_del and has_pk
                                else 'DELIVERY' if has_del else 'PICKUP'),
            'deliverOrderIds': delivery_payloads.get(did, []),
            'pickupOrderIds':  pickup_payloads.get(did, []),
            'isOpportunistic': did in opportunistic,
        })

    run_ref = db.collection('chauffeur_runs').document()
    run_ref.set({
        'type':               'DEPOT_TOUR',
        'triggerType':        trigger,
        'status':             'pending',
        'currentStopIndex':   0,
        'centralId':          central_id,
        'chauffeurId':        chauffeur_id,
        'driverId':           chauffeur_id,
        'stops':              [central_id] + ordered_depot_ids + [central_id],
        'stopManifest':       stop_manifest,
        'deliveryPayloads':   delivery_payloads,
        'pickupPayloads':     pickup_payloads,
        'orderIds':           all_oids,
        'totalDeliveries':    len(all_del_ids),
        'totalPickups':       len(all_pk_ids),
        'totalVolumeCm3':     used_vol,
        'totalWeightKg':      used_wt,
        'opportunisticStops': opportunistic,
        'remainingVolumeCm3': MAX_VOLUME_CM3 - used_vol,
        'remainingWeightKg':  MAX_WEIGHT_KG  - used_wt,
        'rerouteAllowed':     True,
        'waitMinutes':        round(wait_min, 1),
        'createdAt':          firestore.SERVER_TIMESTAMP,
    })

    db.collection('users').document(chauffeur_id).update({
        'chauffeurState': 'ON_DEPOT_TOUR',
        'currentRunId':   run_ref.id,
    })

    batch = db.batch()
    for oid in all_del_ids:
        batch.update(db.collection('orders').document(oid), {
            'status': 'in_transit_inter_city', 'currentRunId': run_ref.id,
            'assignedDriverId': chauffeur_id,
        })
    for oid in all_pk_ids:
        batch.update(db.collection('orders').document(oid), {
            'status': 'in_transit_inter_city', 'currentRunId': run_ref.id,
            'assignedDriverId': chauffeur_id,
        })
    batch.commit()

    print(f"[DT] {run_ref.id} | {central_id} | stops:{ordered_depot_ids} "
          f"| del:{len(all_del_ids)} pk:{len(all_pk_ids)} opp:{opportunistic}")
    return 1


# ═══════════════════════════════════════════════════════════════════════════════
# ⑤ DYNAMIC REROUTING  (mid-tour, called by driver app or GPS Pub/Sub)
# ═══════════════════════════════════════════════════════════════════════════════

def reroute_depot_tour(run_id: str, chauffeur_lat: float, chauffeur_lng: float) -> dict:
    """
    Re-evaluates remaining stops for an active DEPOT_TOUR.
    Injects nearby/urgent satellites, re-optimises with OSRM from current GPS.
    Updates run doc: remainingStops, pickupPayloads, stopManifest, rerouteCount.
    """
    if not db:
        return {'rerouteApplied': False, 'newStops': [], 'message': 'DB not connected'}

    run_ref = db.collection('chauffeur_runs').document(run_id)
    run_doc = run_ref.get()
    if not run_doc.exists:
        return {'rerouteApplied': False, 'newStops': [], 'message': 'Run not found'}

    run_data      = run_doc.to_dict()
    central_id    = run_data.get('centralId')
    central_info  = CENTRAL_REGISTRY.get(central_id, {})
    satellites    = set(CENTRAL_SATELLITES.get(central_id, []))

    if run_data.get('status') != 'ASSIGNED' or not run_data.get('rerouteAllowed', True):
        return {'rerouteApplied': False, 'newStops': [], 'message': 'Reroute not allowed'}

    stop_manifest    = run_data.get('stopManifest', [])
    remaining_depots = [s['depotId'] for s in stop_manifest if s.get('status') != 'DONE']
    current_pickups  = run_data.get('pickupPayloads', {})
    remaining_vol    = run_data.get('remainingVolumeCm3', MAX_VOLUME_CM3)
    remaining_wt     = run_data.get('remainingWeightKg',  MAX_WEIGHT_KG)
    reroute_count    = run_data.get('rerouteCount', 0)
    now              = datetime.datetime.now(datetime.timezone.utc)

    planned       = set(remaining_depots)
    new_stops     = []

    for candidate in satellites - planned:
        cdep = DEPOT_REGISTRY[candidate]
        dist = _haversine(chauffeur_lat, chauffeur_lng, cdep['lat'], cdep['lng'])

        new_ref = (
            db.collection('orders')
            .where(filter=FieldFilter('status', '==', 'ready_to_collect'))
            .where(filter=FieldFilter('senderGovernorate', '==', candidate))
            .order_by('createdAt').limit(1)
        )
        ndocs = list(new_ref.stream())
        if not ndocs:
            continue
        ca    = ndocs[0].to_dict().get('createdAt')
        urgent = ca and (now - ca).total_seconds() / 60.0 >= SLA_URGENT_MIN

        if dist > OPPORTUNISTIC_PROX_KM and not urgent:
            continue

        route_coords = (
            [(chauffeur_lat, chauffeur_lng)]
            + [(DEPOT_REGISTRY[d]['lat'], DEPOT_REGISTRY[d]['lng']) for d in remaining_depots]
            + [(central_info['lat'], central_info['lng'])]
        )
        detour = _cheapest_insertion_detour(route_coords, (cdep['lat'], cdep['lng']))
        if detour > OPP_PICKUP_DETOUR_KM:
            continue

        added = []
        for odoc in db.collection('orders')\
                .where(filter=FieldFilter('status', '==', 'ready_to_collect'))\
                .where(filter=FieldFilter('senderGovernorate', '==', candidate)).stream():
            odata = odoc.to_dict()
            v = _get_order_volume(odata)
            w = odata.get('weight', 0.0)
            if remaining_vol - v >= 0 and remaining_wt - w >= 0:
                added.append(odoc.id)
                remaining_vol -= v
                remaining_wt  -= w
        if not added:
            continue

        current_pickups[candidate] = current_pickups.get(candidate, []) + added
        remaining_depots.append(candidate)
        planned.add(candidate)
        new_stops.append(candidate)
        stop_manifest.append({
            'depotId': candidate, 'depotName': cdep['name'],
            'lat': cdep['lat'], 'lng': cdep['lng'],
            'action': 'PICKUP', 'deliverOrderIds': [],
            'pickupOrderIds': added, 'isOpportunistic': True, 'addedByReroute': True,
        })

    reordered = _osrm_optimize(
        (chauffeur_lat, chauffeur_lng),
        [{'id': d, 'lat': DEPOT_REGISTRY[d]['lat'], 'lng': DEPOT_REGISTRY[d]['lng']}
         for d in remaining_depots]
    )

    run_ref.update({
        'remainingStops':     reordered,
        'pickupPayloads':     current_pickups,
        'stopManifest':       stop_manifest,
        'remainingVolumeCm3': remaining_vol,
        'remainingWeightKg':  remaining_wt,
        'rerouteCount':       reroute_count + 1,
        'lastRerouteAt':      firestore.SERVER_TIMESTAMP,
        'opportunisticStops': list(
            set(run_data.get('opportunisticStops', [])) | set(new_stops)
        ),
    })

    if new_stops:
        batch = db.batch()
        for did in new_stops:
            for oid in current_pickups.get(did, []):
                batch.update(db.collection('orders').document(oid), {
                    'status': 'in_transit_inter_city',
                    'currentRunId': run_id,
                    'assignedDriverId': run_data.get('chauffeurId'),
                })
        batch.commit()

    msg = (f"Rerouted: added {new_stops}, reordered: {reordered}"
           if new_stops else f"Reoptimised: {reordered}")
    print(f"[Reroute] {run_id} | {msg}")
    return {'rerouteApplied': True, 'newStops': new_stops, 'message': msg}
