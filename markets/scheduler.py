"""launchd / cron scheduler helpers — daily 9am queue + 9pm retro.

On macOS (this repo's primary target) we generate a launchd plist file
under `~/Library/LaunchAgents/com.orallexa.markets.{queue|retro}.plist`
and `launchctl load` it. On Linux we print a crontab snippet for the user
to paste themselves (no auto-install — modifying crontab automatically
across distros is fragile).

Times default to:
  9am local time → queue (Polymarket queue for the day)
  9pm local time → retro

The scheduler does NOT trade. It calls `python -m markets queue` and
`python -m markets retro` — both write to disk and exit.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PLIST_DIR = Path.home() / "Library" / "LaunchAgents"

QUEUE_LABEL = "com.orallexa.markets.queue"
RETRO_LABEL = "com.orallexa.markets.retro"


@dataclass
class SchedulerConfig:
    queue_hour: int = 9
    queue_minute: int = 0
    retro_hour: int = 21
    retro_minute: int = 0
    platform: str = "polymarket"   # which venue the queue runs against
    bankroll: float = 300.0
    queue_limit: int = 5
    python_path: str = sys.executable
    repo_path: str = ""             # set at install time
    log_dir: Path = Path.home() / ".orallexa" / "markets" / "logs"


def _plist_xml(
    label: str,
    hour: int,
    minute: int,
    python_path: str,
    repo_path: str,
    cli_args: list[str],
    log_dir: Path,
) -> str:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = log_dir / f"{label}.out.log"
    stderr = log_dir / f"{label}.err.log"
    args_xml = "\n      ".join(
        f"<string>{a}</string>" for a in [python_path, "-m", "markets", *cli_args]
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
      {args_xml}
    </array>
    <key>WorkingDirectory</key>
    <string>{repo_path}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{stdout}</string>
    <key>StandardErrorPath</key>
    <string>{stderr}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
"""


def _crontab_snippet(config: SchedulerConfig) -> str:
    repo = config.repo_path
    py = config.python_path
    logs = config.log_dir
    return f"""# orallexa-markets daily HITL queue + retro
# Append to your crontab via `crontab -e`. WorkingDirectory must be the repo root.
{config.queue_minute} {config.queue_hour} * * *  cd {repo} && {py} -m markets queue --platform {config.platform} --limit {config.queue_limit} --bankroll {config.bankroll}  >> {logs}/queue.out.log  2>> {logs}/queue.err.log
{config.retro_minute} {config.retro_hour} * * *  cd {repo} && {py} -m markets retro --bankroll {config.bankroll}  >> {logs}/retro.out.log  2>> {logs}/retro.err.log
"""


def install_launchd(config: SchedulerConfig) -> tuple[Path, Path]:
    """Write + load both plists. Returns (queue_plist_path, retro_plist_path)."""
    if not config.repo_path:
        config.repo_path = str(Path.cwd())

    PLIST_DIR.mkdir(parents=True, exist_ok=True)

    queue_plist = PLIST_DIR / f"{QUEUE_LABEL}.plist"
    retro_plist = PLIST_DIR / f"{RETRO_LABEL}.plist"

    queue_plist.write_text(_plist_xml(
        label=QUEUE_LABEL,
        hour=config.queue_hour, minute=config.queue_minute,
        python_path=config.python_path,
        repo_path=config.repo_path,
        cli_args=[
            "queue",
            "--platform", config.platform,
            "--limit", str(config.queue_limit),
            "--bankroll", str(config.bankroll),
        ],
        log_dir=config.log_dir,
    ))
    retro_plist.write_text(_plist_xml(
        label=RETRO_LABEL,
        hour=config.retro_hour, minute=config.retro_minute,
        python_path=config.python_path,
        repo_path=config.repo_path,
        cli_args=["retro", "--bankroll", str(config.bankroll)],
        log_dir=config.log_dir,
    ))

    # Reload (unload first; ignore errors when not yet loaded)
    if shutil.which("launchctl"):
        for plist in (queue_plist, retro_plist):
            subprocess.run(
                ["launchctl", "unload", str(plist)],
                capture_output=True, check=False,
            )
            subprocess.run(
                ["launchctl", "load", str(plist)],
                capture_output=True, check=False,
            )

    return queue_plist, retro_plist


def uninstall_launchd() -> None:
    for label in (QUEUE_LABEL, RETRO_LABEL):
        plist = PLIST_DIR / f"{label}.plist"
        if shutil.which("launchctl") and plist.exists():
            subprocess.run(
                ["launchctl", "unload", str(plist)],
                capture_output=True, check=False,
            )
        if plist.exists():
            plist.unlink()


def install(config: Optional[SchedulerConfig] = None) -> str:
    """Cross-platform install entry point. Returns a status string."""
    config = config or SchedulerConfig()
    if not config.repo_path:
        config.repo_path = str(Path.cwd())

    system = platform.system()
    if system == "Darwin":
        q, r = install_launchd(config)
        return (
            f"Installed launchd plists:\n"
            f"  {q}\n  {r}\n"
            f"Logs → {config.log_dir}/\n"
            f"Run `launchctl list | grep orallexa` to confirm."
        )
    # Linux / other: print snippet, don't auto-install
    return (
        f"Detected {system}; auto-install only supported on macOS. "
        f"Append the following to your crontab (`crontab -e`):\n\n"
        f"{_crontab_snippet(config)}"
    )
