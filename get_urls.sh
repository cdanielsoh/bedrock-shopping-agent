#!/bin/bash

echo "🚀 Bedrock Shopping Agent - Deployment URLs"
echo "============================================="

# Get WebSocket URL
WEBSOCKET_URL=$(aws cloudformation describe-stacks --stack-name WebFrontendStack --query 'Stacks[0].Outputs[?OutputKey==`WebSocketURL`].OutputValue' --output text)
echo "📡 WebSocket API: $WEBSOCKET_URL"

# Get HTTP API URL
HTTP_API_URL=$(aws cloudformation describe-stacks --stack-name WebFrontendStack --query 'Stacks[0].Outputs[?OutputKey==`HttpApiUrl`].OutputValue' --output text)
echo "🔗 HTTP API: $HTTP_API_URL"

# Get Website URL
WEBSITE_URL=$(aws cloudformation describe-stacks --stack-name WebFrontendStack --query 'Stacks[0].Outputs[?OutputKey==`WebsiteURL`].OutputValue' --output text)
echo "🌐 Website: $WEBSITE_URL"

# Get Images URL
IMAGES_URL=$(aws cloudformation describe-stacks --stack-name WebFrontendStack --query 'Stacks[0].Outputs[?OutputKey==`ImagesURL`].OutputValue' --output text)
echo "🖼️  Images CDN: $IMAGES_URL"

echo ""
echo "✅ Session Management API Endpoints:"
echo "   GET    $HTTP_API_URL/sessions/{userId}     - Get user sessions"
echo "   POST   $HTTP_API_URL/sessions             - Create new session"
echo "   PUT    $HTTP_API_URL/sessions/{sessionId} - Update session"
echo "   DELETE $HTTP_API_URL/sessions/{sessionId} - Delete session"

echo ""
echo "🎯 Open your shopping assistant: $WEBSITE_URL"
