---
title: 'Foundations of Enterprise Networking: OSI Model, TCP/IP & Wireshark Packet Analysis Lab'
date: '2026-11-11'
draft: false
tags: ['Hardware & Networking', 'Beginner', 'Hands-On Lab']
categories: ['Hardware & Networking']
---

# Lab Objective & Prerequisites

**Objective**:  
- Demonstrate how data traverses the OSI 7‑layer model and the TCP/IP 4‑layer model using real packet captures.  
- Correlate each encapsulation step (Ethernet, IP, TCP/UDP, Application) with the corresponding OSI layer.  
- Build a minimal enterprise‑grade topology in a virtual lab, generate traffic, capture with Wireshark, and analyze the packet headers.

**Prerequisites** (all free / open‑source):
- GNS3 **or** EVE‑NG (latest stable release) – for virtual network devices.
- Cisco IOSvL2 or IOSv image (free for learning) **or** open‑source VyOS/FRR routers.
- A Linux host VM (Ubuntu 22.04) – will act as a client/server and run `tcpdump`/`Wireshark`.
- VirtualBox or VMware Workstation Player – to host the VMs if not using a cloud sandbox.
- Optional: Free tier account on AWS/Azure/GCP to spin up a cloud‑based VM for cross‑cloud traffic.
- Wireshark 4.x installed on the host OS (Windows/macOS/Linux).

# Enterprise Architecture Topology

```mermaid
flowchart TB
    subgraph GNS3_EVE_NG[Virtual Lab]
        direction LR
        Client[Client VM (Ubuntu)] -->|Ethernet| Switch1[Layer‑2 Switch]
        Server[Server VM (Ubuntu)] -->|Ethernet| Switch1
        Router[Router (IOSvL2)] -->|Trunk| Switch1
        Cloud[Cloud VM (AWS Free Tier)] -->|IPsec Tunnel| Router
    end
    style GNS3_EVE_NG fill:#f9f9f9,stroke:#333,stroke-width:2px
    classDef vm fill:#e3f2fd,stroke:#1565c0,stroke-width:1px;
    class Client,Server,Cloud vm;
```

*The topology mimics a classic enterprise edge: a client and a server on the same LAN, a router providing WAN connectivity, and an optional cloud VM to illustrate cross‑internet traffic.*

# Addressing & Resource Inventory Table

| Device | Role | Management IP (IPv4) | Data IP (IPv4) | Interface(s) | OS/Platform |
|--------|------|----------------------|----------------|--------------|-------------|
| Client VM | End‑host (Application) | 192.168.10.10/24 (mgmt) | 192.168.10.10/24 (data) | eth0 (connected to Switch1) | Ubuntu 22.04 LTS |
| Server VM | End‑host (Application) | 192.168.10.20/24 (mgmt) | 192.168.10.20/24 (data) | eth0 (connected to Switch1) | Ubuntu 22.04 LTS |
| Switch1 | Layer‑2 distribution | 192.168.10.2/24 (SVI) | N/A | Gi0/1‑Gi0/2 (access), Gi0/24 (trunk) | Cisco IOSvL2 |
| Router | Edge router (IP routing) | 192.168.10.1/24 (LAN) | 10.0.0.1/30 (WAN) | Gi0/0 (LAN), Gi0/1 (WAN) | Cisco IOSv (or VyOS) |
| Cloud VM | Remote host (Internet) | 3.93.123.45/32 (public) | 10.0.0.2/30 (WAN) | eth0 (attached to router via IPsec) | Ubuntu 22.04 (AWS Free Tier) |

# Step‑By‑Step Configuration

## 1️⃣ Deploy the Virtual Devices

- **GNS3/EVE‑NG**: Create a new project, drag‑and‑drop the following appliances:
  - `Ubuntu Server` (x2) → rename to **Client** and **Server**.
  - `Cisco IOSvL2` → rename to **Switch1**.
  - `Cisco IOSv` (or VyOS) → rename to **Router**.
  - (Optional) `AWS EC2` instance – add as a **Cloud VM** using the *Cloud* node type.
