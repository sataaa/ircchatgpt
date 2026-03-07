#!/bin/bash
set -e
podman exec ircchatgpt /app/venv/bin/python -m pytest app/test_bot.py -v
