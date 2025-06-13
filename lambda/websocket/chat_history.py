import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class ChatHistory:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.sessions_table = os.environ.get('CHAT_HISTORY_TABLE')

    def store_chat_message(self, session_id, role, content, key="messages"):
        """
        Store a chat message in DynamoDB
        
        Args:
            session_id: The session ID
            role: The role of the message sender (user or assistant)
            content: The message content
            key: The key to store the message in (messages or router_messages)
        """
        logger.info(f"Storing chat message: {content} for session_id: {session_id}")
        self.sessions_table.update_item(
            Key={
                'session_id': session_id
            },
            UpdateExpression=f"SET {key} = list_append(if_not_exists({key}, :empty_list), :message)",
            ExpressionAttributeValues={
                ':empty_list': [],
                ':message': [{
                    'role': role,
                    'content': {
                        "text": content
                    }
                }]
            }
        )

    def get_chat_messages(self, session_id, key="messages"):
        """
        Get all chat messages for a session
        
        Args:
            session_id: The session ID
            key: The key to get the messages from (messages or router_messages)
        Returns:
            List of chat messages
        """
        response = self.sessions_table.get_item(
            Key={
                'session_id': session_id
            }
        )
        
        if 'Item' not in response or key not in response['Item']:
            return []
            
        messages = response['Item'][key]
        
        return messages