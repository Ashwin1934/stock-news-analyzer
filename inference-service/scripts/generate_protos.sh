#!/bin/bash

# Generate Python code from proto files

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR/.."

# Create generated directory
mkdir -p "$PROJECT_DIR/generated"

# Generate Python code
python -m grpc_tools.protoc \
    -I"$PROJECT_DIR/protos" \
    --python_out="$PROJECT_DIR/generated" \
    --grpc_python_out="$PROJECT_DIR/generated" \
    "$PROJECT_DIR/protos/headlines.proto"

# Create __init__.py
touch "$PROJECT_DIR/generated/__init__.py"

echo "Proto files generated successfully in generated/"