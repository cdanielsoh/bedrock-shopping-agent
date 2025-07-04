from aws_cdk import (
    Stack,
    aws_opensearchserverless as opensearchserverless,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_lambda as lambda_,
    RemovalPolicy,
    CustomResource,
    CfnOutput,
    Duration,
)
from aws_cdk.custom_resources import Provider
from constructs import Construct
import json


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
            sources=[s3deploy.Source.asset("./data/opensearch/trimmed")],
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

        # opensearchpy layer
        opensearchpy_layer = lambda_.LayerVersion(
            self, "OpensearchpyLayer",
            code=lambda_.Code.from_asset("./layers/opensearchpy"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Layer containing the opensearchpy module"
        )

        # Grant S3 access
        data_bucket.grant_read(lambda_role)

        # Create Lambda function to create index and ingest data
        ingest_lambda = lambda_.Function(
            self, "IngestDataFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_asset("./lambda/ingest_opensearch"),
            environment={
                "COLLECTION_ENDPOINT": f"{collection.attr_collection_endpoint}",
                "DATA_BUCKET": data_bucket.bucket_name,
                "INDEX_NAME": "products",
                "REGION": self.region
            },
            timeout=Duration.minutes(5),
            layers=[opensearchpy_layer],
            role=lambda_role
        )

        # Ensure Lambda waits for access policy to be created
        ingest_lambda.node.add_dependency(data_access_policy)

        # Custom resource to trigger Lambda only once during initial deployment
        custom_resource = CustomResource(
            self, "IngestTrigger",
            service_token=Provider(
                self, "IngestProvider",
                on_event_handler=ingest_lambda
            ).service_token,
            properties={
                "CollectionName": collection_name,  # Static property that won't change
                "IndexName": "products"  # Static property that won't change
            }
        )

        custom_resource.node.add_dependency(collection)
        custom_resource.node.add_dependency(data_access_policy)

        self.opensearch_endpoint = collection.attr_collection_endpoint

        # Output the collection endpoint and bucket name
        CfnOutput(self, "CollectionEndpoint", value=self.opensearch_endpoint)
        CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        CfnOutput(self, "DashboardsURL", value=f"https://{collection.attr_dashboard_endpoint}/_dashboards/")
