---
title: "Enterprise Hybrid Cloud Lab: Cisco IOS-XE to AWS Transit Gateway BGP over IPsec VPN"
date: "2026-11-11"
draft: false
tags: ["AWS", "CCNA", "BGP", "Networking", "Terraform"]
categories: ["Cloud & Networking"]
---

# Executive Architecture Overview

This lab demonstrates a **fully‑functional hybrid‑cloud BGP peering** between a Cisco IOS‑XE edge router (simulated on Cisco CSR1000v) and an **AWS Transit Gateway (TGW)** using **IPsec site‑to‑site VPN**.  The design mirrors a typical enterprise scenario where:

- The on‑premises network runs **IBGP** across its core and **EBGP** to the cloud.
- The AWS side uses **Transit Gateway** to centralise VPC connectivity and to provide a single BGP endpoint for all remote sites.
- **Dynamic routing** (BGP) is exchanged over the encrypted tunnel, enabling automatic route propagation and fail‑over.
- **Terraform** provisions the entire AWS environment (TGW, VPCs, VPN, route tables) while the Cisco router is configured manually (or via Ansible/YAML for automation).

The lab is completely self‑contained and can be executed in a **local dev environment** (Cisco CSR1000v VM + AWS free tier) or in a **CI/CD pipeline**.

---

## 1. Mermaid.js Topology Diagram

```mermaid
flowchart LR
    subgraph OnPrem[On‑Premises Network]
        direction TB
        R1[CSR1000v Router]
        LAN1[10.10.0.0/16 LAN]
        R1 -- "IPsec Tunnel (IKEv2)" --> TGW[AWS Transit Gateway]
        R1 -- "BGP over IPsec" --> TGW
        LAN1 --> R1
    end

    subgraph AWS[Amazon Web Services]
        direction TB
        TGW -- "Attachment" --> VPC1[VPC A (10.0.0.0/16)]
        TGW -- "Attachment" --> VPC2[VPC B (10.1.0.0/16)]
        VPC1 -- "Subnet" --> EC2A[EC2 Instance A]
        VPC2 -- "Subnet" --> EC2B[EC2 Instance B]
    end

    classDef aws fill:#FF9900,color:#fff,stroke:#333,stroke-width:2px;
    classDef onprem fill:#0074D9,color:#fff,stroke:#333,stroke-width:2px;
    class TGW,VPC1,VPC2,EC2A,EC2B aws;
    class R1,LAN1 onprem;
```

---

## 2. IP Addressing & BGP ASN Table

| Device / Interface | IP Address (Subnet)          | Role                     | BGP ASN |
|--------------------|------------------------------|--------------------------|---------|
| **CSR1000v**       |                              |                          | **65001** |
| &nbsp;&nbsp;Gig0/0 | 192.168.100.2/30 (192.168.100.0/30) | Tunnel to AWS TGW (IPsec) | |
| &nbsp;&nbsp;Gig0/1 | 10.10.1.1/24 (LAN)            | Internal LAN             | |
| **AWS TGW**        | 192.168.100.1/30 (same)      | Tunnel endpoint (VPN)    | **64512** |
| **VPC A**          | 10.0.0.0/16                  | Application subnet       | |
| **VPC B**          | 10.1.0.0/16                  | Application subnet       | |
| **EC2 A**          | 10.0.1.10/24                 | Sample workload          | |
| **EC2 B**          | 10.1.1.10/24                 | Sample workload          | |

*Note:* The /30 tunnel subnet is a best‑practice for point‑to‑point IPsec links. Adjust CIDR blocks to avoid overlap with existing networks.

---

## 3. Cisco IOS‑XE Router Configuration (CLI)

> **Copy‑paste the entire block into the router console.**  Inline comments (`!`) explain each command.

