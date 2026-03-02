#!/bin/bash

# Activate virtual environment and run the memo app
cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Installing customtkinter..."
    pip install customtkinter
else
    source venv/bin/activate
fi

# Run the app
echo "Starting Memit Memo App..."
python memo_app.py
