variable "aws_region" {
  default = "us-east-1"
}

variable "instance_type" {
  default     = "t3.medium"
  description = "t3.medium = 2 vCPU 4GB RAM, required for Whisper STT"
}

variable "private_key_path" {
  default     = "~/.ssh/labsuser.pem"
  description = "Local path to the EC2 private key"
}
