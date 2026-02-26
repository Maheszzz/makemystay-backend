import requests
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzZG1pbkBTYWtlTXlzdGF5LmFwIiwiZXhwIjoxNzQzMTQ2ODE3fQ.Zxhw1joxNzc0NjAyOTkyfQ.bNw_OJddge8fY1X6ZsYaF4DWG3kKrzjiG38Vh9ExXjM"
headers = {"Authorization": f"Bearer {token}"}
payload = {"image_url": "https://xyz.com/image.jpg", "is_primary": False, "sort_order": 0}
res = requests.post("http://localhost:8000/api/v1/realty/properties/77/images", json=payload, headers=headers)
print(res.status_code, res.text)
