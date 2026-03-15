#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "============================================"
echo "🛡️  Starting Obscura..."
echo "============================================"

# Check if venv_new is valid (must have bin/activate on Mac)
if [ -d "venv_new" ] && [ ! -f "venv_new/bin/activate" ]; then
    echo "⚠️  Detected invalid virtual environment."
    echo "♻️  Recreating virtual environment for Mac..."
    rm -rf venv_new
fi

# Check if venv_new exists, if not run setup
if [ ! -d "venv_new" ]; then
    echo "⚙️  First time setup (or repair)..."
    # Note: setup_mac.sh might still create 'venv', so we handle it here manually or update setup_mac.sh
    # For now, let's just create it here if missing
    python3 -m venv venv_new
    source venv_new/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Double check
if [ ! -f "venv_new/bin/activate" ]; then
    echo "❌ Setup failed. Could not create virtual environment."
    read -p "Press Enter to exit..."
    exit 1
fi

# Activate virtual environment
source venv_new/bin/activate

# Run the application
echo "🚀 Launching Python Application..."
python main.py

# If it crashed, check if it was due to missing modules
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "⚠️  Application crashed. Checking for missing dependencies..."
    echo "📦 Installing/Updating requirements..."
    pip install -r requirements.txt
    
    echo ""
    echo "🚀 Relaunching..."
    python main.py
fi

# Keep window open if it crashes again
echo ""
echo "Application closed."
read -p "Press Enter to exit..."
