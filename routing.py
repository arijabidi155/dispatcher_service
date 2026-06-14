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
    
    # Using public OSRM API for Driving TSP: start at first coordinate (depot), end at any optimal last stop, no roundtrip
    url = f"http://router.project-osrm.org/trip/v1/driving/{coords_str}?source=first&destination=any&roundtrip=false&steps=false"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 'Ok':
                waypoints = data['waypoints']
                
                # OSRM waypoints array is sorted by input coordinate index.
                # waypoint_index is the optimized position of that input point inside the trip.
                # Create a list of tuples: (input_index, optimized_index)
                indexed_waypoints = []
                for i, wp in enumerate(waypoints):
                    indexed_waypoints.append((i, wp['waypoint_index']))
                
                # Sort the list by optimized_index (waypoint_index)
                indexed_waypoints.sort(key=lambda x: x[1])
                
                # Re-order the original stops, skipping the depot (input_index 0)
                optimized_stops = []
                for input_idx, opt_idx in indexed_waypoints:
                    if input_idx > 0:
                        optimized_stops.append(stops[input_idx - 1])
                
                return [stop['id'] for stop in optimized_stops]
    except Exception as e:
        print(f"OSRM Error: {e}")
        
    # Fallback to original order if optimization fails
    return [stop['id'] for stop in stops]
