from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_bedrock as bedrock,
    CfnOutput
)
from constructs import Construct

class SupervisorAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
                 customer_agent: Stack, recommend_agent: Stack, search_agent: Stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create IAM role for Bedrock Supervisor Agent
        agent_role = iam.Role(
            self, "BedrockSupervisorAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            role_name = 'AmazonBedrockExecutionRoleForAgents_SupervisorAgentStack',
            inline_policies = {
                'BedrockAndLambdaAccess': iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=['bedrock:*'],
                            resources=['*']
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=['lambda:InvokeFunction'],
                            resources=[f'arn:aws:lambda:{self.region}:{self.account}:function:*']
                        )
                    ]
                )
            }
        )

        # Grant permissions to invoke other agents
        agent_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeAgent",
                "bedrock:InvokeAgentAlias"
            ],
            resources=["*"]
        ))

        # Create Bedrock Supervisor Agent
        supervisor_agent = bedrock.CfnAgent(
            self, "SupervisorAgent",
            agent_name="SupervisorAgent",
            agent_resource_role_arn=agent_role.role_arn,
            instruction="""You are a supervisor agent that delegates tasks to specialized agents based on the user's request.
            
            You have access to the following specialist agents:
            1. CustomerAgent: Handles customer information and order management. Use this agent for queries about customer details, addresses, orders, and making purchases.
            2. RecommendAgent: Provides product recommendations using personalization systems. Use this agent for personalized product suggestions, best sellers, and most viewed items.
            3. SearchAgent: Searches for products in the catalog. Use this agent for specific product searches and semantic product queries.
            
            Analyze each user request carefully and delegate to the most appropriate agent. For complex requests, you may need to coordinate between multiple agents to provide a comprehensive response.""",
            foundation_model="anthropic.claude-3-haiku-20240307-v1:0",
            # Enable multi-agent collaboration
            agent_collaboration="SUPERVISOR",
            agent_collaborators=[
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                        alias_arn=customer_agent.agent_alias.attr_agent_alias_arn
                    ),
                    collaboration_instruction="""This agent focuses on customer data and order management.
                    Use this agent for queries about customer details, addresses, orders, and making purchases.
                    For complex queries, coordinate with the RecommendAgent and SearchAgent to provide comprehensive responses.""",
                    collaborator_name=customer_agent.agent.agent_name
                ),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                        alias_arn=recommend_agent.agent_alias.attr_agent_alias_arn
                    ),
                    collaboration_instruction="""This agent focuses on product recommendations.
                    Use this agent for personalized product suggestions, best sellers, and most viewed items.
                    For complex queries, coordinate with the CustomerAgent and SearchAgent to provide comprehensive responses.""",
                    collaborator_name=recommend_agent.agent.agent_name
                ),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                        alias_arn=search_agent.agent_alias.attr_agent_alias_arn
                    ),
                    collaboration_instruction="""This agent focuses on product searches and semantic product queries.
                    Use this agent for specific product searches and semantic product queries.
                    For complex queries, coordinate with the CustomerAgent and RecommendAgent to provide comprehensive responses.""",
                    collaborator_name=search_agent.agent.agent_name
                )
            ]
        )
        
        # Create agent alias for the supervisor agent
        supervisor_agent_alias = bedrock.CfnAgentAlias(
            self, "SupervisorAgentAlias",
            agent_id=supervisor_agent.attr_agent_id,
            agent_alias_name="SupervisorAgentAlias"
        )
        
        # Output the supervisor agent alias ARN for reference
        CfnOutput(
            self, "SupervisorAgentAliasARN",
            value=supervisor_agent_alias.attr_agent_alias_arn,
            description="The ARN of the supervisor agent alias"
        )
