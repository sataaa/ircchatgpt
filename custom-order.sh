#!/bin/bash
set -e

if [ $# -lt 2 ]; then
    echo "Usage: ./custom-order.sh <#channel> <message>"
    exit 1
fi

CHANNEL="$1"
shift
MESSAGE="$*"

echo "$MESSAGE" > "tmp/${CHANNEL}.order"
echo "Order queued for ${CHANNEL}: ${MESSAGE}"
