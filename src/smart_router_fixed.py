#!/usr/bin/env python3
"""
Smart Router - DEBUGGED VERSION v1.1
Cross-referenced with:
- ai-system/src/api_client.py (error handling)
- freedom-ai/samantha/core/system_check.py (health checks)
- freedom-ai/install.sh (logging, systemd patterns)
"""

import os
import re
import json
import time
import threading
import requests
import yaml
from typing import Dict, Optional, Literal
from datetime import datetime
from dataclasses import dataclass, field
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Thread-safe locks
_health_lock = threading.Lock()
_cost_lock = threading.Lock()

@dataclass
class Endpoint:
    name: str
    url: str
    api_key: Optional[str]
    model: str
    is_local: bool
    supports_uncensored: bool
    timeout: int = 30
    is_available: bool = False  # Start as False until proven
    last_check: float = 0
    consecutive_failures: int = 0

class SmartRouter:
    # BUG FIX: More comprehensive keyword detection
    NSFW_KEYWORDS = [
        'nsfw', 'uncensored', 'unfiltered', 'jailbreak', 
        'samantha', 'dolphin', 'adult', 'xxx', 'lewd', 'nude',
        'porn', 'explicit', 'gore', 'violence', 'kill', 'death'
    ]
    
    def __init__(self, config_path: str = "/workspace/ai-system-gpu/configs/router.yaml"):
        self.config = self._load_config(config_path)
        self.endpoints = self._initialize_endpoints()
        self.history = []
        self.session = self._create_session()
        self._total_cost = 0.0
        self._forced_preference = None  # BUG FIX: Store preference persistently
        self._startup_health_check()
        
    def _create_session(self):
        """Create requests session with robust retry logic."""
        session = requests.Session()
        # BUG FIX: More aggressive retries for RunPod cold starts
        retries = Retry(
            total=5,  # Increased from 3
            backoff_factor=2,  # Exponential: 2, 4, 8, 16, 32 seconds
            status_forcelist=[502, 503, 504, 429],  # Added 429 (rate limit)
            allowed_methods=["POST", "GET", "HEAD"]
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session
    
    def _load_config(self, path: str) -> Dict:
        """Load router configuration from YAML."""
        default_config = {
            'endpoints': {
                'local': {
                    # BUG FIX: No trailing slash [^68^][^69^]
                    'url': 'http://localhost:11434/api/chat',  # /api/chat not /api/generate
                    'model': 'samantha',  # Model name as pulled
                    'is_local': True,
                    'supports_uncensored': True,
                    'timeout': 120  # Increased for large models
                },
                'cloud': {
                    'url': 'https://api.runpod.ai/v2/{endpoint_id}/openai/v1/chat/completions',
                    'model': 'openchat/openchat-3.6-8b',
                    'api_key': os.getenv('RUNPOD_API_KEY'),
                    'endpoint_id': os.getenv('RUNPOD_ENDPOINT_ID'),
                    'is_local': False,
                    'supports_uncensored': False,
                    'timeout': 60  # Increased for cold starts
                }
            },
            'routing': {
                'default': 'cloud',
                'nsfw_fallback': 'local',
                'offline_mode': False,
                'cost_tracking': True,
                'max_retries': 3
            }
        }
        
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    loaded = yaml.safe_load(f)
                    if loaded:
                        default_config.update(loaded)
            except Exception as e:
                print(f"⚠️ Config load failed: {e}, using defaults")
        else:
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            with open(path, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False)
            print(f"✅ Created default config at {path}")
                
        return default_config
    
    def _initialize_endpoints(self) -> Dict[str, Endpoint]:
        """Initialize endpoint objects from config."""
        eps = {}
        for name, cfg in self.config['endpoints'].items():
            url = cfg['url']
            # BUG FIX: Handle endpoint ID substitution properly
            if '{endpoint_id}' in url:
                ep_id = cfg.get('endpoint_id') or os.getenv('RUNPOD_ENDPOINT_ID')
                if not ep_id or ep_id == 'xxx':
                    print(f"⚠️ Warning: RUNPOD_ENDPOINT_ID not set for {name}")
                    url = url.format(endpoint_id='PLACEHOLDER')
                else:
                    url = url.format(endpoint_id=ep_id)
            
            # BUG FIX: Strip trailing slashes [^68^][^69^]
            url = url.rstrip('/')
            
            eps[name] = Endpoint(
                name=name,
                url=url,
                api_key=cfg.get('api_key') or os.getenv(f'{name.upper()}_API_KEY'),
                model=cfg['model'],
                is_local=cfg.get('is_local', False),
                supports_uncensored=cfg.get('supports_uncensored', False),
                timeout=cfg.get('timeout', 30)
            )
        return eps
    
    def _startup_health_check(self):
        """Initial health check on startup."""
        print("🔍 Checking endpoint health...")
        for name, ep in self.endpoints.items():
            healthy = self._check_health(ep)
            status = "✅" if healthy else "❌"
            print(f"  {status} {name}: {ep.model}")
    
    def _detect_sensitivity(self, prompt: str) -> Literal['general', 'nsfw']:
        """Detect if prompt needs uncensored model."""
        prompt_lower = prompt.lower()
        
        # Check keywords
        if any(kw in prompt_lower for kw in self.NSFW_KEYWORDS):
            return 'nsfw'
        
        # Check for creative writing patterns that trigger censorship
        patterns = [
            r'\b(write|create|generate|story|roleplay|scene|describe).*\b(mature|explicit|dark|adult|sensual)',
            r'\b(ignore|disregard).*\b(previous|instructions|rules)',
            r'\b(dan|jailbreak|dude|developer mode)\b'
        ]
        
        for pattern in patterns:
            if re.search(pattern, prompt_lower):
                return 'nsfw'
                
        return 'general'
    
    def _check_health(self, endpoint: Endpoint) -> bool:
        """Thread-safe health check with debouncing."""
        # Debounce: only check every 30 seconds (increased from 10)
        if time.time() - endpoint.last_check < 30:
            return endpoint.is_available
        
        try:
            if endpoint.is_local:
                # BUG FIX: Check Ollama properly
                resp = self.session.get(
                    'http://localhost:11434/api/tags',  # Known working endpoint
                    timeout=5
                )
                healthy = resp.status_code == 200
                
                # Also check if specific model exists
                if healthy:
                    try:
                        models = resp.json().get('models', [])
                        model_names = [m.get('name') for m in models]
                        if endpoint.model not in model_names:
                            print(f"⚠️ Model '{endpoint.model}' not found in Ollama. Run: ollama pull {endpoint.model}")
                            healthy = False
                    except:
                        pass
            else:
                # RunPod health check
                headers = {}
                if endpoint.api_key:
                    headers['Authorization'] = f'Bearer {endpoint.api_key}'
                
                # Try health endpoint first
                health_url = endpoint.url.replace('/openai/v1/chat/completions', '/health')
                resp = self.session.get(health_url, headers=headers, timeout=10)
                healthy = resp.status_code in [200, 404]  # 404 means up but no health endpoint
                
                # If 404 on health, try a lightweight model list or assume up
                if resp.status_code == 404:
                    healthy = True  # Endpoint exists, might be cold
            
            # Thread-safe update
            with _health_lock:
                endpoint.is_available = healthy
                endpoint.last_check = time.time()
                if healthy:
                    endpoint.consecutive_failures = 0
                else:
                    endpoint.consecutive_failures += 1
            
            return healthy
            
        except Exception as e:
            with _health_lock:
                endpoint.is_available = False
                endpoint.last_check = time.time()
                endpoint.consecutive_failures += 1
            return False
    
    def _route_to_endpoint(self, prompt: str, preference: Optional[str] = None) -> Endpoint:
        """Determine best endpoint for prompt."""
        # BUG FIX: Use stored preference if set
        if self._forced_preference:
            preference = self._forced_preference
            self._forced_preference = None  # Clear after use
        
        sensitivity = self._detect_sensitivity(prompt)
        
        # Update health status (throttled internally)
        for ep in self.endpoints.values():
            self._check_health(ep)
        
        # Manual override
        if preference and preference in self.endpoints:
            chosen = self.endpoints[preference]
            if chosen.is_available:
                return chosen
            print(f"⚠️ Preferred endpoint '{preference}' unavailable, auto-routing...")
        
        # NSFW content -> Local (Freedom-AI/uncensored)
        if sensitivity == 'nsfw':
            local_ep = self.endpoints.get('local')
            if local_ep and local_ep.is_available and local_ep.supports_uncensored:
                print(f"🔓 ROUTING TO LOCAL (UNCENSORED): {local_ep.model}")
                return local_ep
            else:
                print("⚠️  Local uncensored unavailable, using cloud (WILL BE CENSORED)")
                print("   Tip: Run 'ollama pull samantha' to enable uncensored mode")
                return self.endpoints.get('cloud')
        
        # General content -> Cloud (RunPod) for speed/cost
        cloud_ep = self.endpoints.get('cloud')
        if cloud_ep and cloud_ep.is_available and not self.config['routing'].get('offline_mode'):
            print(f"☁️  ROUTING TO CLOUD (FAST): {cloud_ep.model}")
            return cloud_ep
        
        # Fallback chain
        local_ep = self.endpoints.get('local')
        if local_ep and local_ep.is_available:
            print("⚠️  Cloud unavailable, falling back to LOCAL")
            return local_ep
        
        raise ConnectionError("No endpoints available! Check Ollama and RunPod status.")
    
    def _call_ollama(self, endpoint: Endpoint, prompt: str, system: Optional[str] = None) -> str:
        """Call Freedom-AI via Ollama API - DEBUGGED."""
        # BUG FIX: Use modern /api/chat format with messages array
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": endpoint.model,
            "messages": messages,
            "stream": False,  # BUG FIX: Explicitly disable streaming [^70^]
            "options": {
                "temperature": 0.7,
                "num_ctx": 4096,
                "num_predict": 2048
            }
        }
        
        try:
            resp = self.session.post(endpoint.url, json=payload, timeout=endpoint.timeout)
            
            # BUG FIX: Better error handling for Ollama
            if resp.status_code == 404:
                error_data = resp.json() if resp.text else {}
                if "model" in str(error_data).lower():
                    raise RuntimeError(f"Model '{endpoint.model}' not found. Run: ollama pull {endpoint.model}")
                raise RuntimeError(f"Ollama endpoint not found. Is Ollama running?")
            
            resp.raise_for_status()
            data = resp.json()
            
            # Extract response from modern chat format
            if 'message' in data:
                return data['message'].get('content', '')
            elif 'response' in data:  # Legacy format fallback
                return data['response']
            else:
                raise ValueError(f"Unexpected response format: {data.keys()}")
                
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Ollama timeout after {endpoint.timeout}s (model loading?)")
        except requests.exceptions.ConnectionError:
            raise ConnectionError("Cannot connect to Ollama. Is 'ollama serve' running?")
    
    def _call_runpod(self, endpoint: Endpoint, prompt: str) -> str:
        """Call RunPod vLLM API - DEBUGGED."""
        headers = {
            'Authorization': f'Bearer {endpoint.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': endpoint.model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'max_tokens': 2000,
            'stream': False  # Ensure non-streaming
        }
        
        try:
            resp = self.session.post(endpoint.url, headers=headers, json=data, timeout=endpoint.timeout)
            
            # BUG FIX: Handle RunPod specific errors
            if resp.status_code == 502:
                raise RuntimeError("RunPod cold start (model loading). Wait 30s and retry.")
            elif resp.status_code == 401:
                raise RuntimeError("RunPod API key invalid. Check RUNPOD_API_KEY.")
            elif resp.status_code == 404:
                raise RuntimeError(f"RunPod endpoint not found. Check ENDPOINT_ID: {endpoint.url}")
            
            resp.raise_for_status()
            result = resp.json()
            
            # Validate response structure
            if 'choices' not in result or not result['choices']:
                if 'error' in result:
                    raise RuntimeError(f"RunPod error: {result['error']}")
                raise ValueError(f"No choices in response: {result.keys()}")
                
            return result['choices'][0]['message']['content']
            
        except requests.exceptions.Timeout:
            raise TimeoutError(f"RunPod timeout. Model may be cold-starting (up to 60s).")
    
    def generate(self, prompt: str, preference: Optional[str] = None, system: Optional[str] = None) -> Dict:
        """
        Main generation method with smart routing and fallbacks.
        CROSS-REFERENCE: Based on ai-system/src/api_client.py error handling
        """
        start_time = time.time()
        endpoint = self._route_to_endpoint(prompt, preference)
        self.current_endpoint = endpoint
        
        # Try primary endpoint with retry logic
        max_retries = self.config['routing'].get('max_retries', 3)
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if endpoint.is_local:
                    response = self._call_ollama(endpoint, prompt, system)
                else:
                    response = self._call_runpod(endpoint, prompt)
                break  # Success
                
            except (TimeoutError, RuntimeError) as e:
                last_error = e
                is_cold_start = "cold start" in str(e).lower() or "loading" in str(e).lower()
                
                if is_cold_start and attempt < max_retries - 1:
                    wait_time = min(30, (attempt + 1) * 10)  # Max 30s wait
                    print(f"⏳ Cold start detected, waiting {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                elif attempt < max_retries - 1:
                    print(f"🔄 Retry {attempt + 1}/{max_retries}...")
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    # All retries exhausted, try fallback
                    break
        
        else:  # All retries failed
            # Emergency fallback
            fallback_name = 'local' if not endpoint.is_local else 'cloud'
            print(f"🔄 Emergency fallback to {fallback_name}: {last_error}")
            
            try:
                fallback_ep = self.endpoints.get(fallback_name)
                if not fallback_ep:
                    raise RuntimeError("No fallback endpoint available")
                
                if fallback_ep.is_local:
                    response = self._call_ollama(fallback_ep, prompt, system)
                else:
                    response = self._call_runpod(fallback_ep, prompt)
                endpoint = fallback_ep
                
            except Exception as e2:
                raise RuntimeError(f"Both endpoints failed: {last_error}, then {e2}")
        
        latency = time.time() - start_time
        
        # Cost calculation (thread-safe)
        cost = 0.0
        if not endpoint.is_local:
            # BUG FIX: Better token estimation (rough but closer)
            # ~0.75 words per token average
            estimated_tokens = int((len(prompt) + len(response)) / 4)
            cost = (estimated_tokens / 1000) * 0.0002  # $0.0002 per 1K tokens
            with _cost_lock:
                self._total_cost += cost
        
        result = {
            'response': response,
            'endpoint_used': endpoint.name,
            'model': endpoint.model,
            'is_local': endpoint.is_local,
            'is_uncensored': endpoint.supports_uncensored,
            'latency_seconds': round(latency, 2),
            'timestamp': datetime.now().isoformat(),
            'prompt_length': len(prompt),
            'response_length': len(response),
            'estimated_cost_usd': cost,
            'retries': attempt if 'attempt' in locals() else 0
        }
        
        self.history.append(result)
        self._save_history()
        
        return result
    
    def _save_history(self):
        """Save conversation history (Android-safe path)."""
        try:
            log_dir = os.path.join(os.path.expanduser('~'), 'ai-system-gpu', 'logs')
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, 'router_history.json'), 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save history: {e}")
    
    def get_stats(self) -> Dict:
        """Get routing statistics."""
        if not self.history:
            return {
                'message': 'No requests yet',
                'endpoints': {name: {'available': ep.is_available, 'failures': ep.consecutive_failures} 
                             for name, ep in self.endpoints.items()}
            }
        
        total = len(self.history)
        local_count = sum(1 for r in self.history if r['is_local'])
        cloud_count = total - local_count
        avg_latency = sum(r['latency_seconds'] for r in self.history) / total
        
        return {
            'total_requests': total,
            'local_requests': local_count,
            'cloud_requests': cloud_count,
            'local_percentage': round(local_count/total*100, 1),
            'avg_latency': round(avg_latency, 2),
            'total_estimated_cost': round(self._total_cost, 4),
            'endpoints': {name: {'available': ep.is_available, 'failures': ep.consecutive_failures} 
                         for name, ep in self.endpoints.items()}
        }

    def chat_loop(self):
        """Interactive chat interface."""
        print("🚀 Smart Router Ready (DEBUGGED v1.1)")
        print("Commands: /local, /cloud, /stats, /health, /quit")
        print("-" * 50)
        
        while True:
            try:
                user_input = input("\nYou: ").strip()
                
                if not user_input:
                    continue
                if user_input == '/quit':
                    break
                if user_input == '/stats':
                    stats = self.get_stats()
                    print(json.dumps(stats, indent=2))
                    continue
                if user_input == '/health':
                    print("🔍 Checking health...")
                    for name, ep in self.endpoints.items():
                        healthy = self._check_health(ep)
                        print(f"  {'✅' if healthy else '❌'} {name}: {ep.model}")
                    continue
                if user_input == '/local':
                    self._forced_preference = 'local'  # BUG FIX: Persist preference
                    print("📍 Next request will use LOCAL")
                    continue
                if user_input == '/cloud':
                    self._forced_preference = 'cloud'  # BUG FIX: Persist preference
                    print("☁️ Next request will use CLOUD")
                    continue
                
                # Parse inline preference
                pref = None
                text = user_input
                if user_input.startswith('/local '):
                    pref, text = 'local', user_input[7:]
                elif user_input.startswith('/cloud '):
                    pref, text = 'cloud', user_input[7:]
                
                result = self.generate(text, preference=pref)
                
                print(f"\n🤖 ({result['endpoint_used']}, {result['latency_seconds']}s):")
                print(result['response'])
                
                if result['estimated_cost_usd'] > 0:
                    print(f"\n💰 Cost: ${result['estimated_cost_usd']:.6f}")
                
                if result.get('retries', 0) > 0:
                    print(f"🔄 Retries: {result['retries']}")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                print("Tip: Check /health or run 'ollama serve'")

if __name__ == "__main__":
    try:
        router = SmartRouter()
        router.chat_loop()
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
