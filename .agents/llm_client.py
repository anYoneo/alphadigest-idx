import os
import sys
import ssl
import time
import json
import socket
import urllib.request
import urllib.error
import threading

# Set global socket timeout to prevent indefinite hanging on remote tunnels
socket.setdefaulttimeout(60.0)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    import env_loader
except Exception:
    pass

_lock = threading.Lock()
_active_endpoint = None
_blacklisted_endpoints = set()   # endpoints that returned 401/403 (auth failure — skip permanently)
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

def get_candidate_endpoints():
    endpoints = []
    primary = os.environ.get("CUSTOM_LLM_URL", "").strip()
    fallback = os.environ.get("CUSTOM_LLM_FALLBACK_URL", "").strip()
    
    for u in [primary, fallback]:
        if u:
            if not u.endswith("/chat/completions"):
                u = u.rstrip("/") + "/chat/completions"
            if u not in endpoints:
                endpoints.append(u)
    return endpoints

def check_endpoint_health(url: str, timeout: float = 1.5) -> bool:
    key = os.environ.get("CUSTOM_LLM_KEY", "").strip()
    model = os.environ.get("CUSTOM_LLM_MODEL", "rasp").strip()
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "User-Agent": "LLMClient/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def get_best_endpoint() -> str:
    global _active_endpoint
    with _lock:
        if _active_endpoint:
            return _active_endpoint
        
        candidates = get_candidate_endpoints()
        if not candidates:
            return None
        
        # Prefer LOCAL/intranet endpoints first (tunnel may reject key with 401)
        preferred = [ep for ep in candidates if any(p in ep for p in ["10.", "192.168.", "127.0.0.1", "localhost"])]
        ordered = preferred + [ep for ep in candidates if ep not in preferred]
        
        for ep in ordered:
            if check_endpoint_health(ep):
                _active_endpoint = ep
                print(f"[LLM Client] Selected healthy endpoint: {_active_endpoint}")
                return _active_endpoint
        
        # Fallback: use first candidate even if health check failed
        _active_endpoint = candidates[0]
        print(f"[LLM Client] Warning: No healthy endpoint found. Falling back to: {_active_endpoint}")
        return _active_endpoint

def mark_endpoint_failed(url: str):
    global _active_endpoint
    with _lock:
        candidates = get_candidate_endpoints()
        alternates = [ep for ep in candidates if ep != url]
        if alternates:
            _active_endpoint = alternates[0]
            print(f"[LLM Client] Switched active endpoint from {url} to {_active_endpoint}")
        else:
            _active_endpoint = None

def call_llm(messages: list, temperature: float = 0.1, timeout: int = 10, max_retries: int = 1, context_name: str = "", max_tokens: int = 8000) -> str:
    global _active_endpoint, _blacklisted_endpoints
    key = os.environ.get("CUSTOM_LLM_KEY", "").strip()
    model = os.environ.get("CUSTOM_LLM_MODEL", "rasp").strip()
    
    candidates = get_candidate_endpoints()
    if not candidates or not key:
        return None
    
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode("utf-8")
    
    current_ep = get_best_endpoint()
    ordered_eps = [current_ep] + [ep for ep in candidates if ep != current_ep]
    
    for ep in ordered_eps:
        # Skip endpoints that have permanently failed auth (401/403)
        if ep in _blacklisted_endpoints:
            if context_name:
                print(f"      [!] Skipping blacklisted endpoint (auth failed): {ep}")
            continue

        for attempt in range(max_retries + 1):
            try:
                req = urllib.request.Request(
                    ep,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {key}",
                        "User-Agent": "Mozilla/5.0"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, context=_ssl_ctx, timeout=timeout) as resp:
                    res_text = resp.read().decode("utf-8")
                    clean_json_str = res_text.split("data:")[0].strip()
                    data = json.loads(clean_json_str)
                    choices = data.get("choices", [])
                    if choices:
                        content_str = choices[0]["message"].get("content", "")
                        if content_str:
                            with _lock:
                                _active_endpoint = ep
                            return content_str.strip()
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    # Auth failure — this endpoint will never work with current key, skip permanently
                    _blacklisted_endpoints.add(ep)
                    mark_endpoint_failed(ep)
                    print(f"      [!] HTTP {e.code} Unauthorized on {ep} — blacklisted (wrong key). Will not retry.")
                    break  # Skip remaining attempts for this endpoint
                else:
                    # Other HTTP errors (500, 429, etc.) — treat as transient
                    if attempt < max_retries:
                        time.sleep(1)
                        continue
                    else:
                        mark_endpoint_failed(ep)
                        if context_name:
                            print(f"      [!] HTTP {e.code} error on {ep} ({context_name}): {e}")
                        break
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                else:
                    mark_endpoint_failed(ep)
                    if context_name:
                        print(f"      [!] Endpoint {ep} failed ({context_name}): {e}")
                    break
                    
    return None


def parse_json_from_llm(content_str: str) -> dict:
    if not content_str:
        return None
    try:
        clean_str = content_str
        if "```json" in clean_str:
            clean_str = clean_str.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_str:
            clean_str = clean_str.split("```")[1].split("```")[0].strip()
        fb = clean_str.find("{")
        lb = clean_str.rfind("}")
        if fb != -1 and lb > fb:
            clean_str = clean_str[fb:lb+1]
        parsed = json.loads(clean_str)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return None
