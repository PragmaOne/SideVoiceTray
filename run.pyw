from datetime import datetime
from pathlib import Path
import sys
import traceback

from side_voice_tray.app import main


def _configure_hidden_launch_logging() -> None:
    log_path = Path(__file__).resolve().with_name("source-launch.log")
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file
    print()
    print(f"=== SideVoiceTray hidden start {datetime.now().isoformat(timespec='seconds')} ===")


if __name__ == "__main__":
    _configure_hidden_launch_logging()
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise
