#!/bin/sh
# Start AliExpress Reader on http://127.0.0.1:8835 (localhost only)
cd "$(dirname "$0")"
pkill -f "aliexpress-reader/server.py" 2>/dev/null
setsid nohup python3 "$PWD/server.py" > server.log 2>&1 &
sleep 1; echo "AliExpress Reader: http://127.0.0.1:8835"
