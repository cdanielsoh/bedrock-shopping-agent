from aws_cdk import (
    Stack,
    aws_personalize as personalize,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as lambda_,
    aws_iam as iam,
    Duration,
    CfnOutput,
    triggers
)
from constructs import Construct


class PersonalizeTrainingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, dataset_group_arn: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create solutions for User Personalization and Personalized Ranking
        user_personalization_solution = personalize.CfnSolution(
            self, "UserPersonalizationSolution",
            dataset_group_arn=dataset_group_arn,
            name="user-personalization-solution2",
            recipe_arn="arn:aws:personalize:::recipe/aws-user-personalization-v2"
        )

        personalized_ranking_solution = personalize.CfnSolution(
            self, "PersonalizedRankingSolution",
            dataset_group_arn=dataset_group_arn,
            name="personalized-ranking-solution2",
            recipe_arn="arn:aws:personalize:::recipe/aws-personalized-ranking-v2"
        )

        # Lambda functions for checking status and creating campaigns
        check_solution_version_lambda = lambda_.Function(
            self, "CheckSolutionVersionLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import boto3

def find_solution_version_arn(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'SolutionVersionArn':
                return value
            result = find_solution_version_arn(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_solution_version_arn(item)
            if result:
                return result
    return None


def handler(event, context):
    personalize = boto3.client('personalize')
    solution_version_arn = find_solution_version_arn(event)

    try:
        response = personalize.describe_solution_version(
            solutionVersionArn=solution_version_arn
        )

        status = response['solutionVersion']['status']

        return {
            'solutionVersionArn': solution_version_arn,
            'status': status,
            'isDone': status == 'ACTIVE',
            'isFailed': status == 'CREATE FAILED'
        }
    except Exception as e:
        return {
            'solutionVersionArn': solution_version_arn,
            'status': 'ERROR',
            'isDone': False,
            'isFailed': True,
            'errorMessage': str(e)
        }
"""),
            timeout=Duration.seconds(30)
        )

        check_solution_version_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["personalize:DescribeSolutionVersion"],
            resources=["*"]
        ))

        create_campaign_lambda = lambda_.Function(
            self, "CreateCampaignLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import boto3

def find_solution_version_arn(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'SolutionVersionArn':
                return value
            result = find_solution_version_arn(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_solution_version_arn(item)
            if result:
                return result
    return None

def handler(event, context):
    personalize = boto3.client('personalize')
    solution_version_arn = find_solution_version_arn(event)
    campaign_name = event['campaignName']

    try:
        response = personalize.create_campaign(
            name=campaign_name,
            solutionVersionArn=solution_version_arn,
            minProvisionedTPS=1
        )

        return {
            'campaignArn': response['campaignArn'],
            'status': 'CREATING'
        }
    except Exception as e:
        return {
            'error': str(e),
            'status': 'ERROR'
        }
"""),
            timeout=Duration.seconds(30)
        )

        create_campaign_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["personalize:CreateCampaign"],
            resources=["*"]
        ))

        # Lambda functions for creating and checking recommenders
        create_best_sellers_lambda = lambda_.Function(
            self, "CreateBestSellersLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import boto3
import os

def handler(event, context):
    personalize = boto3.client('personalize')
    dataset_group_arn = os.environ["DATASET_GROUP_ARN"]

    try:
        response = personalize.create_recommender(
            name="best-sellers-recommender",
            datasetGroupArn=dataset_group_arn,
            recipeArn="arn:aws:personalize:::recipe/aws-ecomm-popular-items-by-purchases"
        )
        return {'recommenderArn': response['recommenderArn']}
    except Exception as e:
        return {'error': str(e)}
"""),
            timeout=Duration.minutes(5),
            environment={
                "DATASET_GROUP_ARN": dataset_group_arn
            }
        )

        create_best_sellers_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["personalize:CreateRecommender"],
            resources=["*"]
        ))

        create_most_viewed_lambda = lambda_.Function(
            self, "CreateMostViewedLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import boto3
import os

def handler(event, context):
    personalize = boto3.client('personalize')
    dataset_group_arn = os.environ["DATASET_GROUP_ARN"]

    try:
        response = personalize.create_recommender(
            name="most-viewed-recommender",
            datasetGroupArn=dataset_group_arn,
            recipeArn="arn:aws:personalize:::recipe/aws-ecomm-popular-items-by-views"
        )
        return {'recommenderArn': response['recommenderArn']}
    except Exception as e:
        return {'error': str(e)}
"""),
            timeout=Duration.minutes(5),
            environment={
                "DATASET_GROUP_ARN": dataset_group_arn
            }
        )

        create_most_viewed_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["personalize:CreateRecommender"],
            resources=["*"]
        ))

        check_recommender_lambda = lambda_.Function(
            self, "CheckRecommenderLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import boto3


def find_recommender_arn(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'recommenderArn':
                return value
            result = find_recommender_arn(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_recommender_arn(item)
            if result:
                return result
    return None


def handler(event, context):
    personalize = boto3.client('personalize')
    recommender_arn = event['recommenderArn']

    try:
        response = personalize.describe_recommender(
            recommenderArn=recommender_arn
        )

        status = response['recommender']['status']

        return {
            'recommenderArn': recommender_arn,
            'status': status,
            'isDone': status == 'ACTIVE',
            'isFailed': status == 'CREATE FAILED'
        }
    except Exception as e:
        return {
            'recommenderArn': recommender_arn,
            'status': 'ERROR',
            'isDone': False,
            'isFailed': True,
            'errorMessage': str(e)
        }
"""),
            timeout=Duration.seconds(30)
        )

        check_recommender_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["personalize:DescribeRecommender"],
            resources=["*"]
        ))

        # Failure and success states
        job_failed_user = sfn.Fail(
            self, "UserPersonalizationFailed",
            cause="User Personalization Failed",
            error="UserPersonalizationError"
        )

        job_failed_ranking = sfn.Fail(
            self, "PersonalizedRankingFailed",
            cause="Personalized Ranking Failed",
            error="PersonalizedRankingError"
        )

        job_failed_bestsellers = sfn.Fail(
            self, "BestSellersFailed",
            cause="Best Sellers Recommender Failed",
            error="BestSellersError"
        )

        job_failed_mostviewed = sfn.Fail(
            self, "MostViewedFailed",
            cause="Most Viewed Recommender Failed",
            error="MostViewedError"
        )

        job_succeeded = sfn.Succeed(
            self, "TrainingSucceeded"
        )

        # User Personalization Workflow
        create_user_personalization_version = tasks.CallAwsService(
            self, "CreateUserPersonalizationVersion",
            service="personalize",
            action="createSolutionVersion",
            parameters={
                "SolutionArn": user_personalization_solution.attr_solution_arn
            },
            iam_resources=["*"],
            result_path="$.userPersonalization.solutionVersionDetails"
        )

        check_user_personalization_version = tasks.LambdaInvoke(
            self, "CheckUserPersonalizationVersion",
            lambda_function=check_solution_version_lambda,
            payload=sfn.TaskInput.from_object({
                "SolutionVersionArn": sfn.JsonPath.string_at(
                    "$.userPersonalization.solutionVersionDetails.SolutionVersionArn")
            }),
            result_path="$.userPersonalization.checkStatus"
        )

        wait_user_personalization = sfn.Wait(
            self, "WaitUserPersonalization",
            time=sfn.WaitTime.duration(Duration.seconds(60))
        )

        create_user_personalization_campaign = tasks.LambdaInvoke(
            self, "CreateUserPersonalizationCampaign",
            lambda_function=create_campaign_lambda,
            payload=sfn.TaskInput.from_object({
                "SolutionVersionArn": sfn.JsonPath.string_at(
                    "$.userPersonalization.solutionVersionDetails.SolutionVersionArn"),
                "CampaignName": "user-personalization-campaign"
            }),
            result_path="$.userPersonalization.campaign"
        )

        user_personalization_workflow = sfn.Chain.start(create_user_personalization_version).next(
            check_user_personalization_version.next(
                sfn.Choice(self, "UserPersonalizationDone")
                .when(sfn.Condition.boolean_equals("$.userPersonalization.checkStatus.Payload.isDone", True),
                      create_user_personalization_campaign)
                .when(sfn.Condition.boolean_equals("$.userPersonalization.checkStatus.Payload.isFailed", True),
                      job_failed_user)
                .otherwise(wait_user_personalization.next(check_user_personalization_version))
            )
        )

        # Personalized Ranking Workflow
        create_personalized_ranking_version = tasks.CallAwsService(
            self, "CreatePersonalizedRankingVersion",
            service="personalize",
            action="createSolutionVersion",
            parameters={
                "SolutionArn": personalized_ranking_solution.attr_solution_arn
            },
            iam_resources=["*"],
            result_path="$.personalizedRanking.solutionVersionDetails"
        )

        check_personalized_ranking_version = tasks.LambdaInvoke(
            self, "CheckPersonalizedRankingVersion",
            lambda_function=check_solution_version_lambda,
            payload=sfn.TaskInput.from_object({
                "SolutionVersionArn": sfn.JsonPath.string_at(
                    "$.personalizedRanking.solutionVersionDetails.SolutionVersionArn")
            }),
            result_path="$.personalizedRanking.checkStatus"
        )

        wait_personalized_ranking = sfn.Wait(
            self, "WaitPersonalizedRanking",
            time=sfn.WaitTime.duration(Duration.seconds(60))
        )

        create_personalized_ranking_campaign = tasks.LambdaInvoke(
            self, "CreatePersonalizedRankingCampaign",
            lambda_function=create_campaign_lambda,
            payload=sfn.TaskInput.from_object({
                "SolutionVersionArn": sfn.JsonPath.string_at(
                    "$.personalizedRanking.solutionVersionDetails.SolutionVersionArn"),
                "CampaignName": "personalized-ranking-campaign"
            }),
            result_path="$.personalizedRanking.campaign"
        )

        personalized_ranking_workflow = sfn.Chain.start(create_personalized_ranking_version).next(
            check_personalized_ranking_version.next(
                sfn.Choice(self, "PersonalizedRankingDone")
                .when(sfn.Condition.boolean_equals("$.personalizedRanking.checkStatus.Payload.isDone", True),
                      create_personalized_ranking_campaign)
                .when(sfn.Condition.boolean_equals("$.personalizedRanking.checkStatus.Payload.isFailed", True),
                      job_failed_ranking)
                .otherwise(wait_personalized_ranking.next(check_personalized_ranking_version))
            )
        )

        # Best Sellers Recommender Workflow
        create_best_sellers = tasks.LambdaInvoke(
            self, "CreateBestSellers",
            lambda_function=create_best_sellers_lambda,
            payload=sfn.TaskInput.from_object({
                "DatasetGroupArn": dataset_group_arn
            }),
            result_path="$.bestSellers.recommenderDetails"
        )

        check_best_sellers = tasks.LambdaInvoke(
            self, "CheckBestSellers",
            lambda_function=check_recommender_lambda,
            payload=sfn.TaskInput.from_object({
                "RecommenderArn": sfn.JsonPath.string_at("$.bestSellers.recommenderDetails.Payload.recommenderArn")
            }),
            result_path="$.bestSellers.checkStatus"
        )

        wait_best_sellers = sfn.Wait(
            self, "WaitBestSellers",
            time=sfn.WaitTime.duration(Duration.seconds(60))
        )

        best_sellers_workflow = sfn.Chain.start(create_best_sellers).next(
            check_best_sellers.next(
                sfn.Choice(self, "BestSellersDone")
                .when(sfn.Condition.boolean_equals("$.bestSellers.checkStatus.Payload.isDone", True),
                      sfn.Pass(self, "BestSellersSucceeded"))
                .when(sfn.Condition.boolean_equals("$.bestSellers.checkStatus.Payload.isFailed", True),
                      job_failed_bestsellers)
                .otherwise(wait_best_sellers.next(check_best_sellers))
            )
        )

        # Most Viewed Recommender Workflow
        create_most_viewed = tasks.LambdaInvoke(
            self, "CreateMostViewed",
            lambda_function=create_most_viewed_lambda,
            payload=sfn.TaskInput.from_object({
                "DatasetGroupArn": dataset_group_arn
            }),
            result_path="$.mostViewed.recommenderDetails"
        )

        check_most_viewed = tasks.LambdaInvoke(
            self, "CheckMostViewed",
            lambda_function=check_recommender_lambda,
            payload=sfn.TaskInput.from_object({
                "RecommenderArn": sfn.JsonPath.string_at("$.mostViewed.recommenderDetails.Payload.recommenderArn")
            }),
            result_path="$.mostViewed.checkStatus"
        )

        wait_most_viewed = sfn.Wait(
            self, "WaitMostViewed",
            time=sfn.WaitTime.duration(Duration.seconds(60))
        )

        most_viewed_workflow = sfn.Chain.start(create_most_viewed).next(
            check_most_viewed.next(
                sfn.Choice(self, "MostViewedDone")
                .when(sfn.Condition.boolean_equals("$.mostViewed.checkStatus.Payload.isDone", True),
                      sfn.Pass(self, "MostViewedSucceeded"))
                .when(sfn.Condition.boolean_equals("$.mostViewed.checkStatus.Payload.isFailed", True),
                      job_failed_mostviewed)
                .otherwise(wait_most_viewed.next(check_most_viewed))
            )
        )

        # Create parallel execution
        parallel_training = sfn.Parallel(
            self, "ParallelTraining",
            result_path="$.parallelResults"
        )
        parallel_training.branch(user_personalization_workflow)
        parallel_training.branch(personalized_ranking_workflow)
        parallel_training.branch(best_sellers_workflow)
        parallel_training.branch(most_viewed_workflow)

        # Complete workflow
        complete_workflow = parallel_training.next(job_succeeded)

        # Create the state machine
        state_machine = sfn.StateMachine(
            self, "PersonalizeTrainingStateMachine",
            definition=complete_workflow,
            timeout=Duration.hours(24)
        )

        # Create a trigger to start the Step Functions execution
        triggers.TriggerFunction(
            self, "StartPersonalizeTraining",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import boto3
import os

def handler(event, context):
    client = boto3.client('stepfunctions')
    client.start_execution(
        stateMachineArn=os.environ['STATE_MACHINE_ARN']
    )
    return {'statusCode': 200, 'body': 'Step Functions execution started'}
"""),
            environment={
                "STATE_MACHINE_ARN": state_machine.state_machine_arn
            },
            execute_on_handler_change=True
        ).add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[state_machine.state_machine_arn]
            )
        )

        # Output
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "UserPersonalizationSolutionArn", value=user_personalization_solution.attr_solution_arn)
        CfnOutput(self, "PersonalizedRankingSolutionArn", value=personalized_ranking_solution.attr_solution_arn)
