#!/bin/bash
set -e

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

    # React frontend
    location / {
        root /var/www/react-app;
        index index.html;
        try_files $uri /index.html;
    }

    # API backend
    location /api/ {
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
