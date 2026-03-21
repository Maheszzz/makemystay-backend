module.exports = {
  apps: [
    {
      name: "makemystay-api",
      script: "venv/bin/uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8000 --workers 4 --env-file .env.production",
      instances: 1,
      exec_mode: "fork",
      interpreter: "venv/bin/python",
      cwd: "/home/ubuntu/app",
      env_file: ".env.production",
      autorestart: true,
      max_restarts: 5,
      watch: false
    },
    {
      name: "makemystay-celery",
      script: "venv/bin/celery",
      args: "-A app.core.celery_app worker --loglevel=info --concurrency=4",
      instances: 1,
      exec_mode: "fork",
      cwd: "/home/ubuntu/app",
      env_file: ".env.production",
      autorestart: true,
      max_restarts: 5,
      watch: false
    }
  ]
};
