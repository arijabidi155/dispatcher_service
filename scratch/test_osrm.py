import requests

def test_optimize_route(depot_coords, stops):
    if not stops:
        return []

    # Longitude,Latitude format
    coords_list = [f"{depot_coords[1]},{depot_coords[0]}"] # Start at depot
    for stop in stops:
        coords_list.append(f"{stop['lng']},{stop['lat']}")
        
    coords_str = ";".join(coords_list)
    
    url = f"http://router.project-osrm.org/trip/v1/driving/{coords_str}?source=first&destination=any&roundtrip=false&steps=false"
    
    print(f"Requesting OSRM URL: {url}")
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 'Ok':
                waypoints = data['waypoints']
                print("Raw Waypoints from OSRM:")
                for i, wp in enumerate(waypoints):
                    print(f"  Input Index {i}: snapped_coords={wp['location']}, waypoint_index={wp['waypoint_index']}")
                
                # Correct Sorting Logic:
                # 1. Zip input index and its optimized position (waypoint_index)
                indexed_waypoints = []
                for i, wp in enumerate(waypoints):
                    indexed_waypoints.append((i, wp['waypoint_index']))
                
                # 2. Sort by waypoint_index (optimized position)
                indexed_waypoints.sort(key=lambda x: x[1])
                
                print("\nSorted Waypoints (Optimized Trip Sequence):")
                for input_idx, opt_idx in indexed_waypoints:
                    print(f"  Optimized Position {opt_idx}: Input Index {input_idx}")
                
                # 3. Map to original stops list (excluding the depot at input index 0)
                optimized_stops = []
                for input_idx, opt_idx in indexed_waypoints:
                    if input_idx > 0:
                        optimized_stops.append(stops[input_idx - 1])
                
                return [stop['id'] for stop in optimized_stops]
            else:
                print(f"OSRM returned code: {data.get('code')}")
        else:
            print(f"OSRM HTTP Error: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    return [stop['id'] for stop in stops]

# Mock data
depot = (36.8065, 10.1815) # Tunis Center
stops_data = [
    {'id': 'Stop_A_Far', 'lat': 36.8625, 'lng': 10.2987}, # La Marsa (Farther)
    {'id': 'Stop_B_Close', 'lat': 36.8189, 'lng': 10.1654}, # Bardo (Very Close)
    {'id': 'Stop_C_Medium', 'lat': 36.8432, 'lng': 10.1978}, # Ariana (Medium)
]

print("Original order:", [s['id'] for s in stops_data])
optimized = test_optimize_route(depot, stops_data)
print("\nOptimized order of stops:", optimized)
