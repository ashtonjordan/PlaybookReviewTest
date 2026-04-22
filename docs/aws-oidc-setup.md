# AWS OIDC Setup for GitHub Actions → Bedrock

This document describes how to set up GitHub OIDC federation so the PR Review Agent
can assume an IAM role and call Amazon Bedrock from a GitHub Actions workflow.

## Prerequisites

- An AWS account with Amazon Bedrock model access enabled for `anthropic.claude-3-haiku-20240307-v1:0` in `us-east-1`
- AWS CLI configured with admin permissions (for one-time setup)

## Architecture

```
GitHub Actions → OIDC Token → AWS STS AssumeRoleWithWebIdentity → Temporary Credentials → Bedrock
```

No long-term secrets are stored. The GitHub-issued OIDC token is exchanged for
short-lived AWS credentials scoped to a single IAM role.

## CloudFormation Template

Deploy this stack once in your AWS account:

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: GitHub OIDC federation for PR Review Agent → Bedrock

Parameters:
  GitHubOrg:
    Type: String
    Default: ashtonjordan
  GitHubRepo:
    Type: String
    Default: PlaybookReviewTest
  BedrockRegion:
    Type: String
    Default: us-east-1

Resources:
  GitHubOIDCProvider:
    Type: AWS::IAM::OIDCProvider
    Properties:
      Url: https://token.actions.githubusercontent.com
      ClientIdList:
        - sts.amazonaws.com
      ThumbprintList:
        - 6938fd4d98bab03faadb97b34396831e3780aea1

  PRReviewAgentRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: pr-review-agent-role
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Federated: !GetAtt GitHubOIDCProvider.Arn
            Action: sts:AssumeRoleWithWebIdentity
            Condition:
              StringEquals:
                token.actions.githubusercontent.com:aud: sts.amazonaws.com
              StringLike:
                token.actions.githubusercontent.com:sub: !Sub "repo:${GitHubOrg}/${GitHubRepo}:*"
      Policies:
        - PolicyName: bedrock-invoke
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - bedrock:InvokeModel
                  - bedrock:ApplyGuardrail
                Resource: "*"
                Condition:
                  StringEquals:
                    aws:RequestedRegion: !Ref BedrockRegion

Outputs:
  RoleArn:
    Value: !GetAtt PRReviewAgentRole.Arn
    Description: ARN to use in the GitHub Actions workflow
```

## Deploy via CLI

```bash
aws cloudformation deploy \
  --template-file docs/aws-oidc-setup.yaml \
  --stack-name pr-review-agent-oidc \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    GitHubOrg=ashtonjordan \
    GitHubRepo=PlaybookReviewTest

# Get the role ARN
aws cloudformation describe-stacks \
  --stack-name pr-review-agent-oidc \
  --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" \
  --output text
```

## Manual Setup (if not using CloudFormation)

### 1. Create the OIDC Provider

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. Create the IAM Role

Create a file `trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:ashtonjordan/PlaybookReviewTest:*"
        }
      }
    }
  ]
}
```

```bash
aws iam create-role \
  --role-name pr-review-agent-role \
  --assume-role-policy-document file://trust-policy.json
```

### 3. Attach Bedrock Permissions

```bash
aws iam put-role-policy \
  --role-name pr-review-agent-role \
  --policy-name bedrock-invoke \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:ApplyGuardrail"],
      "Resource": "*"
    }]
  }'
```

## Workflow Configuration

After deploying, add the role ARN as a repository variable or secret:

- Go to repo Settings → Secrets and variables → Actions
- Add a variable `AWS_ROLE_ARN` with the role ARN from the stack output

The workflow uses `aws-actions/configure-aws-credentials` to assume the role.
