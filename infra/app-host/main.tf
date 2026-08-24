terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "interest-calculator"
      Component = "app-host"
      ManagedBy = "terraform"
    }
  }
}

# --------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------
# This account has no default VPC, so the stack brings its own. One public
# subnet: a single instance that must be reachable from the internet, with no
# private workloads to isolate from.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = var.name }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 0)
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name}-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "${var.name}-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "this" {
  name        = "${var.name}-sg"
  description = "Public HTTP/HTTPS. Access control is Google SSO at the proxy, not the security group."
  vpc_id      = aws_vpc.this.id

  # 80 is required for the ACME HTTP-01 challenge, and redirects to 443.
  ingress {
    description = "HTTP (ACME challenge and redirect)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # No port 22: shell access is via SSM Session Manager.

  egress {
    description = "All outbound (ECR, Bedrock, the MCP host, Google, ACME)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = var.name }
}

# --------------------------------------------------------------------------
# Container registries
# --------------------------------------------------------------------------

resource "aws_ecr_repository" "web" {
  name                 = "${var.name}-web"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "backend" {
  name                 = "${var.name}-backend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "web" {
  repository = aws_ecr_repository.web.name
  policy     = local.keep_ten_images
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy     = local.keep_ten_images
}

locals {
  keep_ten_images = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 10 most recent images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# --------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------

# oauth2-proxy signs its session cookie with this. Generated here so it is
# never invented by hand, and rotating it simply logs everyone out.
resource "random_password" "cookie_secret" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "cookie_secret" {
  name        = "/${var.name}/oauth2-cookie-secret"
  description = "oauth2-proxy cookie signing secret"
  type        = "SecureString"
  value       = random_password.cookie_secret.result
}

resource "random_password" "litellm_key" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "litellm_key" {
  name        = "/${var.name}/litellm-master-key"
  description = "Virtual key the API presents to the LiteLLM gateway"
  type        = "SecureString"
  value       = var.litellm_master_key != "" ? var.litellm_master_key : "sk-${random_password.litellm_key.result}"
}

# The Google OAuth client cannot be created from here -- it lives in Google
# Cloud Console under your account. These are created empty and filled in by
# scripts/set-google-oauth.sh, so the secret never passes through Terraform
# state or a committed file.
resource "aws_ssm_parameter" "google_client_id" {
  name        = "/${var.name}/google-client-id"
  description = "Google OAuth client ID (set with scripts/set-google-oauth.sh)"
  type        = "String"
  value       = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "google_client_secret" {
  name        = "/${var.name}/google-client-secret"
  description = "Google OAuth client secret (set with scripts/set-google-oauth.sh)"
  type        = "SecureString"
  value       = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [value]
  }
}

# --------------------------------------------------------------------------
# Instance identity
# --------------------------------------------------------------------------

resource "aws_iam_role" "instance" {
  name = "${var.name}-instance"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "instance" {
  name = "${var.name}-instance"
  role = aws_iam_role.instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PullImages"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = [aws_ecr_repository.web.arn, aws_ecr_repository.backend.arn]
      },
      {
        # This is what replaces mounting AWS keys into the gateway: LiteLLM
        # picks the instance role up from IMDS, so no credential exists on the
        # box to leak or rotate.
        Sid      = "InvokeTheAgent"
        Effect   = "Allow"
        Action   = ["bedrock-agentcore:InvokeAgentRuntime"]
        Resource = [var.agent_runtime_arn, "${var.agent_runtime_arn}/*"]
      },
      {
        Sid    = "ReadOwnSecrets"
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = [
          aws_ssm_parameter.cookie_secret.arn,
          aws_ssm_parameter.litellm_key.arn,
          aws_ssm_parameter.google_client_id.arn,
          aws_ssm_parameter.google_client_secret.arn,
          # Owned by the agent repo's stack; read-only from here.
          "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.mcp_token_parameter}",
        ]
      },
      {
        Effect    = "Allow"
        Action    = ["kms:Decrypt"]
        Resource  = "*"
        Condition = { StringEquals = { "kms:ViaService" = "ssm.${var.region}.amazonaws.com" } }
      },
    ]
  })
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.name}-instance"
  role = aws_iam_role.instance.name
}

# --------------------------------------------------------------------------
# The instance
# --------------------------------------------------------------------------

data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_eip" "this" {
  domain = "vpc"
  tags   = { Name = var.name }
}

resource "aws_instance" "this" {
  ami                    = data.aws_ssm_parameter.al2023_arm64.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.this.id]
  iam_instance_profile   = aws_iam_instance_profile.this.name

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens   = "required" # IMDSv2 only
    http_endpoint = "enabled"
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    region               = var.region
    name                 = var.name
    app_hostname         = var.app_hostname
    acme_email           = var.acme_email
    allowed_email_domain = var.allowed_email_domain
    web_image            = "${aws_ecr_repository.web.repository_url}:latest"
    backend_image        = "${aws_ecr_repository.backend.repository_url}:latest"
    registry             = split("/", aws_ecr_repository.web.repository_url)[0]
    agent_runtime_arn    = var.agent_runtime_arn
    mcp_server_url       = var.mcp_server_url
    mcp_token_param      = var.mcp_token_parameter
    cookie_secret_param  = aws_ssm_parameter.cookie_secret.name
    litellm_key_param    = aws_ssm_parameter.litellm_key.name
    google_id_param      = aws_ssm_parameter.google_client_id.name
    google_secret_param  = aws_ssm_parameter.google_client_secret.name
  })

  user_data_replace_on_change = true

  tags = { Name = var.name }
}

resource "aws_eip_association" "this" {
  instance_id   = aws_instance.this.id
  allocation_id = aws_eip.this.id
}
