output "vpc_id" {
  value = aws_vpc.this.id
}

output "public_subnet_ids" {
  value = [for subnet in aws_subnet.public : subnet.id]
}

output "private_subnet_ids" {
  value = [for subnet in aws_subnet.private : subnet.id]
}

output "database_subnet_ids" {
  value = [for subnet in aws_subnet.database : subnet.id]
}

output "security_group_ids" {
  value = {
    alb        = aws_security_group.alb.id
    web        = aws_security_group.web.id
    api        = aws_security_group.api.id
    worker     = aws_security_group.worker.id
    migration  = aws_security_group.migration.id
    database   = aws_security_group.database.id
    endpoints  = aws_security_group.vpc_endpoints.id
  }
}
