"""Maintenance mode CLI command."""

import sys
from pathlib import Path

from src.lib.constants import MAINTENANCE_FLAG_PATH, MAINTENANCE_MESSAGE


def maintenance(action: str) -> None:
    """Enable, disable, or check maintenance mode.

    Args:
        action: Action to perform ("on", "off", or "status")
    """
    flag_path = Path(MAINTENANCE_FLAG_PATH)

    if action == "on":
        # Create maintenance flag file
        try:
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            flag_path.touch()
            print("✅ Maintenance mode enabled")
            print(f"   Users will see: {MAINTENANCE_MESSAGE}")
            print(f"   Flag file created: {flag_path}")
        except Exception as e:
            print(f"❌ Failed to enable maintenance mode: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "off":
        # Remove maintenance flag file
        try:
            if flag_path.exists():
                flag_path.unlink()
                print("✅ Maintenance mode disabled")
                print(f"   Flag file removed: {flag_path}")
            else:
                print("⚠️  Maintenance mode was already disabled")
        except Exception as e:
            print(f"❌ Failed to disable maintenance mode: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "status":
        # Check current status
        if flag_path.exists():
            print("🔧 Maintenance mode is ENABLED")
            print(f"   Flag file: {flag_path}")
            print(f"   Users see: {MAINTENANCE_MESSAGE}")
        else:
            print("✅ Maintenance mode is DISABLED")
            print(f"   Flag file: {flag_path} (does not exist)")

    else:
        print(f"❌ Unknown action: {action}", file=sys.stderr)
        print("   Valid actions: on, off, status", file=sys.stderr)
        sys.exit(1)
