#!/data/data/com.termux/files/usr/bin/bash
# ONE-CLICK INSTALLER for Smart Router
# Run: chmod +x install.sh && ./install.sh

set -e  # Exit on error

echo "🚀 Starting Smart Router Installation..."
echo "======================================"

# Step 1: Environment check
echo "📱 Checking Termux environment..."
if [ ! -d "/data/data/com.termux/files" ]; then
    echo "❌ Not running in Termux! Exiting."
    exit 1
fi

# Step 2: Update packages
echo "⬇️ Updating packages (this may take 5 mins)..."
pkg update -y > /dev/null 2>&1 && echo "✅ Updated" || echo "⚠️ Update skipped"

# Step 3: Install dependencies
echo "📦 Installing Python and dependencies..."
pkg install -y python git > /dev/null 2>&1
pip install -q requests pyyaml python-dotenv

# Step 4: Directory structure
echo "📁 Creating directories..."
mkdir -p ~/ai-system-gpu/{src,configs,logs,outputs}
cd ~/ai-system-gpu

# Step 5: Create router code (HERE document)
echo "📝 Creating Smart Router..."
cat > src/smart_router.py << 'PYEOF'
[PASTE THE PYTHON CODE FROM ABOVE HERE]
PYEOF

# Step 6: Create config
echo "⚙️ Creating configuration..."
cat > configs/router.yaml << 'YAMLEOF'
endpoints:
  local:
    url: http://localhost:11434/api/generate
    model: samantha-1.11-70b
    is_local: true
    supports_uncensored: true
    timeout: 60
  cloud:
    url: https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/openai/v1/chat/completions
    model: openchat/openchat-3.6-8b
    is_local: false
    supports_uncensored: false
    timeout: 30
routing:
  default: cloud
  nsfw_fallback: local
  cost_tracking: true
YAMLEOF

# Step 7: Create .env template
echo "🔐 Creating environment template..."
cat > .env << 'ENVEOF'
# RunPod Credentials (get from runpod.io/console)
RUNPOD_API_KEY=your_api_key_here
RUNPOD_ENDPOINT_ID=your_endpoint_id_here

# Optional: Local Ollama settings
OLLAMA_HOST=http://localhost:11434
ENVEOF

# Step 8: Create launcher
echo "🎮 Creating launcher..."
cat > run.sh << 'RUNEOF'
#!/bin/bash
cd ~/ai-system-gpu
source .env 2>/dev/null || echo "⚠️ No .env file loaded"
python src/smart_router.py
RUNEOF
chmod +x run.sh

# Step 9: Create quick test
echo "🧪 Creating test script..."
cat > test.sh << 'TESTEOF'
#!/bin/bash
echo "Testing Smart Router setup..."
python3 -c "import requests, yaml; print('✅ Dependencies OK')"
ls -la src/smart_router.py && echo "✅ Router code exists"
ls -la configs/router.yaml && echo "✅ Config exists"
echo ""
echo "Next steps:"
echo "1. Edit .env with your RunPod API key"
echo "2. Start Freedom-AI locally (for uncensored mode)"
echo "3. Run: ./run.sh"
TESTEOF
chmod +x test.sh

echo ""
echo "======================================"
echo "✅ Installation Complete!"
echo ""
echo "📋 NEXT STEPS:"
echo "1. Get RunPod API key: https://www.runpod.io/console"
echo "   → Settings → API Keys → Create"
echo "2. Deploy vLLM endpoint (copy the Endpoint ID)"
echo "3. Edit ~/.env file with your credentials"
echo "4. Run: ./test.sh (to verify)"
echo "5. Run: ./run.sh (to start)"
echo ""
echo "🆘 Commands inside router:"
echo "   /local - Force local (uncensored)"
echo "   /cloud - Force cloud (fast)"
echo "   /stats - Show usage stats"
echo "   /quit  - Exit"
