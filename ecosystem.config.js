module.exports = {
  apps: [
    {
      name: "makemystay-api",
      script: "/home/ubuntu/app/venv/bin/python",
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2",
      instances: 1,
      exec_mode: "fork",
      cwd: "/home/ubuntu/app",
      env: {
        ENV: "production",
        LEAD_PULL_SYNC_ENABLED: "true"
      },
      env_file: ".env.production",
      autorestart: true,
      max_restarts: 5,
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
      max_restarts: 5,
      watch: false
    }
  ]
};
