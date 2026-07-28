#!/bin/bash
set -e

echo "Setting up global Nginx security configs..."
sudo tee /etc/nginx/conf.d/security.conf > /dev/null << 'GLOBAL_CONFIG'
server_tokens off;
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=global:10m rate=20r/s;
GLOBAL_CONFIG

echo "Setting up makemystay config..."
sudo tee /etc/nginx/sites-available/makemystay > /dev/null << 'CONFIG'
server {
    listen 80;
    server_name makemystay.ai www.makemystay.ai;
    return 301 https://makemystay.ai$request_uri;
}

server {
    listen 443 ssl default_server;
    server_name makemystay.ai www.makemystay.ai;

    ssl_certificate /etc/letsencrypt/live/makemystay.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/makemystay.ai/privkey.pem;

    # Global Rate Limiting Layer
    limit_req zone=global burst=50 nodelay;

    # Block bad user agents
    if ($http_user_agent ~* (sqlmap|nikto|curl|wget)) {
        return 403;
    }

    # Block suspicious queries
    if ($query_string ~* "(union|select|drop|insert)") {
        return 403;
    }

    # React frontend
    location / {
        root /var/www/react-app;
        index index.html;
        try_files $uri /index.html;
    }

    # API backend
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
CONFIG

echo "Linking config and removing default..."
sudo ln -sf /etc/nginx/sites-available/makemystay /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

echo "Removing extra default_server from admin..."
sudo sed -i 's/listen 443 ssl default_server/listen 443 ssl/g' /etc/nginx/sites-available/makemystay-admin
echo "Removing extra default_server from api..."
sudo sed -i 's/listen 443 ssl default_server/listen 443 ssl/g' /etc/nginx/sites-available/makemystay-api

echo "Running certbot..."
sudo certbot --nginx -d makemystay.ai -d www.makemystay.ai --non-interactive --agree-tos -m admin@makemystay.ai --keep-until-expiring

echo "Testing nginx and restarting..."
sudo nginx -t
sudo systemctl restart nginx
echo "Done!"
