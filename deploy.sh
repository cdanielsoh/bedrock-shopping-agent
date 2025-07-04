#!/bin/bash

# Install AWS CDK
npm -g install aws-cdk

# Install requirements
pip install -r requirements.txt

# Install required lambda layers
bash install_layers.sh

# Install frontend dependencies
echo "Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Bootstrap CDK
cdk bootstrap

# Deploy CDK stacks
echo "Deploying CDK stacks..."
cdk deploy OpenSearchServerlessStack --require-approval never
cdk deploy DynamoDbStack --require-approval never
cdk deploy WebFrontendStack --require-approval never

# Build and deploy frontend
echo "Building and deploying frontend..."
cd frontend

# Get API endpoints from CloudFormation outputs
echo "Retrieving API endpoints from CloudFormation..."
WEBSOCKET_URL=$(aws cloudformation describe-stacks --stack-name WebFrontendStack --query 'Stacks[0].Outputs[?OutputKey==`WebSocketURL`].OutputValue' --output text)
HTTP_API_URL=$(aws cloudformation describe-stacks --stack-name WebFrontendStack --query 'Stacks[0].Outputs[?OutputKey==`HttpApiUrl`].OutputValue' --output text)
BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name WebFrontendStack --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucketName`].OutputValue' --output text)

# Check if all required values were retrieved
if [ -z "$WEBSOCKET_URL" ] || [ -z "$HTTP_API_URL" ] || [ -z "$BUCKET_NAME" ]; then
    echo "Error: Could not retrieve required values from CloudFormation stack"
    echo "WebSocket URL: $WEBSOCKET_URL"
    echo "HTTP API URL: $HTTP_API_URL"
    echo "Bucket Name: $BUCKET_NAME"
    exit 1
fi

echo "Retrieved endpoints:"
echo "WebSocket URL: $WEBSOCKET_URL"
echo "HTTP API URL: $HTTP_API_URL"
echo "S3 Bucket: $BUCKET_NAME"

# Update the frontend configuration with the correct API endpoints
echo "Updating frontend configuration..."
sed -i "s|const ws = new WebSocketService('.*');|const ws = new WebSocketService('$WEBSOCKET_URL');|g" src/components/ChatBox.tsx
sed -i "s|const httpApiUrl = '.*';|const httpApiUrl = '$HTTP_API_URL';|g" src/components/ChatBox.tsx

# Build the frontend
echo "Building frontend..."
npm run build

# Deploy frontend to S3
echo "Deploying frontend to S3 bucket: $BUCKET_NAME"
aws s3 sync dist/ s3://$BUCKET_NAME

cd ..

echo "Deployment completed successfully!"