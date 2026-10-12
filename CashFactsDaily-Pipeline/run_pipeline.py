#!/usr/bin/env python3
"""
CashFactsDaily / FaktaCuan — Content Pipeline Orchestrator (Phase 1)

Usage:
    python run_pipeline.py scan          # Scan trending topics only
    python run_pipeline.py generate      # Generate scripts from today's topics
    python run_pipeline.py full          # Scan topics + generate scripts
    python run_pipeline.py status        # Show pending/approved/published counts

This is the master entry point for the automation pipeline.
Phase 1 covers: Topic Scanning + Script Generation.
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from utils import load_config, load_env, ensure_dirs, get_today_str, setup_logging, console
from topic_scanner import scan_topics
from script_generator import generate_all_scripts


def cmd_scan(args) -> None:
    """Run topic scanner only."""
    console.rule("[bold cyan]📡 Step 1: Scanning Trending Topics[/]")
    topics = scan_topics()

    if topics and topics.get("topics"):
        console.print(
            f"\n[green]✅ Found {topics['total_topics']} topics![/] "
            f"Saved to data/topics/topics_{get_today_str()}.json"
        )
    else:
        console.print("[yellow]⚠️ No topics found. Check your internet connection.[/]")


def cmd_generate(args) -> None:
    """Generate scripts from today's topics."""
    n = args.count if hasattr(args, "count") else 4
    console.rule("[bold cyan]📝 Step 2: Generating Scripts[/]")
    scripts = generate_all_scripts(n=n)

    if scripts:
        console.print(f"\n[green]✅ Generated {len(scripts)} scripts![/] Check scripts/pending/")
    else:
        console.print(
            "[yellow]⚠️ No scripts generated. "
            "Run 'python run_pipeline.py scan' first.[/]"
        )


def cmd_full(args) -> None:
    """Run full Phase 1 pipeline: scan + generate."""
    console.rule("[bold magenta]🚀 CashFactsDaily Pipeline — Phase 1[/]")
    console.print()

    # Step 1: Scan
    cmd_scan(args)
    console.print()

    # Step 2: Generate
    cmd_generate(args)

    console.print()
    console.rule("[bold magenta]Pipeline Complete[/]")
    console.print(
        "\n[bold]Next steps:[/]\n"
        "  1. Review scripts in [cyan]scripts/pending/[/]\n"
        "  2. Edit for humor, slang, and unique perspective\n"
        "  3. Move approved scripts to [cyan]scripts/approved/[/]\n"
    )


def cmd_status(args) -> None:
    """Show counts of pending/approved/published scripts."""
    config = load_config()
    root = Path(__file__).parent

    dirs = {
        "📋 Pending (need review)": root / config["paths"]["scripts_pending"],
        "✅ Approved (ready to produce)": root / config["paths"]["scripts_approved"],
        "📤 Published": root / config["paths"]["scripts_published"],
    }

    console.rule("[bold cyan]📊 Pipeline Status[/]")
    for label, path in dirs.items():
        if path.exists():
            md_files = list(path.glob("*.md"))
            count = len(md_files)
            # Count by language
            en_count = len([f for f in md_files if "_en_" in f.name])
            id_count = len([f for f in md_files if "_id_" in f.name])
            console.print(f"  {label}: [bold]{count}[/] (EN: {en_count}, ID: {id_count})")
        else:
            console.print(f"  {label}: [dim]0 (directory not created yet)[/]")

    # Show today's topics
    topics_dir = root / config["paths"]["data_topics"]
    today_file = topics_dir / f"topics_{get_today_str()}.json"
    if today_file.exists():
        import json

        data = json.loads(today_file.read_text(encoding="utf-8"))
        console.print(
            f"\n  📡 Today's topics: [bold]{data.get('total_topics', 0)}[/] "
            f"(scanned at {data.get('scan_timestamp', 'unknown')})"
        )
    else:
        console.print("\n  📡 Today's topics: [dim]Not scanned yet[/]")


def main():
    parser = argparse.ArgumentParser(
        description="CashFactsDaily / FaktaCuan — Content Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py scan          # Scan trending topics
  python run_pipeline.py generate      # Generate scripts from topics  
  python run_pipeline.py generate -n 6 # Generate 6 scripts (3 EN + 3 ID)
  python run_pipeline.py full          # Full pipeline (scan + generate)
  python run_pipeline.py status        # Check pipeline status
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Pipeline command")

    # Scan command
    subparsers.add_parser("scan", help="Scan trending topics from all sources")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate video scripts")
    gen_parser.add_argument(
        "-n", "--count", type=int, default=4,
        help="Number of scripts to generate (split between EN+ID, default: 4)"
    )

    # Full pipeline
    full_parser = subparsers.add_parser("full", help="Run full pipeline (scan + generate)")
    full_parser.add_argument(
        "-n", "--count", type=int, default=4,
        help="Number of scripts to generate (default: 4)"
    )

    # Status
    subparsers.add_parser("status", help="Show pipeline status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize
    load_env()
    setup_logging(load_config().get("pipeline", {}).get("log_level", "INFO"))
    ensure_dirs(load_config())

    # Route command
    commands = {
        "scan": cmd_scan,
        "generate": cmd_generate,
        "full": cmd_full,
        "status": cmd_status,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
