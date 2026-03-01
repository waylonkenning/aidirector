#!/bin/bash
# Launch AIDirector.command
cd "$(dirname "$0")"

echo "Starting AI Director Services..."

# Cleanup old processes
echo "Cleaning up ports 8000 and 3000..."
lsof -ti:8000 | xargs kill -9 >/dev/null 2>&1 || true
lsof -ti:3000 | xargs kill -9 >/dev/null 2>&1 || true

# Next.js starts parent and worker processes. `lsof` on port 3000 only kills the worker, 
# leaving the parent holding the .next/dev/lock which causes subsequent launches to hang.
pkill -f "next dev" >/dev/null 2>&1 || true
rm -f frontend_app/.next/dev/lock >/dev/null 2>&1 || true

# Setup trap to kill background processes when script exits
trap 'kill $(jobs -p)' EXIT

# Export explicitly to prevent any hung/interactive prompts on first startup
export NEXT_TELEMETRY_DISABLED=1

# Check and install backend dependencies if missing
echo "Checking Backend Environment..."
cd backend
if [ ! -d "venv" ]; then
    echo "First time setup: Installing Python dependencies (this may take a few minutes)..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Start FastAPI backend in the background
echo "Launching Backend..."
python3 -m uvicorn main:app --reload --port 8000 > /dev/null 2>&1 &
BACKEND_PID=$!

# Wait for backend to be ready
echo -n "Waiting for backend to initialize..."
for i in {1..10}; do
    if curl -s http://localhost:8000/api/status > /dev/null; then
        echo " Ready!"
        break
    fi
    echo -n "."
    sleep 1
done

# Start Next.js frontend
cd ../frontend_app

if [ ! -d "node_modules" ]; then
    echo "First time setup: Installing Frontend UI dependencies..."
    npm install
fi

echo ""
echo "=========================================================="
echo "=> Frontend App is now available at: http://localhost:3000"
echo "=========================================================="
echo ""
npm run dev
