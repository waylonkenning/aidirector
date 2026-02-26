#!/bin/bash
DB_PATH="/Volumes/X9 Pro/Video_Archive.db"
read -p "Enter search term (e.g. Tokyo, Ninja, Beach): " SEARCH_TERM
echo "----------------------------------------"
sqlite3 "$DB_PATH" "SELECT filename, path, transcription FROM videos WHERE id IN (SELECT video_id FROM video_search WHERE transcription MATCH '$SEARCH_TERM');"
echo "----------------------------------------"
