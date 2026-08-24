variable "region" {
  description = "AWS region. Should match the region the AgentCore runtime lives in."
  type        = string
  default     = "us-east-2"
}

variable "name" {
  description = "Name prefix for every resource."
  type        = string
  default     = "interest-app"
}

variable "instance_type" {
  description = "Graviton instance. Four containers (Caddy, oauth2-proxy, API, LiteLLM) fit comfortably in t4g.small."
  type        = string
  default     = "t4g.small"
}

variable "vpc_cidr" {
  type    = string
  default = "10.30.0.0/16"
}

variable "app_hostname" {
  description = <<-EOT
    Public hostname for the app. You must create an A record for this pointing
    at the Elastic IP this stack allocates -- moring.ai is not hosted in this
    account, so Terraform cannot do it. Caddy cannot obtain a certificate until
    that record resolves.
  EOT
  type        = string
  default     = "interest.moring.ai"
}

variable "acme_email" {
  description = "Contact address Let's Encrypt uses for certificate expiry notices."
  type        = string
  default     = "ops@moring.ai"
}

variable "allowed_email_domain" {
  description = "Google Workspace domain permitted to sign in. This is what keeps the app's Bedrock spend to your own organisation."
  type        = string
  default     = "moring.ai"
}

variable "agent_runtime_arn" {
  description = "AgentCore runtime the LiteLLM gateway invokes."
  type        = string
  default     = "arn:aws:bedrock-agentcore:us-east-2:754039697525:runtime/InterestCalculatorAgent_InterestCalculatorAgent-sXxjxMB9xT"
}

variable "mcp_server_url" {
  description = "MCP tool endpoint, from the agent repo: terraform output -raw mcp_url"
  type        = string
  default     = "https://3-140-24-37.sslip.io/mcp"
}

variable "mcp_token_parameter" {
  description = "SSM parameter holding the MCP bearer token. Owned by the agent repo's stack; this one only reads it."
  type        = string
  default     = "/interest-mcp/mcp-token"
}

variable "litellm_master_key" {
  description = "Virtual key the API presents to the LiteLLM gateway. Internal to the compose network, never exposed."
  type        = string
  sensitive   = true
  default     = ""
}
