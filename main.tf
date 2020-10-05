terraform {
  backend "s3" {
    bucket = "xcontest-cashier"
    key    = "infra.tfstate"
    region = "eu-central-1"
  }
}

provider "aws" {
  region  = "eu-central-1"
  version = "~> 2.69"
}

locals {
  deployment = (terraform.workspace == "default") ? "xcontest-cashier" : "${terraform.workspace}-xcontest-cashier"
}


# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "cashier" {
  function_name    = local.deployment
  filename         = "dist/lambda-deployment-package.zip"
  source_code_hash = filebase64sha256("dist/lambda-deployment-package.zip")
  role             = aws_iam_role.lambda.arn
  handler          = "cashier.main.lambda_entrypoint"
  runtime          = "python3.8"
  timeout          = 300
}

# IAM for Lambda

resource "aws_iam_role" "lambda" {
  name               = "${local.deployment}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust_policy.json
}
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
data "aws_iam_policy_document" "lambda_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}
