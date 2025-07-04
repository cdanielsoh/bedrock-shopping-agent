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
npm run build

# Get the S3 bucket name from CloudFormation output
BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name WebFrontendStack --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucketName`].OutputValue' --output text)

# Check if bucket name was retrieved successfully
if [ -z "$BUCKET_NAME" ]; then
    echo "Error: Could not retrieve S3 bucket name from CloudFormation stack"
    exit 1
fi

# Deploy frontend to S3
echo "Deploying frontend to S3 bucket: $BUCKET_NAME"
aws s3 sync dist/ s3://$BUCKET_NAME

cd ..

echo "Deployment completed successfully!"