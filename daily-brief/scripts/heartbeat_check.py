"""heartbeat_check.py — alert if daily-brief cron hasn't completed in 25h.

Read by hand: `python3 ~/.orallexa/daily-brief/scripts/heartbeat_check.py`
Or wire into a launchd watchdog if you want push notification.

Exit code 0 = healthy (last run < 25h ago)
Exit code 1 = stale (last run > 25h ago, or never)
Exit code 2 = missing (file doesn't exist — cron never succeeded)
"""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HEARTBEAT = Path.home() / ".orallexa" / "daily-brief" / ".last_success"
STALE_AFTER = timedelta(hours=25)


def main() -> int:
    if not HEARTBEAT.exists():
        print(f"❌ MISSING: {HEARTBEAT} not found. Daily-brief cron has never completed a full run.")
        return 2
    try:
        last_iso = HEARTBEAT.read_text().strip()
        last = datetime.fromisoformat(last_iso)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except Exception as exc:
        print(f"❌ CORRUPT: {HEARTBEAT} unreadable ({exc})")
        return 2

    now = datetime.now(timezone.utc)
    age = now - last
    if age > STALE_AFTER:
        h = int(age.total_seconds() // 3600)
        print(f"⚠️  STALE: last run was {h}h ago ({last_iso}). Cron may have stopped.")
        print(f"   Diagnose: tail -30 ~/.orallexa/daily-brief/logs/com.orallexa.daily-brief.err.log")
        print(f"   Retry:    launchctl start com.orallexa.daily-brief")
        return 1

    h = int(age.total_seconds() // 3600)
    m = int((age.total_seconds() % 3600) // 60)
    print(f"✅ HEALTHY: last successful run {h}h{m}m ago ({last_iso})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