- Connect interfaces as shown in the Mermaid diagram.
- Set each node to **Start on boot**.

## 2️⃣ Basic Device OS Configuration

### 2.1 Ubuntu Client & Server (copy‑paste to each VM)

```bash
#!/bin/bash
# Configure static IPv4 on eth0
cat <<EOF | sudo tee /etc/netplan/01-static.yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses: [${HOST_IP}/24]
      gateway4: 192.168.10.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
EOF
sudo netplan apply

# Install required tools
sudo apt-get update && sudo apt-get install -y tcpdump wireshark iperf3

# Enable non‑root capture for the user (replace $USER)
sudo dpkg-reconfigure wireshark
# Choose "Yes" to allow non‑superusers to capture packets

# Verify connectivity
ping -c 3 192.168.10.1
```

> **Replace `${HOST_IP}`** with `192.168.10.10` on the client and `192.168.10.20` on the server.

### 2.2 Cisco Switch1 (IOSvL2)

```cisco
! Basic switch configuration – copy‑paste into the console
enable
configure terminal
!
! Management VLAN (10) and SVI
interface vlan 10
 ip address 192.168.10.2 255.255.255.0
 no shutdown
!
! Access ports for client & server
interface range GigabitEthernet0/1-2
 switchport mode access
 switchport access vlan 10
 spanning-tree portfast
!
! Trunk port toward router
interface GigabitEthernet0/24
 switchport trunk encapsulation dot1q
 switchport mode trunk
 switchport trunk allowed vlan 10
 no shutdown
!
! Enable CDP for visibility (optional)
cdp run
!
end
write memory
```

### 2.3 Cisco Router (IOSv) – Core IP Routing

```cisco
! Router configuration – copy‑paste into the console
enable
configure terminal
!
! LAN interface (connected to Switch1)
interface GigabitEthernet0/0
 ip address 192.168.10.1 255.255.255.0
 no shutdown
!
! WAN interface (connected to Cloud VM or simulated ISP)
interface GigabitEthernet0/1
 ip address 10.0.0.1 255.255.255.252
 no shutdown
!
! Static route to the cloud network
ip route 0.0.0.0 0.0.0.0 10.0.0.2
!
! (Optional) Simple IPsec tunnel to Cloud VM – using pre‑shared key
crypto isakmp policy 10
 encr aes
 hash sha256
 authentication pre-share
 group 14
 lifetime 86400
!
crypto isakmp key MySecretKey address 10.0.0.2
!
crypto ipsec transform-set ESP-AES256-SHA esp-aes 256 esp-sha-hmac
!
crypto map VPN 10 ipsec-isakmp
 set peer 10.0.0.2
 set transform-set ESP-AES256-SHA
 match address 100
!
interface GigabitEthernet0/1
 crypto map VPN
!
access-list 100 permit ip 192.168.10.0 0.0.0.255 10.0.0.2 0.0.0.0
!
end
write memory
```

### 2.4 Cloud VM (AWS EC2 – free tier) – Minimal Setup

```bash
#!/bin/bash
# Run on first boot (User Data) or via SSH
sudo apt-get update && sudo apt-get install -y tcpdump iperf3
# Assign the secondary private IP (10.0.0.2) – AWS does this automatically if you create a second ENI.
# Verify routing back to 192.168.10.0/24 via the VPN tunnel.
```

## 3️⃣ Generate Traffic & Capture with Wireshark

1. **Start Wireshark** on the **Client VM** (or on the host OS if you prefer to capture on the virtual NIC).  
   - Select interface `eth0` (or the GNS3/EVE‑NG host‑only adapter).
   - Apply capture filter: `host 192.168.10.20` to focus on traffic to the server.
2. **Generate TCP traffic** from client to server:

```bash
# On Client VM
time iperf3 -c 192.168.10.20 -t 30 -i 5
```

3. **Generate UDP traffic** (to illustrate different transport layer):

```bash
iperf3 -c 192.168.10.20 -u -b 5M -t 20 -i 5
```

4. **Capture a single packet** with `tcpdump` for later offline analysis:

