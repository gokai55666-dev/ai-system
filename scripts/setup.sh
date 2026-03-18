#!/data/data/com.termux/files/usr/bin/bash

echo "Updating system..."
pkg update -y && pkg upgrade -y

echo "Installing python deps..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete."