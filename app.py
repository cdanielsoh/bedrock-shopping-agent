#!/usr/bin/env python3
import os

import aws_cdk as cdk
from stacks.personalize.personalize_stack import PersonalizeDataImportStack
from stacks.opensearch.opensearch_stack import OpenSearchServerlessStack


app = cdk.App()
# PersonalizeDataImportStack(app, "PersonalizeDataImportStack")
OpenSearchServerlessStack(app, "OpenSearchServerlessStack")
app.synth()
