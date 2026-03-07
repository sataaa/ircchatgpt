#!/bin/bash
set -e

podman stop ircchatgpt 2>/dev/null || true
podman rm ircchatgpt 2>/dev/null || true

podman build -t ircchatgpt .

podman run -d --name ircchatgpt --restart unless-stopped \
  -v "$(pwd)/chat.conf:/app/chat.conf" \
  ircchatgpt

echo "Bot started. Follow logs with: podman logs -f ircchatgpt"
