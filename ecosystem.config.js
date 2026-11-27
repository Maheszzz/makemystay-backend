module.exports = {
  apps: [
    {
      name: "makemystay-api",
      script: "/home/ubuntu/app/venv/bin/python",
      args: "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips 127.0.0.1",
      instances: 1,
      exec_mode: "fork",
      cwd: "/home/ubuntu/app",
      env: {
        ENV: "production",
        LEAD_PULL_SYNC_ENABLED: "true"
      },
      env_file: ".env.production",
      autorestart: true,
      // Avoid giving up after a few boot-time crashes (would leave nginx with 502 until manual pm2 restart).
      max_restarts: 50,
      min_uptime: "8s",
      restart_delay: 4000,
      watch: false
    },
    {
      name: "makemystay-celery",
      script: "/home/ubuntu/app/venv/bin/python",
      args: "-m celery -A app.core.celery_app worker --loglevel=info --concurrency=4",
      instances: 1,
      exec_mode: "fork",
      cwd: "/home/ubuntu/app",
      env: {
        ENV: "production",
        LEAD_PULL_SYNC_ENABLED: "true"
      },
      env_file: ".env.production",
      autorestart: true,
      max_restarts: 50,
      min_uptime: "8s",
      restart_delay: 4000,
      watch: false
    }
  ]
};
