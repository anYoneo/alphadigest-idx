import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

console = Console()

def get_project_root() -> Path:
    """Returns the Path to the project root (parent of src/)."""
    return Path(__file__).resolve().parent.parent

def load_config() -> Dict[str, Any]:
    """Load YAML config from config/settings.yaml relative to project root."""
    config_path = get_project_root() / "config" / "settings.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        console.print(f"[red]Error: Config file not found at {config_path}[/red]")
        return {}
    except yaml.YAMLError as e:
        console.print(f"[red]Error parsing YAML config: {e}[/red]")
        return {}

def load_env() -> None:
    """Load .env file using python-dotenv."""
    env_path = get_project_root() / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        console.print(f"[yellow]Warning: .env file not found at {env_path}[/yellow]")

def ensure_dirs(config: Dict[str, Any]) -> None:
    """Create all output directories defined in config['paths'] if they don't exist."""
    root_dir = get_project_root()
    paths = config.get("paths", {})
    for name, path_str in paths.items():
        if path_str:
            dir_path = root_dir / path_str
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                console.print(f"[red]Error creating directory {dir_path}: {e}[/red]")

def save_json(data: Union[Dict[str, Any], List[Any]], filepath: Union[str, Path]) -> None:
    """Save dict/list to JSON file with pretty printing and ensure parent dirs exist."""
    path = Path(filepath)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        console.print(f"[red]Error saving JSON to {path}: {e}[/red]")

def load_json(filepath: Union[str, Path]) -> Union[Dict[str, Any], List[Any]]:
    """Load JSON file, return dict/list."""
    path = Path(filepath)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Error: JSON file not found at {path}[/red]")
        return {}
    except json.JSONDecodeError as e:
        console.print(f"[red]Error parsing JSON at {path}: {e}[/red]")
        return {}

def get_today_str() -> str:
    """Return today's date as 'YYYY-MM-DD' string."""
    return datetime.now().strftime("%Y-%m-%d")

def setup_logging(level: Union[int, str] = logging.INFO) -> None:
    """Configure logging with rich handler."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)]
    )

if __name__ == "__main__":
    setup_logging()
    logging.info("Testing logging setup in utils.py")
    console.print("[green]Console output works![/green]")