```text
! ------------------------------------------------------------
! 1. Basic device configuration
! ------------------------------------------------------------
hostname CSR1000v
!
! Enable secret (hashed) – replace with your own secure value
enable secret 9 $9$K8gk...$...
!
! Configure a local username for SSH/HTTPS access
username admin privilege 15 secret 9 $9$VfK...
!
! ------------------------------------------------------------
! 2. Interface configuration
! ------------------------------------------------------------
!
! GigabitEthernet0/0 – tunnel interface (will be used for IPsec)
interface GigabitEthernet0/0
 ip address 192.168.100.2 255.255.255.252
 no shutdown
!
! GigabitEthernet0/1 – LAN side
interface GigabitEthernet0/1
 ip address 10.10.1.1 255.255.255.0
 no shutdown
!
! ------------------------------------------------------------
! 3. IKEv2 & IPsec configuration (using pre‑shared key for simplicity)
! ------------------------------------------------------------
!
crypto ikev2 proposal IKE_PROPOSAL
 encryption aes-cbc-256
 integrity sha256
 group 14
!
crypto ikev2 policy IKE_POLICY
 proposal IKE_PROPOSAL
!
crypto ikev2 keyring KEYRING
 peer AWS_TGW
  address 192.168.100.1
  pre-shared-key cisco123!
!
crypto ikev2 profile IKEV2_PROFILE
 match identity remote address 192.168.100.1 255.255.255.255
 authentication local pre-share
 authentication remote pre-share
 keyring local KEYRING
!
! IPsec transform set (AES‑256/SHA‑256)
crypto ipsec transform-set ESP_AES256_SHA256 esp-aes 256 esp-sha256-hmac
!
crypto ipsec profile IPSEC_PROFILE
 set transform-set ESP_AES256_SHA256
 set ikev2-profile IKEV2_PROFILE
!
! Apply IPsec to the tunnel interface
interface Tunnel0
 ip address 192.168.100.2 255.255.255.252
 tunnel source GigabitEthernet0/0
 tunnel destination 192.168.100.1
 tunnel mode ipsec ipv4
 tunnel protection ipsec profile IPSEC_PROFILE
!
! ------------------------------------------------------------
! 4. BGP configuration (EBGP to AWS TGW)
! ------------------------------------------------------------
router bgp 65001
 bgp log-neighbor-changes
 neighbor 192.168.100.1 remote-as 64512
 neighbor 192.168.100.1 description AWS-Transit-Gateway
 ! Advertise the on‑prem LAN
 network 10.10.0.0 mask 255.255.0.0
 ! Optional: set BGP timers for faster convergence in lab
 timers bgp 10 30
!
! ------------------------------------------------------------
! 5. Optional: Route‑map to filter/redistribute routes (if needed)
! ------------------------------------------------------------
!
! Example: only advertise LAN, block default
route-map LAN_ONLY permit 10
 match ip address prefix-list LAN_ONLY
!
ip prefix-list LAN_ONLY seq 5 permit 10.10.0.0/16 le 32
!
router bgp 65001
 neighbor 192.168.100.1 route-map LAN_ONLY out
!
! ------------------------------------------------------------
! 6. Enable SSH & HTTPS for management
! ------------------------------------------------------------
ip domain-name lab.example.com
crypto key generate rsa general-keys modulus 2048
ip ssh version 2
line vty 0 4
 transport input ssh
 login local
!
! ------------------------------------------------------------
! 7. Save configuration
! ------------------------------------------------------------
end
write memory
```

---

## 4. AWS Transit Gateway & Site‑to‑Site VPN Terraform Code

> **Copy the entire block into a `main.tf` file** (or split into modules).  Run `terraform init && terraform apply`.

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# ------------------------------------------------------------
# 1. VPCs (two example VPCs attached to the TGW)
# ------------------------------------------------------------
resource "aws_vpc" "vpc_a" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "VPC-A"
  }
}

resource "aws_vpc" "vpc_b" {
  cidr_block = "10.1.0.0/16"
  tags = {
    Name = "VPC-B"
  }
}

# ------------------------------------------------------------
# 2. Transit Gateway
# ------------------------------------------------------------
resource "aws_ec2_transit_gateway" "tgw" {
  description = "Enterprise TGW for BGP over IPsec lab"
  amazon_side_asn = 64512
  auto_accept_shared_attachments = "enable"
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  tags = {
    Name = "Enterprise-TGW"
  }
}

