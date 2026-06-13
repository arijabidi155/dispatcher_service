import requests

def optimize_route(depot_coords, stops):
    """
    Calls OSRM to solve the TSP and returns the ordered sequence of stops.
    stops is a list of dicts: [{'id': 'order_1', 'lat': 36.8, 'lng': 10.1}, ...]
    depot_coords is a tuple: (lat, lng)
    """
    if not stops:
        return []

    # OSRM expects coordinates in "longitude,latitude" format
    coords_list = [f"{depot_coords[1]},{depot_coords[0]}"] # Start at depot
    
    for stop in stops:
        coords_list.append(f"{stop['lng']},{stop['lat']}")
        
    coords_str = ";".join(coords_list)
    
    # Using public OSRM API for Driving TSP
    url = f"http://router.project-osrm.org/trip/v1/driving/{coords_str}?source=first&destination=last&roundtrip=true&steps=false"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 'Ok':
                # Parse the waypoints to get the optimized order
                waypoints = data['waypoints']
                # waypoints[0] is the source (depot). The rest are the stops.
                # OSRM returns waypoints with a 'waypoint_index' mapping original index to optimized index
                
                # We want to re-order our original 'stops' list based on OSRM's optimization
                # waypoints correspond to the input coordinates
                # Skip the first waypoint (depot)
                stop_waypoints = waypoints[1:]
                
                # Sort the original stops based on the 'waypoint_index' of the returned waypoints
                # Actually, the returned waypoints list is already in the *optimized* order?
                # No, the 'waypoints' array corresponds to the input coordinates.
                # We need to sort by 'waypoint_index'.
                
                # OSRM returns waypoints in the optimized order.
                # waypoint_index indicates the index of the coordinate in the input list.
                # Since the first input coordinate is the depot (index 0), stops are shifted by -1.
                optimized_stops = []
                for wp in waypoints:
                    input_idx = wp['waypoint_index']
                    if input_idx > 0:
                        optimized_stops.append(stops[input_idx - 1])
                
                return [stop['id'] for stop in optimized_stops]
    except Exception as e:
        print(f"OSRM Error: {e}")
        
    # Fallback to original order if optimization fails
    return [stop['id'] for stop in stops]
