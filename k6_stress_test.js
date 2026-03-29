import http from 'k6/http';
import { check, sleep } from 'k6';

// Test Configuration
export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '1m', target: 50 },
    { duration: '2m', target: 100 },
    { duration: '1m', target: 0 },
  ],
  thresholds: {
    'http_req_duration{name:health}': ['p(95)<500'],
    'http_req_duration{name:properties}': ['p(95)<2000'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = 'https://api.makemystay.ai';

export default function () {
  // 1. Check Health Endpoint
  let res_health = http.get(`${BASE_URL}/health`, { tags: { name: 'health' } });
  check(res_health, {
    'health status is 200': (r) => r.status === 200,
    'health checks passing': (r) => {
      try {
        return r.json('status') === 'healthy';
      } catch (e) {
        return false;
      }
    },
  });

  // 2. Load Test Properties (Simulating Homepage Load)
  let res_props = http.get(`${BASE_URL}/api/v1/realty/properties?limit=24`, {
    tags: { name: 'properties' },
  });
  check(res_props, {
    'properties status is 200': (r) => r.status === 200,
  });

  // Pause between iterations to simulate real user think time
  sleep(1);
}
