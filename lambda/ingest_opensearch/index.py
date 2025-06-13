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