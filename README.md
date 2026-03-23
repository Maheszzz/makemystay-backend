
<div align="center">
  <h1>MakeMyStay.ai - Backend API</h1>
  <p>The robust FastAPI backend powering the first AI-native revenue engine for co-living and rental operators.</p>

  <p>
    <a href="https://fastapi.tiangolo.com/">
      <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI" />
    </a>
    <a href="https://www.python.org/">
      <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    </a>
    <a href="https://www.sqlalchemy.org/">
      <img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy" />
    </a>
    <a href="https://www.mysql.com/">
      <img src="https://img.shields.io/badge/MySQL-4479A1?style=for-the-badge&logo=mysql&logoColor=white" alt="MySQL" />
    </a>
  </p>
</div>

---

## 🚀 Features

- **High Performance API**: Built with FastAPI for speed and efficiency.
- **Relational Data Management**: Powered by SQLAlchemy ORM and MySQL.
- **Data Validation**: Strict type checking and validation using Pydantic schemas.
- **Secure Endpoints**: API endpoints for property management, contacts, and services.
- **Scripting Support**: Automated scripts for bulk property insertion and updates.

## 🛠️ Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Language**: [Python 3.10+](https://www.python.org/) (production; **3.9** is OK locally if annotations use `typing.Optional` / `Union` — avoid `X | None` in type hints, which requires 3.10+)
- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/)
- **Database**: [MySQL](https://www.mysql.com/)
- **Server**: [Uvicorn](https://www.uvicorn.org/)
- **Validation**: [Pydantic](https://docs.pydantic.dev/)

## 📦 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd no-broker-backend
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Copy the example environment file and configure your credentials:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your database details:
   ```env
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=makemystay
   ```

5. **Start the server**
   ```bash
   python3 -m uvicorn app.main:app --reload
   ```
   The API will be available at `http://localhost:8000`.

## 📚 API Documentation

Once the server is running, you can access the interactive API documentation:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## 📂 Project Structure

```bash
no-broker-backend/
├── app/
│   ├── main.py          # Application entry point
│   ├── models/          # SQLAlchemy database models
│   ├── schemas/         # Pydantic schemas for validation
│   ├── api/             # API route handlers
│   ├── core/            # Core configuration and database setup
│   └── repo/            # Repository layer for DB interactions
├── insert_bulk_properties.py # Script to adding properties
├── update_bulk_properties.py # Script for updating property images
├── requirements.txt     # Python dependencies
└── .env                 # Environment variables
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is proprietary software. All rights reserved. © 2026 MakeMyStay.ai
