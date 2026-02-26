#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS_FILE="$SCRIPT_DIR/backend/settings.json"

# Read DB path from settings.json, fallback to local Video_Archive.db
if command -v python3 &> /dev/null && [ -f "$SETTINGS_FILE" ]; then
    DB_PATH=$(python3 -c "import json; f=open('$SETTINGS_FILE'); print(json.load(f).get('dbPath','$SCRIPT_DIR/Video_Archive.db'))")
else
    DB_PATH="$SCRIPT_DIR/Video_Archive.db"
fi

read -p "Enter search term (e.g. Tokyo, Ninja, Beach): " SEARCH_TERM
echo "----------------------------------------"
sqlite3 "$DB_PATH" "SELECT filename, path, transcription FROM videos WHERE id IN (SELECT video_id FROM video_search WHERE transcription MATCH '$SEARCH_TERM');"
echo "----------------------------------------"
