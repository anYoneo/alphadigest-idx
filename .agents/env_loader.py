import os

def load_env(base_dir=None):
    """Loads key-value pairs from .env into os.environ if not already set."""
    if not base_dir:
        current_file = os.path.abspath(__file__)
        agents_dir = os.path.dirname(current_file)
        model_dir = os.path.dirname(agents_dir)
        candidates = [
            os.path.join(model_dir, ".env"),
            os.path.join(agents_dir, ".env"),
            os.path.join(os.getcwd(), ".env")
        ]
    else:
        candidates = [
            os.path.join(base_dir, ".env"),
            os.path.join(base_dir, ".agents", ".env")
        ]

    for env_path in candidates:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

# Auto-execute on import
load_env()
