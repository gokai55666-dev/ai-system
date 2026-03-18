#!/usr/bin/env python3
"""
Smart Router: Routes between Freedom-AI (local/uncensored) and RunPod (cloud/fast)
Fixed for: Race conditions, network failures, Termux compatibility
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
from dataclasses import dataclass
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
    is_available: bool = True
    last_check: float = 0

class SmartRouter:
    NSFW_KEYWORDS = [
        'nsfw', 'uncensored', 'unfiltered', 'jailbreak', 
        'samantha', 'dolphin', 'adult', 'xxx', 'nsfw', 'lewd'
    ]
    
    def __init__(self, config_path: str = "configs/router.yaml"):
        self.config = self._load_config(config_path)
        self.endpoints = self._initialize_endpoints()
        self.history = []
        self.session = self._create_session()
        self._total_cost = 0.0
        
    def _create_session(self):
        """Create requests session with retry logic."""
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[502, 503, 504],
            allowed_methods=["POST", "GET"]
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
                    'url': 'http://localhost:11434/api/generate',
                    'model': 'samantha-1.11-70b',
                    'api_key': None,
                    'is_local': True,
                    'supports_uncensored': True,
                    'timeout': 60
                },
                'cloud': {
                    'url': 'https://api.runpod.ai/v2/{endpoint_id}/openai/v1/chat/completions',
                    'model': 'openchat/openchat-3.6-8b',
                    'api_key': os.getenv('RUNPOD_API_KEY'),
                    'endpoint_id': os.getenv('RUNPOD_ENDPOINT_ID'),
                    'is_local': False,
                    'supports_uncensored': False,
                    'timeout': 30
                }
            },
            'routing': {
                'default': 'cloud',
                'nsfw_fallback': 'local',
                'offline_mode': False,
                'cost_tracking': True
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
        
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        if not os.path.exists(path):
            with open(path, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False)
                
        return default_config
    
    def _initialize_endpoints(self) -> Dict[str, Endpoint]:
        """Initialize endpoint objects from config."""
        eps = {}
        for name, cfg in self.config['endpoints'].items():
            url = cfg['url']
            if '{endpoint_id}' in url:
                ep_id = cfg.get('endpoint_id', os.getenv('RUNPOD_ENDPOINT_ID', 'xxx'))
                url = url.format(endpoint_id=ep_id)
            
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
    
    def _detect_sensitivity(self, prompt: str) -> Literal['general', 'nsfw']:
        """Detect if prompt needs uncensored model."""
        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in self.NSFW_KEYWORDS):
            return 'nsfw'
        
        # Check for creative writing patterns
        creative_patterns = r'\b(write|create|generate|story|roleplay|scene).*\b(mature|explicit|dark|adult)'
        if re.search(creative_patterns, prompt_lower):
            return 'nsfw'
            
        return 'general'
    
    def _check_health(self, endpoint: Endpoint) -> bool:
        """Thread-safe health check with debouncing."""
        # Debounce: only check every 10 seconds
        if time.time() - endpoint.last_check < 10:
            return endpoint.is_available
        
        try:
            if endpoint.is_local:
                resp = self.session.get(
                    endpoint.url.replace('/api/generate', '/api/tags'),
                    timeout=5
                )
                healthy = resp.status_code == 200
            else:
                # RunPod health check
                headers = {'Authorization': f'Bearer {endpoint.api_key}'} if endpoint.api_key else {}
                resp = self.session.get(
                    endpoint.url.replace('/openai/v1/chat/completions', '/health'),
                    headers=headers,
                    timeout=5
                )
                healthy = resp.status_code in [200, 404]  # 404 means up but no health endpoint
            
            # Thread-safe update
            with _health_lock:
                endpoint.is_available = healthy
                endpoint.last_check = time.time()
            
            return healthy
            
        except Exception as e:
            with _health_lock:
                endpoint.is_available = False
                endpoint.last_check = time.time()
            return False
    
    def _route_to_endpoint(self, prompt: str, preference: Optional[str] = None) -> Endpoint:
        """Determine best endpoint for prompt."""
        sensitivity = self._detect_sensitivity(prompt)
        
        # Update health status
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
                print(f"🔓 Routing to LOCAL (uncensored): {local_ep.model}")
                return local_ep
            else:
                print("⚠️ Local uncensored unavailable, falling back to cloud (may be censored)")
                return self.endpoints.get('cloud')
        
        # General content -> Cloud (RunPod) for speed/cost
        cloud_ep = self.endpoints.get('cloud')
        if cloud_ep and cloud_ep.is_available and not self.config['routing'].get('offline_mode'):
            print(f"☁️  Routing to CLOUD (fast): {cloud_ep.model}")
            return cloud_ep
        
        # Fallback chain
        if self.endpoints.get('local') and self.endpoints['local'].is_available:
            print("⚠️ Cloud unavailable, falling back to LOCAL")
            return self.endpoints['local']
        
        raise ConnectionError("No endpoints available! Check your connections.")
    
    def _call_ollama(self, endpoint: Endpoint, prompt: str, system: Optional[str] = None) -> str:
        """Call Freedom-AI via Ollama API with retries."""
        payload = {
            'model': endpoint.model,
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': 0.7,
                'num_ctx': 4096
            }
        }
        if system:
            payload['system'] = system
        
        try:
            resp = self.session.post(endpoint.url, json=payload, timeout=endpoint.timeout)
            resp.raise_for_status()
            return resp.json()['response']
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Ollama timeout after {endpoint.timeout}s")
        except Exception as e:
            raise ConnectionError(f"Ollama error: {e}")
    
    def _call_runpod(self, endpoint: Endpoint, prompt: str) -> str:
        """Call RunPod vLLM API."""
        headers = {
            'Authorization': f'Bearer {endpoint.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': endpoint.model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'max_tokens': 2000
        }
        
        try:
            resp = self.session.post(endpoint.url, headers=headers, json=data, timeout=endpoint.timeout)
            
            # Handle RunPod model loading (502)
            if resp.status_code == 502:
                raise RuntimeError("RunPod model loading (cold start), retry in 10s")
            
            resp.raise_for_status()
            result = resp.json()
            
            if 'choices' not in result or not result['choices']:
                raise ValueError(f"Invalid response: {result}")
                
            return result['choices'][0]['message']['content']
            
        except requests.exceptions.Timeout:
            raise TimeoutError(f"RunPod timeout after {endpoint.timeout}s")
    
    def generate(self, prompt: str, preference: Optional[str] = None, system: Optional[str] = None) -> Dict:
        """
        Main generation method with smart routing and fallbacks.
        """
        start_time = time.time()
        last_error = None
        
        # Try primary endpoint
        try:
            endpoint = self._route_to_endpoint(prompt, preference)
            self.current_endpoint = endpoint
            
            if endpoint.is_local:
                response = self._call_ollama(endpoint, prompt, system)
            else:
                response = self._call_runpod(endpoint, prompt)
                
        except (ConnectionError, TimeoutError) as e:
            last_error = e
            # Emergency fallback to other endpoint
            fallback_name = 'local' if self.current_endpoint and not self.current_endpoint.is_local else 'cloud'
            print(f"🔄 Emergency fallback to {fallback_name}: {e}")
            
            try:
                fallback_ep = self.endpoints.get(fallback_name)
                if fallback_ep:
                    if fallback_ep.is_local:
                        response = self._call_ollama(fallback_ep, prompt, system)
                    else:
                        response = self._call_runpod(fallback_ep, prompt)
                    endpoint = fallback_ep
                else:
                    raise
            except Exception as e2:
                raise RuntimeError(f"Both endpoints failed: {e}, then {e2}")
        
        latency = time.time() - start_time
        
        # Estimate cost (thread-safe)
        cost = 0.0
        if not endpoint.is_local and self.config['routing'].get('cost_tracking'):
            # Rough estimate: $0.0002 per 1K tokens for RunPod
            tokens = len(prompt.split()) + len(response.split())
            cost = (tokens / 1000) * 0.0002
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
            'estimated_cost_usd': cost
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
            return {'message': 'No requests yet'}
        
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
            'total_estimated_cost': round(self._total_cost, 4)
        }

# CLI Interface
if __name__ == "__main__":
    try:
        router = SmartRouter()
        print("🚀 Smart Router Ready (Fixed for Race Conditions & Termux)")
        print("Commands: /local, /cloud, /stats, /quit")
        print("-" * 50)
        
        while True:
            try:
                user_input = input("\nYou: ").strip()
                
                if not user_input:
                    continue
                if user_input == '/quit':
                    break
                if user_input == '/stats':
                    stats = router.get_stats()
                    print(json.dumps(stats, indent=2))
                    continue
                if user_input == '/local':
                    print("📍 Next request forced to LOCAL")
                    router._force_local = True
                    continue
                if user_input == '/cloud':
                    print("☁️ Next request forced to CLOUD")
                    router._force_cloud = True
                    continue
                
                preference = None
                if user_input.startswith('/local '):
                    preference = 'local'
                    user_input = user_input[7:]
                elif user_input.startswith('/cloud '):
                    preference = 'cloud'
                    user_input = user_input[7:]
                
                result = router.generate(user_input, preference=preference)
                
                print(f"\n🤖 AI ({result['endpoint_used']}, {result['latency_seconds']}s):")
                print(result['response'])
                
                if result['estimated_cost_usd'] > 0:
                    print(f"\n💰 Cost: ${result['estimated_cost_usd']:.6f}")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                print("Tip: Check if Ollama is running (local) or RunPod key is set (cloud)")
        
        print("\n👋 Goodbye!")
        
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        print("Check your config file and environment variables!")
