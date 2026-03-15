#!/bin/bash

echo "============================================"
echo "🛡️  Obscura - Mac Setup Script"
echo "============================================"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install it first (brew install python)."
    exit 1
fi

echo "✅ Python 3 detected"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
else
    echo "📦 Virtual environment already exists"
fi

# Activate venv
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
if [ -f "requirements.txt" ]; then
    echo "📥 Installing dependencies..."
    pip install -r requirements.txt
else
    echo "❌ requirements.txt not found!"
    exit 1
fi

echo "============================================"
echo "🎉 Setup Complete!"
echo "============================================"
echo ""
echo "To run the Obscura Backend:"
echo "1. source venv/bin/activate"
echo "2. python main.py"
echo ""
echo "Then load the 'obscura-chrome-extension' folder in Chrome."
