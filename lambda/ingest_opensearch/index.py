import boto3
import csv
import json
import os
import requests
from requests_aws4auth import AWS4Auth
from io import StringIO
import time
import random

def handler(event, context):
    # Handle CloudFormation custom resource events
    request_type = event.get('RequestType', 'Create')
    
    # Only process on Create events, skip Update and Delete
    if request_type != 'Create':
        print(f"Skipping ingest for RequestType: {request_type}")
        return {
            'statusCode': 200,
            'body': json.dumps(f'Skipped ingest for {request_type} event')
        }
    
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
        # Wait for OpenSearch collection to be fully ready
        if not wait_for_collection_ready(collection_endpoint, awsauth):
            raise Exception("OpenSearch collection did not become ready within timeout period")

        # Check if index already exists and has data
        if index_has_data(collection_endpoint, index_name, awsauth):
            print(f"Index {index_name} already has data, skipping ingest")
            return {
                'statusCode': 200,
                'body': json.dumps('Index already contains data, skipping ingest')
            }

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

def wait_for_collection_ready(endpoint, auth, max_attempts=30, base_delay=10):
    """
    Wait for OpenSearch Serverless collection to be fully ready with exponential backoff
    """
    print(f"Waiting for OpenSearch collection to be ready: {endpoint}")
    
    for attempt in range(max_attempts):
        try:
            # Try a simple health check by attempting to list indices
            url = f"{endpoint}/_cat/indices"
            response = requests.get(url, auth=auth, verify=True, timeout=30)
            
            if response.status_code == 200:
                print(f"OpenSearch collection is ready after {attempt + 1} attempts")
                return True
            elif response.status_code in [403, 401]:
                # Authentication/authorization issues - might indicate collection isn't fully ready
                print(f"Attempt {attempt + 1}: Authentication/authorization not ready (status: {response.status_code})")
            else:
                print(f"Attempt {attempt + 1}: Collection not ready (status: {response.status_code})")
                
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1}: Connection error - {str(e)}")
        except Exception as e:
            print(f"Attempt {attempt + 1}: Unexpected error - {str(e)}")
        
        if attempt < max_attempts - 1:
            # Exponential backoff with jitter
            delay = base_delay * (2 ** min(attempt, 6)) + random.uniform(0, 5)
            print(f"Waiting {delay:.1f} seconds before next attempt...")
            time.sleep(delay)
    
    print(f"OpenSearch collection did not become ready after {max_attempts} attempts")
    return False

def index_has_data(endpoint, index_name, auth, max_retries=5):
    """Check if the index exists and has data with retry logic"""
    url = f"{endpoint}/{index_name}/_count"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, auth=auth, verify=True, timeout=30)
            if response.status_code == 200:
                result = response.json()
                count = result.get('count', 0)
                print(f"Index {index_name} has {count} documents")
                return count > 0
            elif response.status_code == 404:
                print(f"Index {index_name} does not exist")
                return False
            else:
                print(f"Attempt {attempt + 1}: Error checking index count: {response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
                return False
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error checking if index has data: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt + random.uniform(0, 1))
                continue
            return False
    
    return False

def create_index(endpoint, index_name, auth, max_retries=5):
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

    # Check if index exists with retry logic
    for attempt in range(max_retries):
        try:
            response = requests.head(url, auth=auth, verify=True, timeout=30)
            if response.status_code == 200:
                print(f"Index {index_name} already exists")
                return
            elif response.status_code == 404:
                # Index doesn't exist, proceed to create it
                break
            else:
                print(f"Attempt {attempt + 1}: Unexpected status checking index existence: {response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error checking if index exists: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt + random.uniform(0, 1))
                continue

    # Create the index with mapping and retry logic
    for attempt in range(max_retries):
        try:
            response = requests.put(url, auth=auth, headers=headers, json=mapping, verify=True, timeout=60)
            print(f"Index creation attempt {attempt + 1} - status code: {response.status_code}")
            print(f"Response body: {response.text}")
            
            if response.status_code in [200, 201]:
                print(f"Created index {index_name} with mapping")
                return
            elif response.status_code == 400 and "resource_already_exists_exception" in response.text.lower():
                print(f"Index {index_name} already exists")
                return
            else:
                print(f"Attempt {attempt + 1}: Failed to create index - status: {response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
                else:
                    response.raise_for_status()
                    
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error creating index: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt + random.uniform(0, 1))
                continue
            else:
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

def send_batch(url, headers, batch, auth, max_retries=3):
    body = '\n'.join(batch) + '\n'
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, auth=auth, headers=headers, data=body, verify=True, timeout=60)

            # Added better error logging
            if response.status_code >= 400:
                print(f"Attempt {attempt + 1}: Error response: {response.status_code}")
                print(f"Response body: {response.text}")
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
                else:
                    response.raise_for_status()

            # Check for errors in the response
            result = response.json()
            if result.get('errors', False):
                errors = [item for item in result.get('items', []) if item.get('index', {}).get('error')]
                print(f"Bulk indexing had {len(errors)} errors")
                for error in errors[:5]:  # Print first 5 errors
                    print(f"Error: {error}")
                    
                # If there are errors but some documents succeeded, don't retry
                if len(errors) < len(result.get('items', [])) / 2:  # Less than 50% errors
                    print("Continuing despite some errors as majority succeeded")
                    return
                elif attempt < max_retries - 1:
                    print(f"Too many errors, retrying batch (attempt {attempt + 1})")
                    time.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
                else:
                    raise Exception(f"Bulk indexing failed with {len(errors)} errors")
            
            # Success case
            return
            
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error sending batch: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt + random.uniform(0, 1))
                continue
            else:
                raise