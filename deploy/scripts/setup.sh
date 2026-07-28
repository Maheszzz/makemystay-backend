#!/bin/bash

echo "🚀 Setting up no-broker-backend environment..."

# 1. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    python3 -m venv .venv
else
    echo "✅ Virtual environment already exists."
fi

# 2. Activate virtual environment
echo "🔄 Activating virtual environment..."
source .venv/bin/activate

# 3. Upgrade pip to the latest version to avoid build errors 
# (e.g., packages like cryptography or pydantic core that require newer pip for pre-built wheels)
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# 4. Install dependencies
echo "📥 Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo ""
echo "✨ Backend setup complete! ✨"
echo "To start the development server, run:"
echo "source .venv/bin/activate && python3 -m uvicorn app.main:app --reload"
