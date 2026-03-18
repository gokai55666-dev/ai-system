#!/data/data/com.termux/files/usr/bin/bash

# Termux base system update
echo "Updating Termux system..."
pkg update -y && pkg upgrade -y

# Install git and python if missing
echo "Ensuring git and python are installed..."
pkg install -y git python

# Upgrade pip to latest version
echo "Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies from requirements.txt
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Make folders for your workflow
echo "Creating folders..."
mkdir -p src scripts configs models prompts outputs logs

echo "Setup complete!"