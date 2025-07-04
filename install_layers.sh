#!/bin/bash

# Simple virtual environment approach for Lambda layers
set -e

PYTHON_CMD="python3"

# Clean start
rm -rf layers/ temp_venv/
mkdir -p layers

# Function to create layer with virtual environment
create_layer() {
    local layer_name=$1
    local packages=$2
    
    echo "Creating $layer_name layer..."
    
    # Create temporary virtual environment
    $PYTHON_CMD -m venv temp_venv
    source temp_venv/bin/activate
    
    # Install packages in clean environment
    pip install --upgrade pip
    pip install $packages
    
    # Copy to layer directory
    mkdir -p "layers/$layer_name/python"
    cp -r temp_venv/lib/python*/site-packages/* "layers/$layer_name/python/"
    
    # Cleanup venv
    deactivate
    rm -rf temp_venv
    
    # Clean unnecessary files
    find "layers/$layer_name/python" -name "*.pyc" -delete
    find "layers/$layer_name/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    
    echo "✅ $layer_name layer created"
}

# Create layers
create_layer "requests" "requests requests-aws4auth idna urllib3 certifi"
create_layer "opensearchpy" "opensearch-py requests requests-aws4auth"  
create_layer "boto3" "boto3 botocore"
create_layer "strands" "strands-agents strands-agents-tools"

echo "🎉 All layers created successfully!"
du -sh layers/*