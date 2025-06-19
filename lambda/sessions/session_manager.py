"""
Session Management API for Bedrock Shopping Agent
Handles CRUD operations for user conversation sessions
"""

import json
import boto3
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
sessions_table = dynamodb.Table(os.environ.get('SESSIONS_TABLE', 'UserSessionsTable'))

def lambda_handler(event, context):
    """
    Handle session management API requests
    """
    try:
        print(f"Received event: {json.dumps(event)}")
        
        http_method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', ''))
        path = event.get('requestContext', {}).get('http', {}).get('path', event.get('path', ''))
        
        # Handle CORS preflight requests
        if http_method == 'OPTIONS':
            return create_response(200, {'message': 'CORS preflight'})
        
        # Extract path parameters
        path_params = event.get('pathParameters') or {}
        user_id = path_params.get('userId')
        session_id = path_params.get('sessionId')
        
        # Extract query parameters
        query_params = event.get('queryStringParameters') or {}
        
        print(f"Method: {http_method}, Path: {path}")
        print(f"User ID: {user_id}, Session ID: {session_id}")
        
        if http_method == 'GET' and '/sessions/' in path and user_id:
            # Get sessions for user: GET /sessions/{userId}
            return get_user_sessions(user_id)
        elif http_method == 'POST' and path.endswith('/sessions'):
            # Create new session: POST /sessions
            body = json.loads(event.get('body', '{}'))
            return create_session(body)
        elif http_method == 'PUT' and session_id:
            # Update session: PUT /sessions/{sessionId}
            body = json.loads(event.get('body', '{}'))
            return update_session(session_id, body)
        elif http_method == 'DELETE' and session_id:
            # Delete session: DELETE /sessions/{sessionId}
            return delete_session(session_id)
        else:
            return create_response(404, {'error': 'Not found', 'method': http_method, 'path': path})
            
    except Exception as e:
        print(f"Error in session management: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': str(e)})

def create_response(status_code: int, body: dict):
    """Create a standardized API response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body, default=str)
    }

def get_user_sessions(user_id: str):
    """Get all sessions for a user"""
    try:
        print(f"Getting sessions for user: {user_id}")
        
        response = sessions_table.query(
            IndexName='UserIdIndex',
            KeyConditionExpression='user_id = :user_id',
            ExpressionAttributeValues={':user_id': user_id},
            ScanIndexForward=False,  # Most recent first
            Limit=20
        )
        
        sessions = []
        for item in response['Items']:
            sessions.append({
                'sessionId': item['session_id'],
                'userId': item['user_id'],
                'title': item.get('title', f"Session {item['created_at'][:10]}"),
                'createdAt': item['created_at'],
                'lastUsed': item['last_used'],
                'messageCount': int(item.get('message_count', 0))
            })
        
        print(f"Found {len(sessions)} sessions for user {user_id}")
        return create_response(200, {'sessions': sessions})
        
    except Exception as e:
        print(f"Error getting user sessions: {str(e)}")
        return create_response(500, {'error': str(e)})

def create_session(data: Dict[str, Any]):
    """Create a new session"""
    try:
        print(f"Creating session with data: {data}")
        
        now = datetime.now(timezone.utc).isoformat()
        session_id = data.get('sessionId')
        user_id = data.get('userId')
        title = data.get('title', f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        if not session_id or not user_id:
            return create_response(400, {'error': 'sessionId and userId are required'})
        
        sessions_table.put_item(
            Item={
                'session_id': session_id,
                'user_id': user_id,
                'title': title,
                'created_at': now,
                'last_used': now,
                'message_count': 0,
                'ttl': int(datetime.now(timezone.utc).timestamp()) + (30 * 24 * 60 * 60)  # 30 days
            }
        )
        
        print(f"Created session {session_id} for user {user_id}")
        return create_response(201, {
            'sessionId': session_id,
            'message': 'Session created successfully'
        })
        
    except Exception as e:
        print(f"Error creating session: {str(e)}")
        return create_response(500, {'error': str(e)})

def update_session(session_id: str, data: Dict[str, Any]):
    """Update session (e.g., last used time, title)"""
    try:
        print(f"Updating session {session_id} with data: {data}")
        
        update_expression = "SET last_used = :last_used"
        expression_values = {':last_used': datetime.now(timezone.utc).isoformat()}
        
        if 'title' in data:
            update_expression += ", title = :title"
            expression_values[':title'] = data['title']
            
        if 'messageCount' in data:
            update_expression += ", message_count = :message_count"
            expression_values[':message_count'] = data['messageCount']
        
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        print(f"Updated session {session_id}")
        return create_response(200, {'message': 'Session updated successfully'})
        
    except Exception as e:
        print(f"Error updating session: {str(e)}")
        return create_response(500, {'error': str(e)})

def delete_session(session_id: str):
    """Delete a session"""
    try:
        print(f"Deleting session {session_id}")
        
        sessions_table.delete_item(Key={'session_id': session_id})
        
        print(f"Deleted session {session_id}")
        return create_response(200, {'message': 'Session deleted successfully'})
        
    except Exception as e:
        print(f"Error deleting session: {str(e)}")
        return create_response(500, {'error': str(e)})
