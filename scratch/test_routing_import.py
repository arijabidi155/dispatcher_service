import os
import sys

# Add parent dir to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routing import optimize_route

# Mock data
depot = (36.8065, 10.1815) # Tunis Center
stops_data = [
    {'id': 'Stop_A_Far', 'lat': 36.8625, 'lng': 10.2987}, # La Marsa (Farther)
    {'id': 'Stop_B_Close', 'lat': 36.8189, 'lng': 10.1654}, # Bardo (Very Close)
    {'id': 'Stop_C_Medium', 'lat': 36.8432, 'lng': 10.1978}, # Ariana (Medium)
]

print("Imported optimize_route successfully!")
optimized = optimize_route(depot, stops_data)
print("Optimized order of stops:", optimized)
