#!/bin/bash

# Test script for payment-ingester Xendit webhook
# Usage: ./test_webhook.sh

set -e

echo "Starting payment-ingester test..."
echo ""

# Check if XENDIT_WEBHOOK_SECRET is set
if [ -z "$XENDIT_WEBHOOK_SECRET" ]; then
    echo "Warning: XENDIT_WEBHOOK_SECRET not set, using default"
    export XENDIT_WEBHOOK_SECRET="dev-xendit-webhook-secret"
fi

# Check if PUBSUB_EMULATOR_HOST is set
if [ -z "$PUBSUB_EMULATOR_HOST" ]; then
    echo "Warning: PUBSUB_EMULATOR_HOST not set, using default"
    export PUBSUB_EMULATOR_HOST="localhost:8085"
fi

# Start the server in background
echo "Starting payment-ingester on http://localhost:8001"
python run.py &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Test health check
echo "Testing health check endpoint..."
HEALTH_RESPONSE=$(curl -s http://localhost:8001/)
echo "Health check response: $HEALTH_RESPONSE"

if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo "✓ Health check passed"
else
    echo "✗ Health check failed"
    kill $SERVER_PID
    exit 1
fi

echo ""
echo "Server is running. To test Xendit webhooks:"
echo "1. Use a tool like ngrok to expose localhost:8001"
echo "2. Configure the ngrok URL in Xendit dashboard"
echo "3. Send test webhooks from Xendit dashboard"
echo ""
echo "Press Ctrl+C to stop the server"

# Keep server running until user interrupts
wait $SERVER_PID
