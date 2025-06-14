from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct

class DynamoDBUserTableStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for CSV data
        csv_bucket = s3.Bucket(
            self, "CSVBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # Upload CSV to S3 bucket
        s3_upload = s3deploy.BucketDeployment(
            self, "DeployCSV",
            sources=[s3deploy.Source.asset("./data/dynamodb/trimmed")],
            destination_bucket=csv_bucket
        )

        # Create DynamoDB table
        user_table = dynamodb.Table(
            self, "UsersTable",
            table_name="UsersTable",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            import_source=dynamodb.ImportSourceSpecification(
                bucket=csv_bucket,
                input_format=dynamodb.InputFormat.csv(),
                key_prefix="raw_users.csv"
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create items table
        items_table = dynamodb.Table(
            self, "ItemsTable",
            table_name="ItemsTable",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            import_source=dynamodb.ImportSourceSpecification(
                bucket=csv_bucket,
                input_format=dynamodb.InputFormat.csv(),
                key_prefix="raw_items.csv"
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        orders_table = dynamodb.Table(
            self, "OrdersTable",
            table_name="OrdersTable",
            partition_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            import_source=dynamodb.ImportSourceSpecification(
                bucket=csv_bucket,
                input_format=dynamodb.InputFormat.csv(),
                key_prefix="orders.csv"
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create reviews table
        reviews_table = dynamodb.Table(
            self, "ReviewsTable",
            table_name="ReviewsTable",
            partition_key=dynamodb.Attribute(name="product_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            import_source=dynamodb.ImportSourceSpecification(
                bucket=csv_bucket,
                input_format=dynamodb.InputFormat.csv(),
                key_prefix="reviews.csv"
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        orders_table.add_global_secondary_index(
            index_name="UserStatusIndex",
            partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.NUMBER),
            sort_key=dynamodb.Attribute(name="delivery_status", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL
        )

        user_table.node.add_dependency(s3_upload)
        items_table.node.add_dependency(s3_upload)
        orders_table.node.add_dependency(s3_upload)
        reviews_table.node.add_dependency(s3_upload)

        self.user_table_name = user_table.table_name
        self.items_table_name = items_table.table_name
        self.orders_table_name = orders_table.table_name
        self.reviews_table_name = reviews_table.table_name

        # Outputs
        CfnOutput(self, "UsersTableName", value=user_table.table_name)
        CfnOutput(self, "ItemsTableName", value=items_table.table_name)
        CfnOutput(self, "OrdersTableName", value=orders_table.table_name)
        CfnOutput(self, "ReviewsTableName", value=reviews_table.table_name)
        CfnOutput(self, "BucketName", value=csv_bucket.bucket_name)
