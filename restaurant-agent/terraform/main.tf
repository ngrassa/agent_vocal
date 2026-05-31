terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── Elastic IP (created first so provisioner knows the IP) ─────────
resource "aws_eip" "agent" {
  domain = "vpc"
  tags   = { Name = "restaurant-agent-eip" }
}

# ── Security Group ─────────────────────────────────────────────────
resource "aws_security_group" "agent" {
  name        = "restaurant-agent-sg"
  description = "Restaurant AI Agent"

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  # HTTP dashboard
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  # SIP signaling
  ingress {
    from_port   = 5060
    to_port     = 5060
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 5060
    to_port     = 5060
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  # RTP media streams
  ingress {
    from_port   = 10000
    to_port     = 10100
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "restaurant-agent-sg" }
}

# ── Ubuntu 22.04 AMI (latest) ───────────────────────────────────────
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── EC2 Instance ────────────────────────────────────────────────────
resource "aws_instance" "agent" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = "vockey"
  vpc_security_group_ids = [aws_security_group.agent.id]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = <<-EOF
    #!/bin/bash
    set -e
    apt-get update -y
    apt-get install -y docker.io docker-compose-v2 curl git
    systemctl enable docker
    systemctl start docker
    usermod -aG docker ubuntu
    mkdir -p /home/ubuntu/restaurant-agent/data
    chown -R ubuntu:ubuntu /home/ubuntu/restaurant-agent
  EOF

  tags = { Name = "restaurant-agent" }
}

# ── Associate Elastic IP ────────────────────────────────────────────
resource "aws_eip_association" "agent" {
  instance_id   = aws_instance.agent.id
  allocation_id = aws_eip.agent.id
}

# ── Deploy project via SSH ──────────────────────────────────────────
resource "null_resource" "deploy" {
  depends_on = [aws_eip_association.agent]

  triggers = {
    always = timestamp()
  }

  # 1. Archiver le projet localement
  provisioner "local-exec" {
    command = <<-EOT
      cd ${path.module}/.. && \
      tar czf /tmp/restaurant-agent.tar.gz \
        --exclude='.terraform' \
        --exclude='terraform' \
        --exclude='data' \
        --exclude='.git' \
        --exclude='__pycache__' \
        .
    EOT
  }

  connection {
    type        = "ssh"
    user        = "ubuntu"
    private_key = file(var.private_key_path)
    host        = aws_eip.agent.public_ip
    timeout     = "8m"
  }

  # 2. Attendre que l'instance soit prête + créer le répertoire
  provisioner "remote-exec" {
    inline = [
      "cloud-init status --wait || true",
      "mkdir -p /home/ubuntu/restaurant-agent/data"
    ]
  }

  # 3. Uploader l'archive (un seul fichier, pas de pb scp)
  provisioner "file" {
    source      = "/tmp/restaurant-agent.tar.gz"
    destination = "/home/ubuntu/restaurant-agent.tar.gz"
  }

  # 4. Extraire et déployer
  provisioner "remote-exec" {
    inline = [
      "cd /home/ubuntu",
      "tar xzf restaurant-agent.tar.gz -C restaurant-agent/",
      "rm -f restaurant-agent.tar.gz",
      "cd restaurant-agent",
      "chmod +x scripts/install_server.sh",
      "bash scripts/install_server.sh 2>&1 | tee /home/ubuntu/deploy.log"
    ]
  }
}
