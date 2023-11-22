import requests
import json

# Virtualizor API details
api_url = "https://65.108.106.177:4085/index.php?act=vs"
api_key = "A2m11jXLBTH4E3o4id7LTj6CwQX6IsTO"
api_pass = "aTLjtHzbJCjxrpbukhEDRZI7Z7QOQx2f"

# Parameters for the API request
params = {
    'apikey': api_key,
    'apipass': api_pass,
    'vpsname': 'v2228',  # Specify if you want to query a specific VPS
    # Add other parameters as needed
}

# Make the GET request to the Virtualizor API
response = requests.get(api_url, params=params, verify=False)  # Set verify=False if SSL certificate issues

# Parse the JSON response
data = response.json()

# Process the response data
# Example: print all VPS IPs
print(response.text)
# print(f"{data}")