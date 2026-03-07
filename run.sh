#!/bin/bash
set -e

podman stop ircchatgpt 2>/dev/null || true
podman rm ircchatgpt 2>/dev/null || true

podman build -t ircchatgpt .

mkdir -p "$(pwd)/tmp"
chmod a+w "$(pwd)/tmp"

podman run -d --name ircchatgpt --restart unless-stopped \
  -v "$(pwd)/chat.conf:/app/chat.conf" \
  -v "$(pwd)/tmp:/app/tmp" \
  ircchatgpt

echo "Bot started. Follow logs with: podman logs -f ircchatgpt"
