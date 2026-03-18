#!/bin/bash
# ONE-CLICK RUNPOD DEPLOYMENT
# Requires: RUNPOD_API_KEY env var

ENDPOINT_NAME="openchat-uncensored-bridge"
MODEL="openchat/openchat-3.6-8b"
GPU_TYPE="NVIDIA RTX 4090"

echo "🚀 Deploying to RunPod..."

# Install RunPod CLI if missing
if ! command -v runpodctl &> /dev/null; then
    pip install runpod
fi

# Deploy serverless endpoint (using Python SDK)
python3 << 'PYEOF'
import os
import runpod

runpod.api_key = os.getenv('RUNPOD_API_KEY')

# Create endpoint
endpoint = runpod.create_endpoint(
    name="openchat-fast-bridge",
    template_id="vllm-serverless",  # Pre-built template
    gpu_type="NVIDIA RTX 4090",
    workers_min=0,
    workers_max=3,
    env={
        "MODEL_NAME": "openchat/openchat-3.6-8b",
        "MAX_MODEL_LEN": "8192",
        "GPU_MEMORY_UTILIZATION": "0.95"
    }
)

print(f"✅ Endpoint Created: {endpoint['id']}")
print(f"📝 Add this to your .env:")
print(f"RUNPOD_ENDPOINT_ID={endpoint['id']}")
PYEOF
