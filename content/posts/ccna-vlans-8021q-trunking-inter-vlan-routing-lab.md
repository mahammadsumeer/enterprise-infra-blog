---
title: "CCNA Lab 01: Configuring 802.1Q VLANs, Trunking & Router-on-a-Stick on Cisco IOS"
date: "2026-11-11"
draft: false
tags: ["CCNA", "Beginner", "Hands-On Lab"]
categories: ["CCNA"]
---

# 1. Lab Objective & Prerequisites

**Objective**
- Build a multi‑VLAN LAN using 802.1Q trunking.
- Implement *Router‑on‑a‑Stick* (inter‑VLAN routing) on a Cisco ISR/CSR.
- Verify end‑to‑end connectivity and apply basic security hardening.

**Prerequisites**
- GNS3 **or** EVE‑NG (free community edition) with Cisco IOSv (or IOS‑XRv) images.
- Optional: VirtualBox/VMware for host PCs (e.g., Ubuntu Desktop).
- Basic knowledge of Cisco CLI, VLAN concepts, and IP addressing.
- A workstation with a modern web browser and SSH client (PuTTY, OpenSSH).

# 2. Enterprise Architecture Topology

```mermaid
flowchart TB
    subgraph GNS3
        direction TB
        R1[Router (Router‑on‑a‑Stick)]
        SW1[Layer‑2 Switch]
        PC1[Host PC - VLAN 10]
        PC2[Host PC - VLAN 20]
    end
    R1 -- "Gig0/0 (trunk)" --> SW1
    SW1 -- "Fa0/1 (access)" --> PC1
    SW1 -- "Fa0/2 (access)" --> PC2
    classDef cisco fill:#0c5399,color:#fff,stroke:#333,stroke-width:2px;
    class R1,SW1 cisco;
```

# 3. Addressing & Resource Inventory Table

| Device | Interface | Description | IP Address | Subnet Mask | VLAN |
|--------|-----------|-------------|------------|-------------|------|
| **R1** | Gig0/0    | Trunk to SW1 (router‑on‑a‑stick) | 10.0.0.1 | 255.255.255.0 | N/A (sub‑interfaces) |
| **R1** | Gig0/0.10 | VLAN 10 SVI | 10.0.10.1 | 255.255.255.0 | 10 |
| **R1** | Gig0/0.20 | VLAN 20 SVI | 10.0.20.1 | 255.255.255.0 | 20 |
| **SW1**| Gig0/1    | Trunk to R1 | – | – | Trunk (802.1Q) |
| **SW1**| Fa0/1     | Access port – PC1 | – | – | Access VLAN 10 |
| **SW1**| Fa0/2     | Access port – PC2 | – | – | Access VLAN 20 |
| **PC1**| eth0      | Host in VLAN 10 | 10.0.10.10 | 255.255.255.0 | 10 |
| **PC2**| eth0      | Host in VLAN 20 | 10.0.20.10 | 255.255.255.0 | 20 |

# 4. Step‑by‑Step Configuration

## 4.1. Switch (SW1) – VLANs & Trunk

```text
! ---------------------------------------------------
! Switch configuration (SW1)
! ---------------------------------------------------
conf t
  ! Create VLANs
  vlan 10
    name VLAN10_Users
  exit
  vlan 20
    name VLAN20_Users
  exit

  ! Assign access ports
  interface FastEthernet0/1
    switchport mode access
    switchport access vlan 10
    spanning-tree portfast
  exit

  interface FastEthernet0/2
    switchport mode access
    switchport access vlan 20
    spanning-tree portfast
  exit

  ! Configure trunk to router
  interface GigabitEthernet0/1
    description *** Trunk to R1 ***
    switchport trunk encapsulation dot1q
    switchport mode trunk
    switchport trunk native vlan 99   ! optional native VLAN (unused)
  exit

  ! Optional: enable CDP/LLDP for discovery (can be disabled later)
  cdp run
  lldp run

  ! Save configuration
  end
  write memory
```

## 4.2. Router (R1) – Router‑on‑a‑Stick

```text
! ---------------------------------------------------
! Router configuration (R1)
! ---------------------------------------------------
conf t
  ! Enable routing (default on IOS, but ensure no shutdown)
  no shutdown

  ! Create sub‑interfaces for each VLAN
  interface GigabitEthernet0/0
    no shutdown
    description *** Trunk to SW1 ***
  exit

  interface GigabitEthernet0/0.10
    encapsulation dot1q 10
    ip address 10.0.10.1 255.255.255.0
  exit

  interface GigabitEthernet0/0.20
    encapsulation dot1q 20
    ip address 10.0.20.1 255.255.255.0
  exit

  ! Optional: enable routing protocol (static routes are sufficient for this lab)
  ip route 0.0.0.0 0.0.0.0 Null0   ! placeholder for default route if needed

  ! Enable IPv4 routing (already on IOS, but explicit for clarity)
  ip routing

  ! Secure management access (see Section 6)
  line vty 0 4
    transport input ssh
    login local
  exit

  username admin privilege 15 secret 0 cisco123

  ! Enable SSH (RSA key generation)
  crypto key generate rsa general-keys modulus 2048
  ip domain-name lab.local

  ! Save configuration
  end
  write memory
```

