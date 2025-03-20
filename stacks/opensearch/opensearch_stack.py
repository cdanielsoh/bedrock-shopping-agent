from aws_cdk import (
    Stack,
    aws_opensearchservice as opensearch,
    aws_opensearchserverless as opensearchserverless,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_lambda as lambda_,
    aws_ec2 as ec2,
    RemovalPolicy,
    CustomResource,
    CfnOutput,
    Duration,
    triggers
)
from aws_cdk.custom_resources import Provider
from constructs import Construct
import json
from datetime import datetime


class OpenSearchServerlessStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for storing CSV data
        data_bucket = s3.Bucket(
            self, "OpenSearchDataBucket",
            bucket_name=f"opensearch-serverless-data-{self.account}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # Upload CSV data to S3 bucket
        s3deploy.BucketDeployment(
            self, "DeployProductsData",
            sources=[s3deploy.Source.asset("./data/opensearch/")],
            destination_bucket=data_bucket
        )

        # Define a valid collection name
        collection_name = "products-collection"

        # Lambda role with necessary permissions (moved earlier for policy references)
        lambda_role = iam.Role(
            self, "IngestLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )

        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "aoss:APIAccessAll",
                    "aoss:List*",
                    "aoss:Create*",
                    "aoss:Update*",
                    "aoss:Delete*",
                ],
                resources=["*"]
            )
        )

        # 1. Create Encryption Policy (required before collection)
        encryption_policy = opensearchserverless.CfnSecurityPolicy(
            self, "CollectionEncryptionPolicy",
            name=f"encryption-policy",
            type="encryption",
            policy=json.dumps({
                "Rules": [{
                    "ResourceType": "collection",
                    "Resource": [f"collection/{collection_name}"]
                }],
                "AWSOwnedKey": True
            })
        )

        # 2. Create Network Policy
        network_policy = opensearchserverless.CfnSecurityPolicy(
            self, "CollectionNetworkPolicy",
            name=f"network-policy",
            type="network",
            policy=json.dumps([{
                "Rules": [{
                    "ResourceType": "collection",
                    "Resource": [f"collection/{collection_name}"]
                }, {
                    "ResourceType": "dashboard",
                    "Resource": [f"collection/{collection_name}"]
                }],
                "AllowFromPublic": True  # For demo purposes only
            }])
        )

        # 3. Create OpenSearch Serverless Collection
        collection = opensearchserverless.CfnCollection(
            self, "ProductsSearchCollection",
            name=collection_name,
            type="VECTORSEARCH",  # Changed from VECTORSEARCH to SEARCH
            description="Collection for product search demo"
        )

        # Add dependencies to ensure proper creation order
        collection.add_dependency(encryption_policy)
        collection.add_dependency(network_policy)

        # 4. Create Data Access Policy with proper format
        data_access_policy = opensearchserverless.CfnAccessPolicy(
            self, "CollectionAccessPolicy",
            name=f"data-access-policy",
            type="data",
            policy=json.dumps([{
                "Rules": [
                    {
                        "ResourceType": "index",
                        "Resource": [f"index/{collection_name}/*"],
                        "Permission": ["aoss:*"]
                    },
                    {
                        "ResourceType": "collection",
                        "Resource": [f"collection/{collection_name}"],
                        "Permission": ["aoss:*"]
                    }
                ],
                "Principal": [
                    lambda_role.role_arn,
                    f"arn:aws:iam::{self.account}:root"
                ]  # Use actual IAM role ARN instead of "*"
            }])
        )

        # Add dependency to ensure collection exists before access policy
        data_access_policy.add_dependency(collection)

        # Requests layer
        requests_layer = lambda_.LayerVersion(
            self, "RequestsLayer",
            code=lambda_.Code.from_asset("./layers/requests"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_9],
            description="Layer containing the requests module"
        )

        # Grant S3 access
        data_bucket.grant_read(lambda_role)

        # Create Lambda function to create index and ingest data
        ingest_lambda = lambda_.Function(
            self, "IngestDataFunction",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_lambda_code()),
            environment={
                "COLLECTION_ENDPOINT": f"{collection.attr_collection_endpoint}",
                "DATA_BUCKET": data_bucket.bucket_name,
                "INDEX_NAME": "products",
                "REGION": self.region
            },
            timeout=Duration.minutes(5),
            layers=[requests_layer],
            role=lambda_role
        )

        # Ensure Lambda waits for access policy to be created
        ingest_lambda.node.add_dependency(data_access_policy)

        # Custom resource to trigger Lambda only after collection is fully ready
        custom_resource = CustomResource(
            self, "IngestTrigger",
            service_token=Provider(
                self, "IngestProvider",
                on_event_handler=ingest_lambda
            ).service_token,
            properties={
                "Timestamp": datetime.now().isoformat()  # Force update on each deployment
            }
        )

        custom_resource.node.add_dependency(collection)
        custom_resource.node.add_dependency(data_access_policy)

        # Output the collection endpoint and bucket name
        CfnOutput(self, "CollectionEndpoint", value=collection.attr_collection_endpoint)
        CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        CfnOutput(self, "DashboardsURL", value=f"https://{collection.attr_dashboard_endpoint}/_dashboards/")

    def _get_lambda_code(self):
        return """
import boto3
import csv
import json
import os
import requests
from requests_aws4auth import AWS4Auth
from io import StringIO
import time

def handler(event, context):
    # Get environment variables
    collection_endpoint = os.environ['COLLECTION_ENDPOINT']
    bucket_name = os.environ['DATA_BUCKET']
    index_name = os.environ['INDEX_NAME']
    region = os.environ.get('AWS_REGION')

    # Initialize S3 client
    s3 = boto3.client('s3')

    # Create AWS4Auth for authentication - CRITICAL CHANGE: service is 'aoss' for serverless
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        'aoss', 
        session_token=credentials.token
    )

    try:
        # Create the OpenSearch index with mapping
        create_index(collection_endpoint, index_name, awsauth)

        # Get the CSV file from S3
        response = s3.get_object(Bucket=bucket_name, Key='products.csv')
        csv_content = response['Body'].read().decode('utf-8')

        # Parse CSV
        csv_reader = csv.DictReader(StringIO(csv_content))

        # Bulk insert data
        bulk_index_data(collection_endpoint, index_name, csv_reader, awsauth)

        return {
            'statusCode': 200,
            'body': json.dumps('Successfully indexed products data')
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }

def create_index(endpoint, index_name, auth):
    url = f"{endpoint}/{index_name}"
    headers = {'Content-Type': 'application/json'}

    # Define the index mapping
    mapping = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 1
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "url": {"type": "keyword"},
                "sk": {"type": "keyword"},
                "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "category": {"type": "keyword"},
                "style": {"type": "keyword"},
                "description": {"type": "text"},
                "aliases": {"type": "text"},
                "price": {"type": "float"},
                "image": {"type": "keyword"},
                "gender_affinity": {"type": "keyword"},
                "current_stock": {"type": "integer"},
                "featured": {"type": "boolean"}
            }
        }
    }

    # Check if index exists
    try:
        response = requests.head(url, auth=auth, verify=True)
        if response.status_code == 200:
            print(f"Index {index_name} already exists")
            return
    except Exception as e:
        print(f"Error checking if index exists: {str(e)}")

    # Create the index with mapping
    try:
        response = requests.put(url, auth=auth, headers=headers, json=mapping, verify=True)
        print(f"Index creation status code: {response.status_code}")
        print(f"Response body: {response.text}")
        response.raise_for_status()
        print(f"Created index {index_name} with mapping")
    except Exception as e:
        print(f"Error creating index: {str(e)}")
        raise

def bulk_index_data(endpoint, index_name, csv_reader, auth):
    url = f"{endpoint}/_bulk"
    headers = {'Content-Type': 'application/x-ndjson'}

    # Process in batches of 500 documents
    batch_size = 500
    batch = []
    count = 0
    total_indexed = 0

    for row in csv_reader:
        # Convert empty strings to None/null
        for key, value in row.items():
            if value == '':
                row[key] = None

        # Handle numeric and boolean fields
        if row.get('price') is not None:
            row['price'] = float(row['price'])
        if row.get('current_stock') is not None:
            row['current_stock'] = int(row['current_stock'])
        if row.get('featured') is not None:
            row['featured'] = row['featured'].lower() == 'true'

        # Create index action
        action = {
            "index": {
                "_index": index_name,
            }
        }

        # Add to batch
        batch.append(json.dumps(action))
        batch.append(json.dumps(row))
        count += 1

        # Send batch if it reaches batch_size
        if count >= batch_size:
            send_batch(url, headers, batch, auth)
            total_indexed += count
            print(f"Indexed {total_indexed} documents")
            batch = []
            count = 0

    # Send any remaining documents
    if batch:
        send_batch(url, headers, batch, auth)
        total_indexed += count
        print(f"Indexed {total_indexed} documents")

    # Allow time for indexing to complete
    time.sleep(2)

    # Refresh the index to make documents searchable
    refresh_url = f"{endpoint}/{index_name}/_refresh"
    try:
        requests.post(refresh_url, auth=auth, verify=True)
        print(f"Refreshed index {index_name}")
    except Exception as e:
        print(f"Error refreshing index: {str(e)}")

def send_batch(url, headers, batch, auth):
    body = '\\n'.join(batch) + '\\n'
    try:
        response = requests.post(url, auth=auth, headers=headers, data=body, verify=True)

        # Added better error logging
        if response.status_code >= 400:
            print(f"Error response: {response.status_code}")
            print(f"Response body: {response.text}")

        response.raise_for_status()

        # Check for errors in the response
        result = response.json()
        if result.get('errors', False):
            errors = [item for item in result.get('items', []) if item.get('index', {}).get('error')]
            print(f"Bulk indexing had {len(errors)} errors")
            for error in errors[:5]:  # Print first 5 errors
                print(f"Error: {error}")
    except Exception as e:
        print(f"Error sending batch: {str(e)}")
        raise
"""
