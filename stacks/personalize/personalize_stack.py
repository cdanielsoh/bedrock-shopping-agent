from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_s3_deployment as s3deploy,
    RemovalPolicy,
    CfnOutput,
    Duration,
    triggers
)
from constructs import Construct


class PersonalizeDataImportStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for storing datasets
        data_bucket = s3.Bucket(
            self, "PersonalizeDataBucket",
            bucket_name=f"personalize-data-{self.account}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        data_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                principals=[
                    iam.ServicePrincipal("personalize.amazonaws.com")
                ],
                resources=[
                    data_bucket.bucket_arn,
                    f"{data_bucket.bucket_arn}/*"
                ]
            )
        )

        # Upload data to S3 bucket
        s3deploy.BucketDeployment(
            self, "DeployPersonalizeData",
            sources=[s3deploy.Source.asset("./data/personalize")],
            destination_bucket=data_bucket,
        )

        # Create IAM role for Personalize
        personalize_role = iam.Role(
            self, "PersonalizeRole",
            assumed_by=iam.ServicePrincipal("personalize.amazonaws.com")
        )

        # Add permissions to the role
        personalize_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                resources=[
                    data_bucket.bucket_arn,
                    f"{data_bucket.bucket_arn}/*"
                ]
            )
        )

        # Define schemas
        items_schema = {
            "name": "ItemsSchema",
            "schema": """
            {
                "type": "record",
                "name": "Items",
                "namespace": "com.amazonaws.personalize.schema",
                "fields": [
                    {
                        "name": "ITEM_ID",
                        "type": "string"
                    },
                    {
                        "name": "CATEGORY_L1",
                        "type": "string",
                        "categorical": true
                    },
                    {
                        "name": "PRICE",
                        "type": "float"
                    },
                    {
                        "name": "CATEGORY_L2",
                        "type": [
                            "null",
                            "string"
                        ],
                        "categorical": true
                    },
                    {
                        "name": "PRODUCT_DESCRIPTION",
                        "type": "string",
                        "textual": true
                    },
                    {
                        "name": "GENDER",
                        "type": [
                            "null",
                            "string"
                        ],
                        "categorical": true
                    }
                ],
                "version": "1.0"
            }
            """
        }

        users_schema = {
            "name": "UsersSchema",
            "schema": """
            {
                "type": "record",
                "name": "Users",
                "namespace": "com.amazonaws.personalize.schema",
                "fields": [
                    {
                        "name": "USER_ID",
                        "type": "string"
                    },
                    {
                        "name": "AGE",
                        "type": "int"
                    },
                    {
                        "name": "GENDER",
                        "type": "string",
                        "categorical": true
                    }
                ],
                "version": "1.0"
            }
            """
        }

        interactions_schema = {
            "name": "InteractionsSchema",
            "schema": """
            {
                "type": "record",
                "name": "Interactions",
                "namespace": "com.amazonaws.personalize.schema",
                "fields": [
                    {
                        "name": "ITEM_ID",
                        "type": "string"
                    },
                    {
                        "name": "USER_ID",
                        "type": "string"
                    },
                    {
                        "name": "EVENT_TYPE",
                        "type": "string"
                    },
                    {
                        "name": "TIMESTAMP",
                        "type": "long"
                    },
                    {
                        "name": "DISCOUNT",
                        "type": "string",
                        "categorical": true
                    }
                ],
                "version": "1.0"
            }
            """
        }

        # Create a trigger that will run the Lambda function automatically after deployment
        personalize_setup_trigger = triggers.TriggerFunction(
            self, "PersonalizeSetupTrigger",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_lambda_code()),
            environment={
                "DATA_BUCKET": data_bucket.bucket_name,
                "PERSONALIZE_ROLE_ARN": personalize_role.role_arn,
                "ITEMS_SCHEMA": items_schema["schema"],
                "USERS_SCHEMA": users_schema["schema"],
                "INTERACTIONS_SCHEMA": interactions_schema["schema"]
            },
            timeout=Duration.minutes(15),
            execute_on_handler_change=True,  # Run on every deployment
            execute_after=[data_bucket]  # Make sure bucket exists first
        )

        # Grant Lambda permissions to create Personalize resources
        personalize_setup_trigger.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "personalize:CreateSchema",
                    "personalize:CreateDatasetGroup",
                    "personalize:CreateDataset",
                    "personalize:CreateDatasetImportJob",
                    "personalize:DescribeDatasetImportJob",
                    "personalize:DescribeDatasetGroup",
                    "personalize:DescribeSchema",
                    "personalize:DescribeDataset",
                    "iam:PassRole"
                ],
                resources=["*"]
            )
        )

        # Grant Lambda permissions to read from S3
        data_bucket.grant_read(personalize_setup_trigger)

        # Output the bucket name and role ARN
        CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        CfnOutput(self, "PersonalizeRoleArn", value=personalize_role.role_arn)

    # TODO: Separate this function to a folder like /lambda
    def _get_lambda_code(self):
        return """
import cfnresponse
import boto3
import json
import os
import time
import uuid

def handler(event, context):
    print(f"Received event: {json.dumps(event)}")  # Add this to debug
    
    try:
        personalize = boto3.client('personalize')

        # Get environment variables
        data_bucket = os.environ['DATA_BUCKET']
        personalize_role_arn = os.environ['PERSONALIZE_ROLE_ARN']
        items_schema_json = os.environ['ITEMS_SCHEMA']
        users_schema_json = os.environ['USERS_SCHEMA']
        interactions_schema_json = os.environ['INTERACTIONS_SCHEMA']

        # Create dataset group
        dataset_group_name = f"personalize-dataset-group-{str(uuid.uuid4())[:8]}"
        dataset_group_response = personalize.create_dataset_group(
            name=dataset_group_name,
            domain="ECOMMERCE"
        )
        dataset_group_arn = dataset_group_response['datasetGroupArn']

        print(f"Dataset Group ARN: {dataset_group_arn}")

        # Wait for dataset group to be active
        wait_for_dataset_group(personalize, dataset_group_arn)

        # Create schemas
        items_schema_response = personalize.create_schema(
            name=f"items-schema-{str(uuid.uuid4())[:8]}",
            schema=items_schema_json,
            domain="ECOMMERCE"
        )
        items_schema_arn = items_schema_response['schemaArn']

        users_schema_response = personalize.create_schema(
            name=f"users-schema-{str(uuid.uuid4())[:8]}",
            schema=users_schema_json,
            domain="ECOMMERCE"
        )
        users_schema_arn = users_schema_response['schemaArn']

        interactions_schema_response = personalize.create_schema(
            name=f"interactions-schema-{str(uuid.uuid4())[:8]}",
            schema=interactions_schema_json,
            domain="ECOMMERCE"
        )
        interactions_schema_arn = interactions_schema_response['schemaArn']

        # Create datasets
        items_dataset_response = personalize.create_dataset(
            name=f"items-dataset-{str(uuid.uuid4())[:8]}",
            schemaArn=items_schema_arn,
            datasetGroupArn=dataset_group_arn,
            datasetType='ITEMS'
        )
        items_dataset_arn = items_dataset_response['datasetArn']

        users_dataset_response = personalize.create_dataset(
            name=f"users-dataset-{str(uuid.uuid4())[:8]}",
            schemaArn=users_schema_arn,
            datasetGroupArn=dataset_group_arn,
            datasetType='USERS'
        )
        users_dataset_arn = users_dataset_response['datasetArn']

        interactions_dataset_response = personalize.create_dataset(
            name=f"interactions-dataset-{str(uuid.uuid4())[:8]}",
            schemaArn=interactions_schema_arn,
            datasetGroupArn=dataset_group_arn,
            datasetType='INTERACTIONS'
        )
        interactions_dataset_arn = interactions_dataset_response['datasetArn']

        # Create dataset import jobs
        wait_for_dataset(personalize, items_dataset_response['datasetArn'])
        create_import_job(
            personalize, 
            items_dataset_arn, 
            f"s3://{data_bucket}/items.csv", 
            personalize_role_arn,
            "items-import"
        )
        
        wait_for_dataset(personalize, users_dataset_response['datasetArn'])
        create_import_job(
            personalize, 
            users_dataset_arn, 
            f"s3://{data_bucket}/users.csv", 
            personalize_role_arn,
            "users-import"
        )
        
        wait_for_dataset(personalize, interactions_dataset_response['datasetArn'])
        create_import_job(
            personalize, 
            interactions_dataset_arn, 
            f"s3://{data_bucket}/interactions.csv", 
            personalize_role_arn,
            "interactions-import"
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'DatasetGroupArn': dataset_group_arn,
                'ItemsSchemaArn': items_schema_arn,
                'UsersSchemaArn': users_schema_arn,
                'InteractionsSchemaArn': interactions_schema_arn,
                'ItemsDatasetArn': items_dataset_arn,
                'UsersDatasetArn': users_dataset_arn,
                'InteractionsDatasetArn': interactions_dataset_arn
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        raise e

def wait_for_dataset_group(personalize, dataset_group_arn):
    max_attempts = 60
    for i in range(max_attempts):
        response = personalize.describe_dataset_group(
            datasetGroupArn=dataset_group_arn
        )
        status = response['datasetGroup']['status']
        if status == 'ACTIVE':
            return
        if status == 'CREATE FAILED':
            raise Exception(f"Dataset group creation failed: {response}")
        time.sleep(10)
    raise Exception("Dataset group creation timed out")
    
def wait_for_dataset(personalize, dataset_arn):
    max_attempts = 60
    for i in range(max_attempts):
        response = personalize.describe_dataset(
            datasetArn=dataset_arn
        )
        status = response['dataset']['status']
        if status == 'ACTIVE':
            print(f"Dataset {dataset_arn} is now ACTIVE")
            return
        if status == 'CREATE FAILED':
            raise Exception(f"Dataset creation failed: {response}")
        print(f"Dataset {dataset_arn} status: {status}. Waiting...")
        time.sleep(10)
    raise Exception(f"Dataset creation timed out for {dataset_arn}")

def create_import_job(personalize, dataset_arn, data_location, role_arn, job_name_prefix):
    import_job_response = personalize.create_dataset_import_job(
        jobName=f"{job_name_prefix}-{str(uuid.uuid4())[:8]}",
        datasetArn=dataset_arn,
        dataSource={
            'dataLocation': data_location
        },
        roleArn=role_arn
    )
    import_job_arn = import_job_response['datasetImportJobArn']
    print(f"Created import job: {import_job_arn}")
    return import_job_arn
"""
