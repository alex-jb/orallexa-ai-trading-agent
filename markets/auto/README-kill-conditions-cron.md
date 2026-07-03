# Kill-conditions nightly cron — install guide

Ships 2026-07-02 (Tier-1 #10 wire-up follow-up).

## What this is

A nightly `launchd` job that runs `check_kill_conditions()` from
`engine/kill_conditions.py` against the current portfolio state
built from disk (paper P&L history + polymarket brier history +
decision log), then persists the decision to
`~/.orallexa/markets/kill_state.json`.

## Why

Without this cron, `check_kill_conditions()` only fires when a
caller happens to invoke it. If the caller forgets, dangerous
market conditions can pile up unnoticed. The nightly cron
guarantees at least one fresh check per day + writes the decision
where every other caller can find it. Any morning path that reads
a stale kill state (>30h old) should treat it as WAIT to fail
conservatively.

## Install steps

Files live outside the repo (in `~/Library/LaunchAgents/` and
`~/.orallexa/orallexa-nightly-cron/`) so they persist across repo
clones and can't accidentally be checked in.

### 1. Verify the Python cron works

```bash
cd ~/Desktop/orallexa-ai-trading-agent
python3 markets/auto/kill_conditions_cron.py
cat ~/.orallexa/markets/kill_state.json
```

Expected: exit 0, `state: "OK"` in the JSON.

### 2. Create the bash wrapper (TCC-sidestep)

Path: `~/.orallexa/orallexa-nightly-cron/run-kill-conditions.sh`

```bash
mkdir -p ~/.orallexa/orallexa-nightly-cron
cat > ~/.orallexa/orallexa-nightly-cron/run-kill-conditions.sh <<'EOF'
#!/bin/bash
set -euo pipefail
REPO="/Users/alexji/Desktop/orallexa-ai-trading-agent"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export ORALLEXA_REAL_MONEY="${ORALLEXA_REAL_MONEY:-0}"
echo "[kill-conditions-nightly] wrapper start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
cd "$REPO"
/usr/bin/python3 markets/auto/kill_conditions_cron.py
EXIT=$?
echo "[kill-conditions-nightly] wrapper exit code $EXIT $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit $EXIT
EOF
chmod +x ~/.orallexa/orallexa-nightly-cron/run-kill-conditions.sh
```

Reason for the wrapper: bare `/usr/bin/python3` under launchd hits
macOS TCC "Operation not permitted" on Desktop reads. `/bin/bash`
outer wrapper gets FDA permission and passes syscalls through.
Same pattern as `morning-deep-dive.sh` + `kelly-audit`.

### 3. Install the launchd plist

Path: `~/Library/LaunchAgents/com.alexji.orallexa.kill-conditions-nightly.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.alexji.orallexa.kill-conditions-nightly</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/alexji/.orallexa/orallexa-nightly-cron/run-kill-conditions.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>21</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/tmp/orallexa-kill-conditions.out</string>
  <key>StandardErrorPath</key>
  <string>/tmp/orallexa-kill-conditions.err</string>
  <key>KeepAlive</key>
  <false/>
</dict>
</plist>
```

### 4. Load into launchd

```bash
launchctl unload ~/Library/LaunchAgents/com.alexji.orallexa.kill-conditions-nightly.plist 2>/dev/null || true
launchctl load   ~/Library/LaunchAgents/com.alexji.orallexa.kill-conditions-nightly.plist
launchctl list | grep orallexa.kill
```

Expected: shows `-\t0\tcom.alexji.orallexa.kill-conditions-nightly`.
(`0` = not fired yet since load; `-` = not currently running.)

## Firing

Fires nightly at 21:00 NY local (macOS handles DST). Verify next
morning:

```bash
tail -20 /tmp/orallexa-kill-conditions.out
cat ~/.orallexa/markets/kill_state.json
```

Manual fire for testing:

```bash
launchctl start com.alexji.orallexa.kill-conditions-nightly
```

## Exit codes

- **0** = check ran, `can_trade: true` written (paper mode healthy)
- **2** = check ran, `can_trade: false` written (a kill gate fired — this
  is NORMAL if the state actually looks bad; the morning path should
  read the JSON and honor it)
- **1** = check itself crashed — no reliable state written; the morning
  pipeline should treat "kill state stale > 30h" as WAIT

## Real-money mode

Default is paper. To flip to real money, set env var in the plist
by adding:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>ORALLEXA_REAL_MONEY</key>
  <string>1</string>
</dict>
```

**Do NOT flip this without a manual review that all four gates have
been clear for the paper-days threshold** (default 30). The
`is_ready_for_real_money(state)` helper in `engine/kill_conditions.py`
enforces the stricter transition check.
