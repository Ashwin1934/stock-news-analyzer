#!/bin/bash

# Run the inference server with a specific profile

PROFILE=${1:-uds}

echo "Starting inference server with profile: $PROFILE"

cd "$(dirname "$0")/.."
python src/inference_server.py "$PROFILE"