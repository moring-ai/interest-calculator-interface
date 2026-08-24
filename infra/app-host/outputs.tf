output "app_url" {
  description = "Where the app will be served, once DNS points at public_ip."
  value       = "https://${var.app_hostname}"
}

output "public_ip" {
  description = "Create an A record for app_hostname pointing here. Caddy cannot get a certificate until it resolves."
  value       = aws_eip.this.public_ip
}

output "dns_record_required" {
  description = "The DNS record you must create by hand (moring.ai is not in Route53 in this account)."
  value       = "${var.app_hostname}.  A  ${aws_eip.this.public_ip}"
}

output "google_oauth_redirect_uri" {
  description = "Paste this into the Google Cloud Console OAuth client as an Authorized redirect URI."
  value       = "https://${var.app_hostname}/oauth2/callback"
}

output "google_oauth_javascript_origin" {
  description = "Authorized JavaScript origin for the same OAuth client."
  value       = "https://${var.app_hostname}"
}

output "ecr_web_repository_url" {
  value = aws_ecr_repository.web.repository_url
}

output "ecr_backend_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "instance_id" {
  description = "For shell access: aws ssm start-session --target <id>"
  value       = aws_instance.this.id
}

output "google_client_id_parameter" {
  value = aws_ssm_parameter.google_client_id.name
}

output "google_client_secret_parameter" {
  value = aws_ssm_parameter.google_client_secret.name
}
