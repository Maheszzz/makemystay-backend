import requests
import json

base_url = "http://localhost:8000/api/v1"
headers = {"Authorization": "Bearer dummy"} # Actually I don't need auth if I can just query the DB directly, or I can use the API. Let's use the DB.
