#!/bin/bash
# DEBUGGED SETUP SCRIPT v1.1
# Cross-referenced with freedom-ai/install.sh best practices

set -e  # Exit on error

WORKSPACE="/workspace/ai-system-gpu"
echo "🚀 Setting up Smart Router (Debugged)..."

# 1. System setup
mkdir -p $WORKSPACE/{src,configs,logs,models}
cd $WORKSPACE

# 2. Install Ollama properly (with wait)
echo "📦 Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "⏳ Starting Ollama service..."
ollama serve > /tmp/ollama.log 2>&1 &

# BUG FIX: Wait for Ollama to be ready (from freedom-ai install.sh)
echo "⏳ Waiting for Ollama API..."
for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "✅ Ollama ready!"
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

# 3. Pull model with error handling
echo "📥 Pulling Samantha model..."
if ollama pull samantha; then
    echo "✅ Model ready"
else
    echo "⚠️ Failed to pull 'samantha', trying alternatives..."
    ollama pull openchat || echo "⚠️ Will use default model"
fi

# 4. Install Python deps
pip install -q requests pyyaml python-dotenv

# 5. Create debugged config
cat > configs/router.yaml << 'EOF'
endpoints:
  local:
    url: http://localhost:11434/api/chat
    model: samantha
    is_local: true
    supports_uncensored: true
    timeout: 120
  cloud:
    url: https://api.runpod.ai/v2/{endpoint_id}/openai/v1/chat/completions
    model: openchat/openchat-3.6-8b
    is_local: false
    supports_uncensored: false
    timeout: 60
routing:
  default: cloud
  cost_tracking: true
  max_retries: 3
EOF

# 6. Create .env template
cat > .env << 'EOF'
RUNPOD_API_KEY=your_key_here
RUNPOD_ENDPOINT_ID=your_endpoint_here
EOF

echo ""
echo "✅ Setup complete!"
echo ""
echo "NEXT STEPS:"
echo "1. Edit .env with your RunPod credentials"
echo "2. Run: python src/smart_router_fixed.py"
echo ""
echo "TROUBLESHOOTING:"
echo "- Check Ollama: curl http://localhost:11434/api/tags"
echo "- Check RunPod: https://www.runpod.io/console/serverless"
