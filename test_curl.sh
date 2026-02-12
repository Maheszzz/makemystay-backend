#!/bin/bash

echo "Testing with 127.0.0.1..."
curl -X POST "http://[IP_ADDRESS]/api/v1/realty/properties" \
     -H "Content-Type: application/json" \
     -d '{
           "property_name": "Curl Test Villa",
           "location": "Curl Location",
           "phone": "1234567890",
           "property_type": "2BHK",
           "listing_type": "rent",
           "private_price": 15000.0,
           "description": "Created via curl"
         }'
echo -e "\n\nTesting with localhost..."
curl -X POST "http://[IP_ADDRESS]/api/v1/realty/properties" \
     -H "Content-Type: application/json" \
     -d '{
           "property_name": "Curl Localhost Villa",
           "location": "Curl Location",
           "phone": "0987654321",
           "property_type": "2BHK",
           "listing_type": "rent",
           "private_price": 15000.0,
           "description": "Created via curl localhost"
         }'
echo -e "\nDone."
