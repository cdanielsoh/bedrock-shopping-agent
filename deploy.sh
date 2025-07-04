#!/bin/bash

# Install AWS CDK
npm -g install aws-cdk

# Install requirements
pip install -r requirements.txt

# Install required lambda layers
bash install_layers.sh

# Bootstrap CDK
cdk bootstrap

# Deploy CDK
cdk deploy --require-approval never