```bash
sudo tcpdump -i eth0 -c 1 -w /tmp/first_packet.pcap host 192.168.10.20
```

5. **Stop the capture** in Wireshark after ~30 seconds.  Save the `.pcap` file for the analysis section.

# Verification & Troubleshooting Commands

| Goal | Command | Expected Result |
|------|---------|-----------------|
| Verify Layer‑2 connectivity | `show mac address-table` (Switch) | Client & Server MACs appear in VLAN 10.
| Verify VLAN membership | `show vlan brief` (Switch) | VLAN 10 active, ports Gi0/1‑2 in access mode.
| Verify trunk negotiation | `show interfaces trunk` (Switch) | Gi0/24 shows encapsulation dot1q, allowed VLAN 10.
| Verify IP routing | `show ip route` (Router) | Default route points to 10.0.0.2; LAN network 192.168.10.0/24 present.
| Test end‑to‑end ping | `ping 192.168.10.20` (Client) | Replies with < 1 ms latency.
| Test cross‑cloud ping | `ping 3.93.123.45` (Client) | Replies via IPsec tunnel (if configured).
| Verify IPsec SA | `show crypto ipsec sa` (Router) | Active SA with peer 10.0.0.2.
| Capture verification | `tcpdump -r /tmp/first_packet.pcap -vv` | Shows Ethernet → IP → TCP headers.
| Wireshark layer view | Open `.pcap` → expand **Frame → Ethernet → Internet Protocol → Transmission Control Protocol** | Each layer maps to OSI 1‑4 respectively.
| Troubleshoot no traffic | `show interface status` (Switch) / `show ip interface brief` (Router) | Interfaces up, correct IPs.
| Verify NTP (optional) | `show ntp status` (Router) | NTP synchronized – good for timestamp accuracy.

# Security Hardening & Production Best Practices

1. **Management Plane Isolation**
   - Place out‑of‑band management VLAN (e.g., VLAN 99) on the switch; assign only the SVI `192.168.99.1/24`.
   - Use SSH (v2) only; disable Telnet.
2. **Control Plane Policing (CoPP)**
   - Rate‑limit ICMP, SSH, and BGP (if used) on the router to mitigate DoS.
3. **IPsec Hardening**
   - Use AES‑256 encryption and SHA‑256 integrity.
   - Rotate pre‑shared keys every 90 days; consider certificate‑based IKEv2 for production.
4. **Logging & Monitoring**
   - Enable syslog to a centralized server (`logging 192.168.10.250`).
   - Configure SNMPv3 with authentication and privacy.
5. **Patch Management**
   - Keep IOS images up‑to‑date (`show version` → compare with Cisco security advisories).
   - Apply Ubuntu security updates (`sudo apt-get upgrade -y`).
6. **Least‑Privilege Access**
   - Create role‑based admin accounts on Cisco devices (`username netadmin privilege 15 secret <strong‑pwd>`).
   - Use `sudo` with limited NOPASSWD for `tcpdump` on Linux hosts.
7. **Network Segmentation**
   - In a real enterprise, move the client and server to separate VLANs and enforce inter‑VLAN routing ACLs.
   - Example ACL to allow only HTTP/HTTPS from client to server:

```cisco
ip access-list extended CLIENT‑TO‑SERVER
 permit tcp host 192.168.10.10 host 192.168.10.20 eq 80
 permit tcp host 192.168.10.10 host 192.168.10.20 eq 443
 deny ip any any
!
interface GigabitEthernet0/0
 ip access-group CLIENT‑TO‑SERVER in
```

8. **Capture Hygiene**
   - Rotate capture files (`-C 100` in `tcpdump` to limit size).
   - Store PCAPs on a read‑only forensic share; restrict access via ACLs.
9. **Documentation & Change Control**
   - Keep this lab notebook version‑controlled (Git) and tag each iteration.
   - Use configuration management tools (Ansible, Terraform) for reproducibility.

---

*By completing this lab, students will have a concrete, hands‑on understanding of how a data unit is encapsulated at each OSI/TCP‑IP layer, how to visualize those layers with Wireshark, and how to apply production‑grade security controls to a seemingly simple network.*