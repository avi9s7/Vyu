data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 3)

  public_subnet_cidrs   = [for index, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, index)]
  private_subnet_cidrs  = [for index, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, index + 16)]
  database_subnet_cidrs = [for index, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, index + 32)]

  nat_gateways = var.single_nat_gateway ? { (local.azs[0]) = local.azs[0] } : { for az in local.azs : az => az }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "vyu-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-igw"
    Environment = var.environment
  }
}

resource "aws_subnet" "public" {
  for_each = { for index, az in local.azs : az => {
    cidr = local.public_subnet_cidrs[index]
    az   = az
  } }

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = true

  tags = {
    Name        = "vyu-${var.environment}-public-${each.key}"
    Environment = var.environment
    Tier        = "public"
  }
}

resource "aws_subnet" "private" {
  for_each = { for index, az in local.azs : az => {
    cidr = local.private_subnet_cidrs[index]
    az   = az
  } }

  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az

  tags = {
    Name        = "vyu-${var.environment}-private-${each.key}"
    Environment = var.environment
    Tier        = "private"
  }
}

resource "aws_subnet" "database" {
  for_each = { for index, az in local.azs : az => {
    cidr = local.database_subnet_cidrs[index]
    az   = az
  } }

  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az

  tags = {
    Name        = "vyu-${var.environment}-database-${each.key}"
    Environment = var.environment
    Tier        = "database"
  }
}

resource "aws_eip" "nat" {
  for_each = local.nat_gateways

  domain = "vpc"

  tags = {
    Name        = "vyu-${var.environment}-nat-eip-${each.key}"
    Environment = var.environment
  }
}

resource "aws_nat_gateway" "this" {
  for_each = local.nat_gateways

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id

  tags = {
    Name        = "vyu-${var.environment}-nat-${each.key}"
    Environment = var.environment
  }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name        = "vyu-${var.environment}-public"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  for_each = aws_subnet.private

  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = var.single_nat_gateway ? aws_nat_gateway.this[local.azs[0]].id : aws_nat_gateway.this[each.key].id
  }

  tags = {
    Name        = "vyu-${var.environment}-private-${each.key}"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}

resource "aws_route_table" "database" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-database"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "database" {
  for_each = aws_subnet.database

  subnet_id      = each.value.id
  route_table_id = aws_route_table.database.id
}