## 4.3. Host PCs – IP Settings

- **PC1 (VLAN 10)**
  - IP: `10.0.10.10`
  - Mask: `255.255.255.0`
  - Default‑gw: `10.0.10.1`
- **PC2 (VLAN 20)**
  - IP: `10.0.20.10`
  - Mask: `255.255.255.0`
  - Default‑gw: `10.0.20.1`

> In GNS5/EVE‑NG you can set these values in the *cloud‑init* or via the host OS network manager.

# 5. Verification & Troubleshooting Commands

## 5.1. Switch Verification

```text
show vlan brief               ! Verify VLANs exist
show interfaces trunk          ! Confirm trunk status and allowed VLANs
show spanning-tree vlan 10    ! Ensure ports are forwarding
show mac address-table         ! Verify MAC learning across trunk
```

## 5.2. Router Verification

```text
show ip interface brief       ! Verify sub‑interfaces are up with IPs
show running-config interface GigabitEthernet0/0.10
show running-config interface GigabitEthernet0/0.20
show ip route                 ! Should have directly connected routes for 10.0.10.0/24 and 10.0.20.0/24
```

## 5.3. End‑to‑End Connectivity Tests

```bash
# From PC1
ping 10.0.10.1          # to router SVI (same VLAN)
ping 10.0.20.10         # to PC2 (inter‑VLAN)

# From PC2
ping 10.0.20.1          # to router SVI (same VLAN)
ping 10.0.10.10         # to PC1 (inter‑VLAN)
```

If ping fails:
1. Verify trunk is up (`show interfaces status` on SW1).
2. Confirm sub‑interface encapsulation matches VLAN IDs.
3. Check that the hosts' default gateways point to the correct SVI.
4. Use `traceroute` to see where packets are dropped.

# 6. Security Hardening & Production Best Practices

| Area | Recommendation | Example CLI |
|------|----------------|------------|
| **Management Access** | Use local admin accounts with strong passwords or integrate with RADIUS/TACACS+. | `username admin privilege 15 secret 5 $1$abcd$E9ZbK5YfK9eVh1KZpVYVb/` |
| **SSH Only** | Disable Telnet, enforce SSH v2. | `line vty 0 4`<br>`transport input ssh`<br>`transport output ssh` |
| **ACLs on Router‑on‑Stick** | Restrict inter‑VLAN traffic to needed flows (e.g., only allow DNS/HTTP). | `access-list 101 permit ip host 10.0.10.10 host 10.0.20.10`<br>`interface GigabitEthernet0/0.10`<br>`ip access-group 101 in` |
| **Port‑Security on Access Ports** | Limit MAC addresses, set violation mode to shutdown. | `interface FastEthernet0/1`<br>`switchport port-security`<br>`switchport port-security maximum 2`<br>`switchport port-security violation shutdown`<br>`switchport port-security mac-address sticky` |
| **BPDU Guard** | Prevent rogue switches on access ports. | `interface FastEthernet0/1`<br>`spanning-tree portfast bpduguard enable` |
| **Storm Control** | Mitigate broadcast storms on trunk. | `interface GigabitEthernet0/1`<br>`storm-control broadcast level 5.00` |
| **Logging & Syslog** | Forward logs to a central syslog server. | `logging host 10.0.0.250`<br>`logging trap informational` |
| **Software Updates** | Keep IOS images patched; use `show version` to verify. | `show version` |
| **Backup Configurations** | Schedule regular `copy running-config startup-config` or use TFTP/Ansible. | `copy running-config tftp://192.0.2.10/r1.cfg` |

**Production Checklist**
- [ ] All VLANs documented and unused VLANs removed.
- [ ] Native VLAN on trunk set to an unused VLAN (e.g., 99) to avoid VLAN hopping.
- [ ] Port‑security and BPDU guard enabled on all access ports.
- [ ] SSH keys generated, Telnet disabled.
- [ ] ACLs applied where needed; default‑deny stance.
- [ ] Regular configuration backups and change‑control process.
- [ ] Monitoring (SNMP, NetFlow) configured for visibility.

---
*Lab created by an Enterprise Network & Cloud Architect. Use responsibly and adapt to your environment.*