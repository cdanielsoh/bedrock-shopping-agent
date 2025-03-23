from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    RemovalPolicy,
    CfnOutput,
    aws_personalize as personalize
)
from constructs import Construct

class PersonalizeDataImportStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for storing datasets
        data_bucket = s3.Bucket(
            self, "PersonalizeDataBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # Upload data to S3 bucket
        data_upload = s3deploy.BucketDeployment(
            self, "UploadPersonalizeData",
            sources=[s3deploy.Source.asset("./data/personalize/")],
            destination_bucket=data_bucket,
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

        data_bucket.grant_read(personalize_role)

        # Create dataset group using CfnDatasetGroup
        dataset_group = personalize.CfnDatasetGroup(
            self, "PersonalizeDatasetGroup",
            name=f"personalize-dataset-group-{self.stack_name}",
            domain="ECOMMERCE"
        )

        # Create schemas using CfnSchema
        items_schema = personalize.CfnSchema(
            self, "ItemsSchema",
            name=f"items-schema-{self.stack_name}",
            domain="ECOMMERCE",
            schema="""
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
        )

        users_schema = personalize.CfnSchema(
            self, "UsersSchema",
            name=f"users-schema-{self.stack_name}",
            domain="ECOMMERCE",
            schema="""
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
        )

        interactions_schema = personalize.CfnSchema(
            self, "InteractionsSchema",
            name=f"interactions-schema-{self.stack_name}",
            domain="ECOMMERCE",
            schema="""
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
        )

        # Create datasets with import jobs
        items_dataset = personalize.CfnDataset(
            self, "ItemsDataset",
            dataset_group_arn=dataset_group.attr_dataset_group_arn,
            dataset_type="Items",
            name=f"items-dataset-{self.stack_name}",
            schema_arn=items_schema.attr_schema_arn,
            dataset_import_job=personalize.CfnDataset.DatasetImportJobProperty(
                job_name=f"items-import-job-{self.stack_name}",
                data_source={
                    "DataLocation": f"s3://{data_bucket.bucket_name}/items.csv"
                },
                role_arn=personalize_role.role_arn
            )
        )

        users_dataset = personalize.CfnDataset(
            self, "UsersDataset",
            dataset_group_arn=dataset_group.attr_dataset_group_arn,
            dataset_type="Users",
            name=f"users-dataset-{self.stack_name}",
            schema_arn=users_schema.attr_schema_arn,
            dataset_import_job=personalize.CfnDataset.DatasetImportJobProperty(
                job_name=f"users-import-job-{self.stack_name}",
                data_source={
                    "DataLocation": f"s3://{data_bucket.bucket_name}/users.csv"
                },
                role_arn=personalize_role.role_arn
            )
        )

        interactions_dataset = personalize.CfnDataset(
            self, "InteractionsDataset",
            dataset_group_arn=dataset_group.attr_dataset_group_arn,
            dataset_type="Interactions",
            name=f"interactions-dataset-{self.stack_name}",
            schema_arn=interactions_schema.attr_schema_arn,
            dataset_import_job=personalize.CfnDataset.DatasetImportJobProperty(
                job_name=f"interactions-import-job-{self.stack_name}",
                data_source={
                    "DataLocation": f"s3://{data_bucket.bucket_name}/interactions.csv"
                },
                role_arn=personalize_role.role_arn
            )
        )

        # Add dependencies to ensure proper creation order
        items_dataset.node.add_dependency(data_upload)
        items_dataset.add_dependency(items_schema)
        items_dataset.add_dependency(dataset_group)
        users_dataset.node.add_dependency(data_upload)
        users_dataset.add_dependency(users_schema)
        users_dataset.add_dependency(dataset_group)
        interactions_dataset.node.add_dependency(data_upload)
        interactions_dataset.add_dependency(interactions_schema)
        interactions_dataset.add_dependency(dataset_group)

        self.dataset_group_arn = dataset_group.attr_dataset_group_arn

        # Output relevant ARNs and names
        CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        CfnOutput(self, "PersonalizeRoleArn", value=personalize_role.role_arn)
        CfnOutput(self, "DatasetGroupArn", value=dataset_group.attr_dataset_group_arn)
        CfnOutput(self, "ItemsSchemaArn", value=items_schema.attr_schema_arn)
        CfnOutput(self, "UsersSchemaArn", value=users_schema.attr_schema_arn)
        CfnOutput(self, "InteractionsSchemaArn", value=interactions_schema.attr_schema_arn)
