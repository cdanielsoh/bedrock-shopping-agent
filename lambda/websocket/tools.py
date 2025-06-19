from abc import ABC, abstractmethod
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
import os
import boto3
import re
from boto3.dynamodb.conditions import Key
import logging

REGION = 'us-west-2'


logger = logging.getLogger()
logger.setLevel(logging.INFO)


class Tool(ABC):
    @abstractmethod
    def execute(self, *args, **kwargs):
        pass

    @abstractmethod
    def get_tool_name(self):
        pass

    @abstractmethod
    def get_tool_spec(self):
        pass


class KeywordProductSearchTool(Tool):
    def __init__(self, os_host: str, index: str, cloudfront_url: str, dynamodb: boto3.resource, reviews_table: str):
        self.oss_client = OpenSearch(
            hosts=[{'host': os_host, 'port': 443}],
            http_auth=AWSV4SignerAuth(
                boto3.Session().get_credentials(),
                REGION,
                'aoss'
            ),
            use_ssl=True,
            verify_certs=True,
            http_compress=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=30
        )
        self.cloudfront_url = cloudfront_url
        self.index = index
        self.dynamodb = dynamodb
        self.reviews_table = reviews_table

    def execute(self, query_keywords: str) -> list:
        logger.info(f"Executing keyword product search with query keywords: {query_keywords}")
        body = {
            "_source": ["id", "image_url", "name", "description", "price", "gender_affinity", "current_stock"],
            "query": {
                "multi_match": {
                    "query": query_keywords,
                    "fields": ["name", "category", "style", "description"],
                }
            },
            "size": 10
        }

        response = self.oss_client.search(
            index=self.index,
            body=body,
        )

        search_results = response['hits']['hits']

        item_ids = [hit['_source']['id'] for hit in search_results]

        # Remove duplicates based on item_id
        seen_ids = set()
        unique_results = []
        for hit in search_results:
            item_id = hit['_source']['id']
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                unique_results.append(hit)
        
        item_ids = [hit['_source']['id'] for hit in unique_results]

        logger.info(f"Found {len(item_ids)} items in search results")

        if item_ids:

            for hit in unique_results:
                hit['_source']['image_url'] = f"{self.cloudfront_url}/{hit['_source']['id']}.jpg"

            product_reviews = GetProductReviewsTool(self.dynamodb, self.reviews_table).execute(item_ids)

            for hit in unique_results:
                hit['_source']['reviews'] = product_reviews.get(hit['_source']['id'], {})
            
            return unique_results

        else:
            return []

    def get_tool_name(self):
        return "keyword_product_search"

    def get_tool_spec(self):
        return {
            "toolSpec": {
                "name": "keyword_product_search",
                "description": "Search for products by keywords in the product catalog",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "query_keywords": {
                                "type": "string",
                                "description": "The keywords to search for in the product catalog"
                            }
                        },
                        "required": ["query_keywords"]
                    }
                }
            }
        }

class GetProductReviewsTool(Tool):
    def __init__(self, dynamodb: boto3.resource, reviews_table: str):
        self.dynamodb = dynamodb
        self.reviews_table = reviews_table

    def execute(self, product_ids: list) -> dict:
        """
        Get reviews for multiple products using BatchGetItem.
        
        Args:
            product_ids: List of product IDs to retrieve reviews for
            
        Returns:
            Dictionary mapping product IDs to their review data
        """
        logger.info(f"Executing get product reviews with product IDs: {product_ids}")
        try:
            # BatchGetItem can retrieve up to 100 items at once
            if len(product_ids) > 100:
                product_ids = product_ids[:100]  # Limit to first 100
                
            # Prepare the request items format for BatchGetItem
            request_items = {
                self.reviews_table: {
                    'Keys': [{'product_id': product_id} for product_id in product_ids]
                }
            }
            
            # Execute the BatchGetItem operation
            response = self.dynamodb.batch_get_item(RequestItems=request_items)
            
            # Process the results
            reviews_by_id = {}
            if 'Responses' in response and 'ReviewsTable' in response['Responses']:
                for item in response['Responses']['ReviewsTable']:
                    product_id = item['product_id']
                    reviews_by_id[product_id] = {
                        'avg_rating': item.get('avg_rating'),
                        'positive_keywords': item.get('positive_keywords'),
                        'negative_keywords': item.get('negative_keywords'),
                        'review_summary': item.get('review_summary')
                    }
                    
            return reviews_by_id
            
        except Exception as e:
            print(f"Error retrieving product reviews: {str(e)}")
            return {}
        
    def get_tool_name(self):
        return "get_product_reviews"
    
    def get_tool_spec(self):
        return {
            "toolSpec": {
                "name": "get_product_reviews",
                "description": "Get reviews for multiple products",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "product_ids": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "description": "The ID of the product to get reviews for"
                                }
                            }
                        },
                        "required": ["product_ids"]
                    }
                }
            }
        }


class GetOrderHistoryTool(Tool):
    def __init__(self, orders_table: str, oss_client: OpenSearch, index: str):
        self.orders_table = boto3.resource('dynamodb', region_name=REGION).Table(orders_table)
        self.oss_client = oss_client
        self.index = index

    def execute(self, user_id: str) -> dict:
        """
        Get order history for a user
        """
        logger.info(f"Executing get order history with user ID: {user_id}")
        try:
            response = self.orders_table.query(
                IndexName='UserStatusIndex',
                KeyConditionExpression=Key('user_id').eq(int(user_id))
            )
            
            orders = response.get('Items', [])

            item_ids = [order.get('item_id') for order in orders]
            
            item_details = self.oss_client.search(
                index=self.index,
                body={
                    "_source": ["id", "image_url", "name", "description", "price", "gender_affinity", "current_stock"],
                    "query": {
                        "terms": {
                            "id": item_ids
                        }
                    }
                }
            )

            formatted_orders = []
            for order, item_detail in zip(orders, item_details['hits']['hits']):
                item_id = order.get('item_id')
                
                formatted_order = {
                    "order_id": order.get('order_id'),
                    "timestamp": order.get('timestamp'),
                    "item_id": item_id,
                    "delivery_status": order.get('delivery_status'),
                    "item_details": item_detail['_source']
                }
                formatted_orders.append(formatted_order)

            return formatted_orders
            
        except Exception as e:
            print(f"Error retrieving order history: {str(e)}")
            return []
        
    def get_tool_name(self):
        return "get_order_history_with_user_id"
    
    def get_tool_spec(self):
        return {
            "toolSpec": {
                "name": "get_order_history_with_user_id",
                "description": "Get order history for a user",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "string",
                                "description": "The ID of the user to get order history for"
                            }
                        },
                        "required": ["user_id"]
                    }
                }
            }
        }
    

class GetUserInfoTool(Tool):
    def __init__(self, user_table: str):
        self.user_table = boto3.resource('dynamodb', region_name=REGION).Table(user_table)

    def execute(self, user_id: str) -> dict:
        if not user_id:
            return "Error: user_id is required"
        
        try:
            response = self.user_table.get_item(
                Key={
                    'id': user_id
                }
            )

            user = response.get('Item')

            if not user:
                return "Error: User not found"
            
            return "User info: " + str(user)

        except Exception as e:
            error_msg = f"Error getting user address: {str(e)}"
            print(error_msg)
            return "Error: " + error_msg

    def get_tool_name(self):
        return "get_user_info"
    
    def get_tool_spec(self):
        return {
            "toolSpec": {
                "name": "get_user_info",
                "description": "Get user info for a user",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "string",
                                "description": "The ID of the user to get info for"
                            }
                        },
                        "required": ["user_id"]
                    }
                }
            }
        }