# ------------------------------------------------------------
# 3. TGW Attachments (VPCs)
# ------------------------------------------------------------
resource "aws_ec2_transit_gateway_vpc_attachment" "tgw_attach_a" {
  transit_gateway_id = aws_ec2_transit_gateway.tgw.id
  vpc_id             = aws_vpc.vpc_a.id
  subnet_ids         = [aws_subnet.vpc_a_subnet.id]
  tags = {
    Name = "TGW-Attach-VPC-A"
  }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "tgw_attach_b" {
  transit_gateway_id = aws_ec2_transit_gateway.tgw.id
  vpc_id             = aws_vpc.vpc_b.id
  subnet_ids         = [aws_subnet.vpc_b_subnet.id]
  tags = {
    Name = "TGW-Attach-VPC-B"
  }
}

# ------------------------------------------------------------
# 4. Subnets for VPCs (used for TGW attachment & EC2 demo)
# ------------------------------------------------------------
resource "aws_subnet" "vpc_a_subnet" {
  vpc_id            = aws_vpc.vpc_a.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
  tags = { Name = "VPC-A-Subnet" }
}

resource "aws_subnet" "vpc_b_subnet" {
  vpc_id            = aws_vpc.vpc_b.id
  cidr_block        = "10.1.1.0/24"
  availability_zone = "us-east-1b"
  tags = { Name = "VPC-B-Subnet" }
}

# ------------------------------------------------------------
# 5. EC2 instances (optional – for connectivity testing)
# ------------------------------------------------------------
resource "aws_instance" "ec2_a" {
  ami           = "ami-0c02fb55956c7d316" # Amazon Linux 2 (us-east-1)
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.vpc_a_subnet.id
  associate_public_ip_address = true
  tags = { Name = "EC2-A" }
}

resource "aws_instance" "ec2_b" {
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.vpc_b_subnet.id
  associate_public_ip_address = true
  tags = { Name = "EC2-B" }
}

# ------------------------------------------------------------
# 6. Site‑to‑Site VPN (Customer Gateway + VPN Connection)
# ------------------------------------------------------------
# Customer Gateway – represents the on‑prem Cisco router
resource "aws_customer_gateway" "cgw" {
  bgp_asn    = 65001
  ip_address = "192.168.100.2"   # Public IP of the CSR1000v (use NAT/Elastic IP if needed)
  type       = "ipsec.1"
  tags = { Name = "OnPrem-CGW" }
}

# VPN Connection – attaches the CGW to the TGW
resource "aws_ec2_transit_gateway_vpn_attachment" "vpn_att" {
  transit_gateway_id = aws_ec2_transit_gateway.tgw.id
  customer_gateway_id = aws_customer_gateway.cgw.id
  vpn_connection_options {
    static_routes_only = false   # Enable BGP dynamic routing
  }
  tags = { Name = "TGW-VPN-Attachment" }
}

# ------------------------------------------------------------
# 7. Route propagation – ensure TGW propagates routes to VPCs
# ------------------------------------------------------------
resource "aws_ec2_transit_gateway_route_table_association" "assoc_a" {
  transit_gateway_attachment_id = aws_ec2_transit_gateway_vpc_attachment.tgw_attach_a.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway.tgw.association_default_route_table_id
}

resource "aws_ec2_transit_gateway_route_table_association" "assoc_b" {
  transit_gateway_attachment_id = aws_ec2_transit_gateway_vpc_attachment.tgw_attach_b.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway.tgw.association_default_route_table_id
}

# Propagate VPN routes to the TGW route table (default)
resource "aws_ec2_transit_gateway_route_table_propagation" "prop_vpn" {
  transit_gateway_route_table_id = aws_ec2_transit_gateway.tgw.propagation_default_route_table_id
  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpn_attachment.vpn_att.id
}

# ------------------------------------------------------------
# 8. Output values for quick reference
# ------------------------------------------------------------
output "tgw_id" {
  value = aws_ec2_transit_gateway.tgw.id
}

output "vpn_connection_id" {
  value = aws_ec2_transit_gateway_vpn_attachment.vpn_att.id
}

output "customer_gateway_id" {
  value = aws_customer_gateway.cgw.id
}
```

**Important notes**:
- Replace `ip_address` in `aws_customer_gateway` with the **public IP** of your CSR1000v (or an Elastic IP that forwards to the router).  In a pure lab you can use a **NAT instance** or **AWS VPN CloudHub** for testing.
- The TGW VPN attachment automatically creates an **AWS side VPN endpoint** with its own public IPs; those are visible after `terraform apply`.
- BGP ASN on the TGW is set to **64512** (matching the Cisco config).

---

## 5. Verification & Troubleshooting Commands

### 5.1. Cisco Router Checks

```text
! Verify tunnel interface status
show interfaces Tunnel0

! Verify IPsec SA details
show crypto ipsec sa

! Verify IKEv2 status
show crypto ikev2 sa

! BGP neighbor state
show bgp neighbors 192.168.100.1
show bgp summary

! Verify routes learned via BGP
show ip route bgp

! Debug (use with caution in production)
debug crypto ikev2 protocol
debug crypto ipsec
```

### 5.2. AWS Side Checks (CLI)

```bash
# List VPN connections and their status
aws ec2 describe-transit-gateway-vpn-attachments \
    --transit-gateway-id <tgw-id>

# Show BGP status for the VPN attachment
aws ec2 describe-transit-gateway-attachments \
    --attachment-ids <vpn-attachment-id>

# Verify propagated routes in the TGW route table
aws ec2 get-transit-gateway-route-table \
    --transit-gateway-route-table-id <rtb-id>

# Pull BGP peer status (requires CloudWatch metrics – optional)
aws cloudwatch get-metric-statistics \
    --namespace AWS/TransitGateway \
    --metric-name BGPState \
    --dimensions Name=TransitGatewayAttachmentId,Value=<vpn-attachment-id> \
    --statistics Average --period 60 --start-time $(date -u -d '-5 minutes' +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ)
```

### 5.3. End‑to‑End Connectivity Tests

```bash
# From the CSR1000v (ping a host in VPC‑A)
ping 10.0.1.10 source 10.10.1.1

# From an EC2 instance, ping the on‑prem LAN
ping 10.10.1.1 -c 4

# Traceroute to verify path through TGW
traceroute 10.10.1.1
```

### 5.4. Common Issues & Fixes

| Symptom | Likely Cause | Remedy |
|---------|--------------|--------|
| Tunnel interface down (`Tunnel0` shows `down`) | IKE SA not established (mismatched PSK, IKE version) | Verify `crypto ikev2 keyring` PSK, ensure both sides use IKEv2, check NAT traversal (`crypto isakmp nat-traversal`) |
| BGP neighbor stays in `Idle` or `Active` | No BGP session because IPsec SA not up or ASN mismatch | Confirm `show crypto ipsec sa` shows `UP`; verify `neighbor remote-as` matches TGW ASN (64512) |
| No routes advertised to AWS | Route‑map/filter blocks prefixes | Review `route-map` and `prefix-list` on the router; ensure `network` statements match your LAN CIDR |
| AWS side shows `DOWN` for VPN attachment | Customer gateway unreachable (wrong public IP, security group) | Ensure SG allows UDP 500/4500 and ESP (protocol 50) inbound; verify CGW IP is reachable from the internet |
| High latency / packet loss | MTU mismatch on tunnel (default 1500 vs. 1400) | Set `mtu 1400` on tunnel interface or enable `fragmentation` on both ends |

---

## 6. Clean‑Up

```bash
# Destroy all AWS resources created by Terraform
terraform destroy -auto-approve

# On the Cisco router, remove the configuration (optional)
configure terminal
 no interface Tunnel0
 no crypto ikev2 profile IKEV2_PROFILE
 no crypto ipsec profile IPSEC_PROFILE
 no router bgp 65001
 end
 write memory
```

---

### Congratulations!
You have successfully built a **dynamic BGP‑enabled site‑to‑site VPN** between a Cisco IOS‑XE edge router and an AWS Transit Gateway using **Terraform** for the cloud side and **native IOS‑XE CLI** for the on‑prem side.  This foundation can be extended to multiple remote sites, redundant VPN tunnels, or Direct Connect integrations.

---
