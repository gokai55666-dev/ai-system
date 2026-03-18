#!/usr/bin/env python3
"""
Smart Router: Automatically routes between Freedom-AI (local/uncensored) 
and RunPod (cloud/fast) based on content sensitivity and availability.
"""

import os
import re
import json
import time
import requests
import yaml
from typing import Dict, Optional, Literal
from datetime import datetime
from dataclasses import dataclass, asdict

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

class SmartRouter:
    # Keywords that trigger uncensored routing
    NSFW_KEYWORDS = [
        'nsfw', 'uncensored', 'unfiltered', 'jailbreak', 
        'samantha', 'dolphin', 'uncensored', 'adult', 'xxx'
    ]
    
    def __init__(self, config_path: str = "configs/router.yaml"):
        self.config = self._load_config(config_path)
        self.endpoints = self._initialize_endpoints()
        self.history = []
        self.current_endpoint = None
        
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
            with open(path, 'r') as f:
                loaded = yaml.safe_load(f)
                default_config.update(loaded)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, 'w') as f:
                yaml.dump(default_config, f)
                
        return default_config
    
    def _initialize_endpoints(self) -> Dict[str, Endpoint]:
        """Initialize endpoint objects from config."""
        eps = {}
        for name, cfg in self.config['endpoints'].items():
            # Format URL for RunPod
            url = cfg['url']
            if '{endpoint_id}' in url:
                url = url.format(endpoint_id=cfg.get('endpoint_id', 'xxx'))
            
            eps[name] = Endpoint(
                name=name,
                url=url,
                api_key=cfg.get('api_key'),
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
        
        # Check for creative writing that might hit filters
        creative_patterns = r'\b(write|create|generate|story|roleplay|scene).*\b(sexual|violence|dark|mature)'
        if re.search(creative_patterns, prompt_lower):
            return 'nsfw'
            
        return 'general'
    
    def _check_health(self, endpoint: Endpoint) -> bool:
        """Check if endpoint is reachable."""
        try:
            if endpoint.is_local:
                # Ollama health check
                resp = requests.get(
                    endpoint.url.replace('/api/generate', '/api/tags'),
                    timeout=5
                )
                return resp.status_code == 200
            else:
                # RunPod health check (lightweight)
                resp = requests.get(
                    endpoint.url.replace('/openai/v1/chat/completions', '/health'),
                    headers={'Authorization': f'Bearer {endpoint.api_key}'},
                    timeout=5
                )
                return resp.status_code == 200
        except:
            return False
    
    def _route_to_endpoint(self, prompt: str, preference: Optional[str] = None) -> Endpoint:
        """Determine best endpoint for prompt."""
        sensitivity = self._detect_sensitivity(prompt)
        
        # Check endpoint health
        for ep in self.endpoints.values():
            ep.is_available = self._check_health(ep)
        
        # Routing logic
        if preference and preference in self.endpoints:
            chosen = self.endpoints[preference]
            if chosen.is_available:
                return chosen
        
        # NSFW content -> Local (Freedom-AI)
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
        if cloud_ep and cloud_ep.is_available:
            print(f"☁️  Routing to CLOUD (fast): {cloud_ep.model}")
            return cloud_ep
        
        # Fallback to local if cloud down
        print("⚠️ Cloud unavailable, falling back to LOCAL")
        return self.endpoints.get('local')
    
    def _call_ollama(self, endpoint: Endpoint, prompt: str, system: Optional[str] = None) -> str:
        """Call Freedom-AI via Ollama API."""
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
        
        resp = requests.post(endpoint.url, json=payload, timeout=endpoint.timeout)
        resp.raise_for_status()
        return resp.json()['response']
    
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
        
        resp = requests.post(endpoint.url, headers=headers, json=data, timeout=endpoint.timeout)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']
    
    def generate(self, prompt: str, preference: Optional[str] = None, system: Optional[str] = None) -> Dict:
        """
        Main generation method with smart routing.
        
        Args:
            prompt: User input
            preference: Force 'local' or 'cloud'
            system: System prompt (for Ollama)
        
        Returns:
            Dict with response, routing info, and metadata
        """
        start_time = time.time()
        endpoint = self._route_to_endpoint(prompt, preference)
        self.current_endpoint = endpoint
        
        try:
            if endpoint.is_local:
                response = self._call_ollama(endpoint, prompt, system)
            else:
                response = self._call_runpod(endpoint, prompt)
            
            latency = time.time() - start_time
            
            result = {
                'response': response,
                'endpoint_used': endpoint.name,
                'model': endpoint.model,
                'is_local': endpoint.is_local,
                'is_uncensored': endpoint.supports_uncensored,
                'latency_seconds': round(latency, 2),
                'timestamp': datetime.now().isoformat(),
                'prompt_length': len(prompt),
                'response_length': len(response)
            }
            
            self.history.append(result)
            self._save_history()
            
            # Cost tracking (approximate)
            if self.config['routing'].get('cost_tracking'):
                cost = self._estimate_cost(result)
                result['estimated_cost_usd'] = cost
                print(f"💰 Est. cost: ${cost:.6f}")
            
            return result
            
        except Exception as e:
            # Emergency fallback
            print(f"❌ Error with {endpoint.name}: {e}")
            if endpoint.name != 'local' and 'local' in self.endpoints:
                print("🔄 Emergency fallback to LOCAL...")
                return self.generate(prompt, preference='local', system=system)
            raise
    
    def _save_history(self):
        """Save conversation history."""
        os.makedirs('logs', exist_ok=True)
        with open('logs/router_history.json', 'w') as f:
            json.dump(self.history, f, indent=2)
    
    def _estimate_cost(self, result: Dict) -> float:
        """Estimate API cost."""
        if result['is_local']:
            # Local cost = electricity (~$0.0001 per request)
            return 0.0001
        
        # RunPod serverless: ~$0.00019/sec + compute
        # Rough estimate: $0.0002 per 1K tokens
        tokens = result['prompt_length'] + result['response_length']
        return (tokens / 1000) * 0.0002
    
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
            'total_estimated_cost': round(sum(r.get('estimated_cost_usd', 0) for r in self.history), 4)
        }

# CLI Interface
if __name__ == "__main__":
    router = SmartRouter()
    print("🚀 Smart Router Ready")
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
                print(json.dumps(router.get_stats(), indent=2))
                continue
            if user_input == '/local':
                print("📍 Next request forced to LOCAL")
                continue
            if user_input == '/cloud':
                print("☁️ Next request forced to CLOUD")
                continue
            
            preference = None
            if user_input.startswith('/local '):
                preference = 'local'
                user_input = user_input[7:]
            elif user_input.startswith('/cloud '):
                preference = 'cloud'
                user_input = user_input[7:]
            
            result = router.generate(user_input, preference=preference)
            print(f"\n🤖 AI ({result['endpoint_used']}): {result['response'][:500]}...")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n👋 Goodbye!")
