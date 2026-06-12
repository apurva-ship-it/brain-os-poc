#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"

echo "=== Brain OS POC ==="

# Check .env
if [ ! -f "$BACKEND/.env" ]; then
  echo "Creating .env from template..."
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  echo ""
  echo "⚠  Add your Anthropic API key to $BACKEND/.env"
  echo "   ANTHROPIC_API_KEY=sk-ant-..."
  echo ""
fi

# Check python
if ! command -v python3 &> /dev/null; then
  echo "Python3 not found"; exit 1
fi

# Create venv if needed
if [ ! -d "$BACKEND/venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$BACKEND/venv"
fi

source "$BACKEND/venv/bin/activate"

echo "Installing dependencies..."
pip install -q -r "$BACKEND/requirements.txt"

echo ""
echo "Starting Brain OS POC on http://localhost:8000"
echo "Open http://localhost:8000 in your browser"
echo ""

cd "$BACKEND"
python main.py
