const axios = require('axios');

async function test() {
  try {
    const res = await axios.post('http://localhost:8000/api/v1/realty/properties', {
      property_name: 'Test',
      property_type: 'PG',
      location: 'Bangalore',
      starting_price: 5000,
      listing_type: 'rent',
      phone: '9876543210'
    });
    console.log(res.data);
  } catch (e) {
    console.log(e.response?.status, e.response?.data);
  }
}
test();
