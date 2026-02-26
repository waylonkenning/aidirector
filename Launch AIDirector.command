#!/bin/bash
# Launch AIDirector.command
cd "$(dirname "$0")"

echo "Starting AI Director Services..."

# Cleanup old processes
echo "Cleaning up ports 8000 and 3000..."
lsof -ti:8000 | xargs kill -9 >/dev/null 2>&1 || true
lsof -ti:3000 | xargs kill -9 >/dev/null 2>&1 || true

# Setup trap to kill background processes when script exits
trap 'kill $(jobs -p)' EXIT

# Start FastAPI backend in the background
echo "Launching Backend..."
cd backend
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
echo ""
echo "=========================================================="
echo "=> Frontend App is now available at: http://localhost:3000"
echo "=========================================================="
echo ""
npm run dev
