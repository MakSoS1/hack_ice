#!/usr/bin/env bash
# SSH tunnel + backend keepalive for macOS -> Windows PC
# Usage: bash scripts/start_backend_keepalive.sh

SSH_KEY=~/.ssh/id_ed25520
PC_USER=maksi
PC_HOST=10.78.211.199
PC_DIR='C:\Users\maksi\projects\vizard-arctic\backend'
PC_VENV='C:\Users\maksi\projects\vizard-arctic\.venv\Scripts\python.exe'

echo "Checking if backend is already running..."
HEALTH=$(curl -s --connect-timeout 3 --max-time 5 "http://${PC_HOST}:8000/health" 2>/dev/null)
if echo "$HEALTH" | grep -q '"status":"ok"'; then
  echo "Backend is already running!"
  exit 0
fi

echo "Starting backend on PC via SSH..."
ssh -i "$SSH_KEY" "${PC_USER}@${PC_HOST}" "cd ${PC_DIR}; ${PC_VENV} run.py" &

echo "Waiting for backend to start..."
for i in $(seq 1 20); do
  sleep 2
  HEALTH=$(curl -s --connect-timeout 2 --max-time 5 "http://${PC_HOST}:8000/health" 2>/dev/null)
  if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo "Backend started! (took ~$((i*2))s)"
    echo "IMPORTANT: Keep this terminal open while using the demo."
    echo "Closing this terminal will stop the backend."
    echo ""
    echo "Frontend: http://localhost:8080"
    echo "Backend:  http://${PC_HOST}:8000"
    # Keep SSH alive
    wait
    exit 0
  fi
done

echo "ERROR: Backend did not start within 40s"
exit 1
