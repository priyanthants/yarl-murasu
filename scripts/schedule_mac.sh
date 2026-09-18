#!/bin/bash
# Turn automatic news updates on or off on this Mac (runs scripts/update.sh on a timer).
#
#   scripts/schedule_mac.sh on        # every 30 minutes (default)
#   scripts/schedule_mac.sh on 15     # every 15 minutes
#   scripts/schedule_mac.sh off
#   scripts/schedule_mac.sh status
set -eu
LABEL="lk.jaffna.news.update"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"

case "${1:-status}" in
  on)
    MINUTES="${2:-30}"
    mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT/logs"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$PROJECT/scripts/update.sh</string></array>
  <key>StartInterval</key><integer>$((MINUTES * 60))</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$PROJECT/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$PROJECT/logs/launchd.log</string>
</dict>
</plist>
EOF
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "Automatic updates ON: every $MINUTES minutes. Log: $PROJECT/logs/update.log"
    ;;
  off)
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Automatic updates OFF."
    ;;
  status)
    if launchctl list | grep -q "$LABEL"; then echo "Automatic updates are ON."; else echo "Automatic updates are OFF."; fi
    [ -f "$PROJECT/logs/update.log" ] && { echo "--- last log lines ---"; tail -n 12 "$PROJECT/logs/update.log"; }
    ;;
  *)
    echo "Usage: $0 on [minutes] | off | status"; exit 1 ;;
esac
