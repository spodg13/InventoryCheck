#!/bin/zsh
# Start the PriceWatch page in the background at http://pricewatch.localhost:8503.
# It keeps running after you close the terminal, switch VS Code projects or
# close the browser tab, until you stop it (or the Mac restarts).
# Scheduled price checks run separately and don't need the page to be running.
#
#   prices           start it, or open it if it's already running
#   prices restart   stop any running copy and start fresh (after code changes)
#   prices stop      stop it
#   prices log       show its recent output (errors appear here)
set -e
cd "$(dirname "$0")"

APP="PriceWatch/web.py"
HOST="pricewatch.localhost"
NAME="PriceWatch page"
LOG="$HOME/Library/Logs/pricewatch-web.log"

# ".nosync" keeps iCloud Drive from syncing the Python environment; .venv is a
# symlink to it so editors and old commands still find it.
VENV=".venv.nosync"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Setting up the Python environment for the first time. This takes a minute..."
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -r requirements.txt
  "$VENV/bin/python" -m playwright install chromium
fi
if [[ -d .venv && ! -L .venv ]]; then
  echo "Replacing the iCloud-synced .venv folder with a link to $VENV..."
  rm -rf .venv
fi
[[ -L .venv ]] || ln -s "$VENV" .venv

running_pids() { pgrep -f "python.* $APP" || true; }

running_port() {
  local pid
  for pid in $(running_pids); do
    lsof -nP -a -p $pid -iTCP -sTCP:LISTEN 2>/dev/null \
      | awk 'NR==2{n=split($9,a,":"); print a[n]; exit}'
  done | head -1
}

stop_app() {
  local pids=($(running_pids))
  if (( ${#pids} )); then
    echo "Stopping the $NAME..."
    kill $pids
    for i in {1..10}; do
      [[ -z "$(running_pids)" ]] && break
      sleep 0.5
    done
  else
    echo "The $NAME wasn't running."
  fi
}

case "$1" in
  "") ;;
  restart) stop_app ;;
  stop) stop_app; exit 0 ;;
  log) tail -n 40 "$LOG" 2>/dev/null || echo "No log yet."; exit 0 ;;
  *) echo "Unknown option '$1'. Use: prices, prices restart, prices stop or prices log."; exit 1 ;;
esac

# Already running? Just open it instead of starting a second copy.
RUNNING_PORT=$(running_port)
if [[ -n "$RUNNING_PORT" ]]; then
  echo "$NAME is already running at http://$HOST:$RUNNING_PORT"
  open "http://$HOST:$RUNNING_PORT"
  exit 0
fi

# Use PORT (default 8503); if another program already has it, move up in steps of 10.
PORT=${PORT:-8503}
while lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; do
  echo "Port $PORT is already used by another program ($(lsof -nP -iTCP:$PORT -sTCP:LISTEN | awk 'NR==2{print $1}')); trying $((PORT+10))."
  PORT=$((PORT+10))
done

# nohup + &! detach it from this terminal. Output goes to the log.
mkdir -p "$(dirname "$LOG")"
PORT=$PORT nohup "$VENV/bin/python" "$APP" >"$LOG" 2>&1 &!

# Wait (up to 15 seconds) until it answers, then open it
for i in {1..30}; do
  curl -s -o /dev/null "http://localhost:$PORT/api/items" && break
  sleep 0.5
done
if curl -s -o /dev/null "http://localhost:$PORT/api/items"; then
  echo "$NAME running in the background at http://$HOST:$PORT"
  echo "Stop it with: prices stop   (log: prices log)"
  open "http://$HOST:$PORT"
else
  echo "The $NAME didn't start. Recent output:"
  tail -n 20 "$LOG"
  exit 1
fi
