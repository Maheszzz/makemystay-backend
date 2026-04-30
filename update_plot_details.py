import requests

API_BASE = "http://127.0.0.1:8000/api/v1/realty"


def update_plot():
    plot_data = {
        "property_name": "Premium Residential Plot",
        "location": "Jigani, Anekal main road banglore",
        "city": "bangalore",
        "starting_price": 3600000.0,
        "description": "Plots Size - 1200sq ft to 2400sq ft • Price - 3000/- per sq ft • Total 11 Plots available • Location - Jigani, Anekal main road banglore",
        "features": ["1200 - 2400 sq ft", "11 Plots Available", "₹3000/sq ft"],
    }

    # We update property 68
    response = requests.put(f"{API_BASE}/properties/68", json=plot_data)
    if response.status_code == 200:
        print("✅ Successfully updated property 68!")
    else:
        print(f"❌ Failed to update property. Status: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    update_plot()
