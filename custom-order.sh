#!/bin/bash
set -e

CHANNEL="$1"
shift

# Accept channel with or without leading #
if [ -z "$CHANNEL" ]; then
    echo "Error: first argument must be a channel name."
    echo "Example: ./custom-order.sh notes say something about pizza"
    exit 1
fi
[[ "$CHANNEL" == \#* ]] || CHANNEL="#${CHANNEL}"

MESSAGE="$*"
if [ -z "$MESSAGE" ]; then
    echo "Error: order message cannot be empty."
    echo "Example: ./custom-order.sh notes say something about pizza"
    exit 1
fi

echo "$MESSAGE" > "tmp/${CHANNEL}.order"
echo "Order queued for ${CHANNEL}: ${MESSAGE}"
