output "elastic_ip" {
  value       = aws_eip.agent.public_ip
  description = "IP publique élastique du serveur"
}

output "dashboard_url" {
  value       = "http://${aws_eip.agent.public_ip}:8000"
  description = "URL du tableau de bord"
}

output "ssh_command" {
  value       = "ssh -i ~/.ssh/labsuser.pem ubuntu@${aws_eip.agent.public_ip}"
  description = "Commande SSH pour accéder au serveur"
}

output "sip_server" {
  value       = aws_eip.agent.public_ip
  description = "Adresse SIP à entrer dans Zoiper (pour tester)"
}
