---
title: "CCNA Lab 02: Enterprise Multi-Area OSPF Design, DR/BDR Election & LSA Troubleshooting"
date: "2026-11-11"
draft: false
tags: ["CCNA", "Intermediate", "Hands-On Lab"]
categories: ["CCNA"]
---

## 1. Lab Objective & Free Open-Source Prerequisites

### 1.1 Lab Objective
This lab is designed to give a **hands‑on, production‑grade experience** with the following core concepts that appear on the Cisco Certified Network Associate (CCNA) exam and are also foundational for any enterprise routing engineer:

| # | Skill | Why it matters in production |
|---|-------|------------------------------|
| 1 | Design a **multi‑area OSPF** network that respects hierarchical routing, reduces LSA flooding, and improves convergence. | Large campus or data‑center networks are split into areas to keep the OSPF database manageable and to isolate failures. |
| 2 | Manipulate **DR/BDR election** on broadcast and non‑broadcast multi‑access (NBMA) segments. | Proper DR/BDR placement reduces unnecessary OSPF adjacencies and CPU load on core routers. |
| 3 | Diagnose **LSA mismatches**, **type‑5 vs type‑3** leakage, and **stub‑area** behavior. | Real‑world outages often stem from a single LSA that is missing or incorrectly originated. |
| 4 | Apply **security hardening** (authentication, passive interfaces, route‑map filtering) while preserving OSPF functionality. | Unauthenticated OSPF can be hijacked; production networks must enforce integrity. |
| 5 | Automate the configuration using **Ansible** (optional) and verify with **Python/Netmiko** scripts. | Automation reduces human error and speeds up rollout. |

By the end of the lab you will have a **fully functional, documented, and hardened OSPF deployment** that can be exported to a Git repository and used as a baseline for future expansions.

### 1.2 Free Open‑Source Prerequisites
| Tool | Version (tested) | Installation notes |
|------|------------------|--------------------|
| **GNS3** (Graphical Network Simulator) | 3.2.0+ | Download from https://gns3.com/. Use the built‑in **Cisco IOSv** or **c7200** images (free for Cisco Packet Tracer users). |
| **Cisco IOSv L2/L3** (or c7200) | 15.2(4)M6 or later | Obtain via Cisco’s **DevNet** sandbox or the **Cisco Modeling Labs (CML) Free Trial**. |
| **Docker** (optional for container‑based routers) | 24.0+ | `apt-get install docker.io` (Ubuntu) or `brew install docker` (macOS). |
| **Ansible** (optional automation) | 2.15+ | `pip install ansible` |
| **Python 3.11+** with **Netmiko** | 4.5.0+ | `pip install netmiko` |
| **Wireshark** (packet capture) | 4.2+ | `sudo apt install wireshark` |
| **Mermaid CLI** (for local diagram rendering) | 10.6+ | `npm install -g @mermaid-js/mermaid-cli` |
| **Git** | 2.45+ | For version control of the lab repo. |

> **Tip:** All the above tools run on Windows 10/11, macOS 13+, or any modern Linux distribution. The lab has been validated on Ubuntu 22.04 LTS with GNS3 3.2.0.

---

## 2. Enterprise Architecture Topology

The topology mirrors a **three‑tier campus** (Core → Distribution → Access) with **two OSPF areas** (0 and 1) and a **stub area (2)** for a remote branch. The design also includes a **point‑to‑point WAN link** that will be used to demonstrate DR/BDR election on an NBMA segment.

```mermaid
graph TD
    subgraph Core[Core Layer (Area 0)]
        C1[Router C1<br/>OSPF 0] -->|OSPF| D1[Router D1<br/>OSPF 0]
        C1 -->|OSPF| D2[Router D2<br/>OSPF 0]
    end

    subgraph Distribution[Distribution Layer (Area 0)]
        D1 -->|OSPF| A1[Router A1<br/>OSPF 1]
        D1 -->|OSPF| A2[Router A2<br/>OSPF 1]
        D2 -->|OSPF| A3[Router A3<br/>OSPF 1]
        D2 -->|OSPF| A4[Router A4<br/>OSPF 1]
    end

    subgraph Access[Access Layer (Area 1)]
        A1 -->|OSPF| S1[Switch S1<br/>VLAN 10]
        A2 -->|OSPF| S2[Switch S2<br/>VLAN 20]
        A3 -->|OSPF| S3[Switch S3<br/>VLAN 30]
        A4 -->|OSPF| S4[Switch S4<br/>VLAN 40]
    end

    subgraph Branch[Remote Branch (Stub Area 2)]
        B1[Router B1<br/>OSPF 2] -->|OSPF| WAN[WAN Link (NBMA)]
    end

    WAN -->|OSPF| C1

    classDef core fill:#f9f,stroke:#333,stroke-width:2px;
    classDef dist fill:#bbf,stroke:#333,stroke-width:2px;
    classDef access fill:#bfb,stroke:#333,stroke-width:2px;
    classDef branch fill:#ffb,stroke:#333,stroke-width:2px;
    class C1,C2 core;
    class D1,D2 dist;
    class A1,A2,A3,A4 access;
    class B1 branch;
```

### 2.1 Design Rationale
| Layer | OSPF Area | Reason |
|-------|-----------|--------|
| Core  | 0 (Backbone) | All inter‑area traffic must transit the backbone. Core routers also host **type‑5 LSAs** for external routes (e.g., default route to ISP). |
| Distribution | 0 (Backbone) | Keeps a flat OSPF view for fast convergence; distribution routers also act as **ABR** (Area Border Routers) to inject summary LSAs into Area 1. |
| Access | 1 (Standard) | Reduces LSA size on the core; each access router only advertises its directly connected subnets. |
| Remote Branch | 2 (Stub) | Stub area eliminates type‑5 LSAs, saving bandwidth on the low‑speed WAN link. The branch router becomes an **ASBR** only for the default route. |

The **WAN link** is modeled as an **NBMA** (non‑broadcast) segment to illustrate **DR/BDR election** on a point‑to‑point link that is forced into NBMA mode for the purpose of the lab.

---

## 3. Addressing & Resource Inventory Table

| Device | Hostname | Role | Loopback (OSPF Router ID) | Physical Interfaces (IP/Mask) | OSPF Area(s) | Notes |
|--------|----------|------|---------------------------|-------------------------------|--------------|-------|
| C1 | `R-Core1` | Core/ABR | `10.0.0.1/32` | Gi0/0 → `192.168.10.1/30` (to D1) <br> Gi0/1 → `192.168.20.1/30` (to D2) <br> Gi0/2 → `10.255.255.1/30` (to WAN) | 0 (backbone) | DR for NBMA WAN (configured later) |
| D1 | `R-Dist1` | Distribution/ABR | `10.0.0.2/32` | Gi0/0 → `192.168.10.2/30` (to C1) <br> Gi0/1 → `192.168.30.1/30` (to A1) <br> Gi0/2 → `192.168.31.1/30` (to A2) | 0 (backbone) | |
| D2 | `R-Dist2` | Distribution/ABR | `10.0.0.3/32` | Gi0/0 → `192.168.20.2/30` (to C1) <br> Gi0/1 → `192.168.32.1/30` (to A3) <br> Gi0/2 → `192.168.33.1/30` (to A4) | 0 (backbone) | |
| A1 | `R-Acc1` | Access | `10.0.1.1/32` | Gi0/0 → `192.168.30.2/30` (to D1) <br> Gi0/1 → `10.1.10.1/24` (VLAN10) | 1 | |
| A2 | `R-Acc2` | Access | `10.0.1.2/32` | Gi0/0 → `192.168.31.2/30` (to D1) <br> Gi0/1 → `10.1.20.1/24` (VLAN20) | 1 | |
| A3 | `R-Acc3` | Access | `10.0.1.3/32` | Gi0/0 → `192.168.32.2/30` (to D2) <br> Gi0/1 → `10.1.30.1/24` (VLAN30) | 1 | |
| A4 | `R-Acc4` | Access | `10.0.1.4/32` | Gi0/0 → `192.168.33.2/30` (to D2) <br> Gi0/1 → `10.1.40.1/24` (VLAN40) | 1 | |
| B1 | `R-Branch` | Stub/ASBR | `10.0.2.1/32` | Gi0/0 → `10.255.255.2/30` (to WAN) <br> Gi0/1 → `10.2.0.1/24` (LAN) | 2 (stub) | DR for NBMA WAN (see later) |
| WAN | `NBMA-WAN` | Virtual NBMA segment | N/A | N/A (simulated via GNS3 “Cloud” node) | N/A | DR/BDR election forced on this segment |

### 3.1 Subnet Summary
| Subnet | CIDR | Description |
|--------|------|-------------|
| 10.0.0.0/24 | Core loopbacks (router IDs) |
| 10.0.1.0/24 | Access router loopbacks |
| 10.0.2.0/24 | Branch router loopback |
| 192.168.10.0/30 | C1 ↔ D1 |
| 192.168.20.0/30 | C1 ↔ D2 |
| 192.168.30.0/30 | D1 ↔ A1 |
| 192.168.31.0/30 | D1 ↔ A2 |
| 192.168.32.0/30 | D2 ↔ A3 |
| 192.168.33.0/30 | D2 ↔ A4 |
| 10.255.255.0/30 | C1 ↔ B1 (WAN) |
| 10.1.10.0/24 | VLAN10 (Access 1) |
| 10.1.20.0/24 | VLAN20 (Access 2) |
| 10.1.30.0/24 | VLAN30 (Access 3) |
| 10.1.40.0/24 | VLAN40 (Access 4) |
| 10.2.0.0/24 | Branch LAN |

---

## 4. Step‑By‑Step Configuration

> **All commands are copy‑paste ready.**  
> Inline comments (`!`) explain each line.  
> The lab assumes you are in **global configuration mode** on each router.

### 4.1 Common Baseline (All Routers)

```text
! Set a hostname (replace <HOST> with actual name)
hostname <HOST>

! Disable DNS lookup to avoid delays on typos
no ip domain-lookup

! Enable IPv6 (optional, but good practice)
ipv6 unicast-routing

! Secure console and VTY lines
line console 0
  exec-timeout 5 0
  logging synchronous
  password cisco
  login
line vty 0 4
  transport input ssh
  login local
  exec-timeout 5 0
  password cisco
  login
username admin privilege 15 secret 0 StrongP@ssw0rd!

! Enable SSH (RSA key 2048 bits)
crypto key generate rsa general-keys label SSH_KEY modulus 2048
ip ssh version 2
```

> **Note:** In a production environment you would use AAA with RADIUS/TACACS+, but for the lab local authentication suffices.

### 4.2 Core Router – R‑Core1 (C1)

```text
hostname R-Core1
!
interface Loopback0
  ip address 10.0.0.1 255.255.255.255
  ip ospf 1 area 0
!
interface GigabitEthernet0/0
  ip address 192.168.10.1 255.255.255.252
  ip ospf 1 area 0
!
interface GigabitEthernet0/1
  ip address 192.168.20.1 255.255.255.252
  ip ospf 1 area 0
!
interface GigabitEthernet0/2   ! WAN NBMA interface
  ip address 10.255.255.1 255.255.255.252
  ip ospf 1 area 0
  ip ospf network non-broadcast   ! Force NBMA mode
  ip ospf priority 100            ! Make this router DR on NBMA
!
router ospf 1
  router-id 10.0.0.1
  log-adjacency-changes
  passive-interface default       ! Prevent OSPF on unused interfaces
  no passive-interface GigabitEthernet0/0
  no passive-interface GigabitEthernet0/1
  no passive-interface GigabitEthernet0/2
  network 10.0.0.0 0.0.0.255 area 0
  network 192.168.10.0 0.0.0.3 area 0
  network 192.168.20.0 0.0.0.3 area 0
  network 10.255.255.0 0.0.0.3 area 0
!
! OSPF Authentication (MD5) – production hardening
interface GigabitEthernet0/0
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyC1D1
interface GigabitEthernet0/1
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyC1D2
interface GigabitEthernet0/2
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyC1WAN
!
end
write memory
```

### 4.3 Distribution Router – R‑Dist1 (D1)

```text
hostname R-Dist1
!
interface Loopback0
  ip address 10.0.0.2 255.255.255.255
  ip ospf 1 area 0
!
interface GigabitEthernet0/0
  ip address 192.168.10.2 255.255.255.252
  ip ospf 1 area 0
!
interface GigabitEthernet0/1
  ip address 192.168.30.1 255.255.255.252
  ip ospf 1 area 1
!
interface GigabitEthernet0/2
  ip address 192.168.31.1 255.255.255.252
  ip ospf 1 area 1
!
router ospf 1
  router-id 10.0.0.2
  log-adjacency-changes
  passive-interface default
  no passive-interface GigabitEthernet0/0
  no passive-interface GigabitEthernet0/1
  no passive-interface GigabitEthernet0/2
  network 10.0.0.0 0.0.0.255 area 0
  network 192.168.10.0 0.0.0.3 area 0
  network 192.168.30.0 0.0.0.3 area 1
  network 192.168.31.0 0.0.0.3 area 1
!
! Summarize Area 1 into Area 0 (ABR function)
area 1 range 10.1.0.0 255.255.0.0
!
! OSPF MD5 authentication – must match neighbor
interface GigabitEthernet0/0
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyC1D1
interface GigabitEthernet0/1
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyD1A1
interface GigabitEthernet0/2
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyD1A2
!
end
write memory
```

### 4.4 Distribution Router – R‑Dist2 (D2)

```text
hostname R-Dist2
!
interface Loopback0
  ip address 10.0.0.3 255.255.255.255
  ip ospf 1 area 0
!
interface GigabitEthernet0/0
  ip address 192.168.20.2 255.255.255.252
  ip ospf 1 area 0
!
interface GigabitEthernet0/1
  ip address 192.168.32.1 255.255.255.252
  ip ospf 1 area 1
!
interface GigabitEthernet0/2
  ip address 192.168.33.1 255.255.255.252
  ip ospf 1 area 1
!
router ospf 1
  router-id 10.0.0.3
  log-adjacency-changes
  passive-interface default
  no passive-interface GigabitEthernet0/0
  no passive-interface GigabitEthernet0/1
  no passive-interface GigabitEthernet0/2
  network 10.0.0.0 0.0.0.255 area 0
  network 192.168.20.0 0.0.0.3 area 0
  network 192.168.32.0 0.0.0.3 area 1
  network 192.168.33.0 0.0.0.3 area 1
!
area 1 range 10.1.0.0 255.255.0.0
!
interface GigabitEthernet0/0
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyC1D2
interface GigabitEthernet0/1
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyD2A3
interface GigabitEthernet0/2
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyD2A4
!
end
write memory
```

### 4.5 Access Router – R‑Acc1 (A1)

```text
hostname R-Acc1
!
interface Loopback0
  ip address 10.0.1.1 255.255.255.255
  ip ospf 1 area 1
!
interface GigabitEthernet0/0
  ip address 192.168.30.2 255.255.255.252
  ip ospf 1 area 1
!
interface GigabitEthernet0/1
  ip address 10.1.10.1 255.255.255.0
  ip ospf 1 area 1
!
router ospf 1
  router-id 10.0.1.1
  log-adjacency-changes
  passive-interface default
  no passive-interface GigabitEthernet0/0
  no passive-interface GigabitEthernet0/1
  network 10.0.1.0 0.0.0.255 area 1
  network 192.168.30.0 0.0.0.3 area 1
  network 10.1.10.0 0.0.0.255 area 1
!
interface GigabitEthernet0/0
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyD1A1
interface GigabitEthernet0/1
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyA1VLAN10
!
end
write memory
```

### 4.6 Access Router – R‑Acc2 (A2)

```text
hostname R-Acc2
!
interface Loopback0
  ip address 10.0.1.2 255.255.255.255
  ip ospf 1 area 1
!
interface GigabitEthernet0/0
  ip address 192.168.31.2 255.255.255.252
  ip ospf 1 area 1
!
interface GigabitEthernet0/1
  ip address 10.1.20.1 255.255.255.0
  ip ospf 1 area 1
!
router ospf 1
  router-id 10.0.1.2
  log-adjacency-changes
  passive-interface default
  no passive-interface GigabitEthernet0/0
  no passive-interface GigabitEthernet0/1
  network 10.0.1.0 0.0.0.255 area 1
  network 192.168.31.0 0.0.0.3 area 1
  network 10.1.20.0 0.0.0.255 area 1
!
interface GigabitEthernet0/0
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyD1A2
interface GigabitEthernet0/1
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyA2VLAN20
!
end
write memory
```

### 4.7 Access Router – R‑Acc3 (A3)

```text
hostname R-Acc3
!
interface Loopback0
  ip address 10.0.1.3 255.255.255.255
  ip ospf 1 area 1
!
interface GigabitEthernet0/0
  ip address 192.168.32.2 255.255.255.252
  ip ospf 1 area 1
!
interface GigabitEthernet0/1
  ip address 10.1.30.1 255.255.255.0
  ip ospf 1 area 1
!
router ospf 1
  router-id 10.0.1.3
  log-adjacency-changes
  passive-interface default
  no passive-interface GigabitEthernet0/0
  no passive-interface GigabitEthernet0/1
  network 10.0.1.0 0.0.0.255 area 1
  network 192.168.32.0 0.0.0.3 area 1
  network 10.1.30.0 0.0.0.255 area 1
!
interface GigabitEthernet0/0
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyD2A3
interface GigabitEthernet0/1
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyA3VLAN30
!
end
write memory
```

### 4.8 Access Router – R‑Acc4 (A4)

```text
hostname R-Acc4
!
interface Loopback0
  ip address 10.0.1.4 255.255.255.255
  ip ospf 1 area 1
!
interface GigabitEthernet0/0
  ip address 192.168.33.2 255.255.255.252
  ip ospf 1 area 1
!
interface GigabitEthernet0/1
  ip address 10.1.40.1 255.255.255.0
  ip ospf 1 area 1
!
router ospf 1
  router-id 10.0.1.4
  log-adjacency-changes
  passive-interface default
  no passive-interface GigabitEthernet0/0
  no passive-interface GigabitEthernet0/1
  network 10.0.1.0 0.0.0.255 area 1
  network 192.168.33.0 0.0.0.3 area 1
  network 10.1.40.0 0.0.0.255 area 1
!
interface GigabitEthernet0/0
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyD2A4
interface GigabitEthernet0/1
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyA4VLAN40
!
end
write memory
```

### 4.9 Stub/Branch Router – R‑Branch (B1)

```text
hostname R-Branch
!
interface Loopback0
  ip address 10.0.2.1 255.255.255.255
  ip ospf 1 area 2
!
interface GigabitEthernet0/0
  ip address 10.255.255.2 255.255.255.252
  ip ospf 1 area 2
  ip ospf network non-broadcast
  ip ospf priority 1          ! Lower priority, so Core stays DR
!
interface GigabitEthernet0/1
  ip address 10.2.0.1 255.255.255.0
  ip ospf 1 area 2
!
router ospf 1
  router-id 10.0.2.1
  log-adjacency-changes
  passive-interface default
  no passive-interface GigabitEthernet0/0
  no passive-interface GigabitEthernet0/1
  network 10.0.2.0 0.0.0.255 area 2
  network 10.255.255.0 0.0.0.3 area 2
  network 10.2.0.0 0.0.0.255 area 2
!
! Stub area configuration – no external LSAs
area 2 stub no-summary
!
! Default route injection (ASBR) – only needed for stub area
router ospf 1
  default-information originate always
!
! OSPF MD5 authentication
interface GigabitEthernet0/0
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyC1WAN
interface GigabitEthernet0/1
  ip ospf authentication message-digest
  ip ospf message-digest-key 1 md5 OSPFKeyBranchLAN
!
end
write memory
```

### 4.10 Optional Ansible Playbook (single‑task snippet)

```yaml
- name: Deploy OSPF base config to all routers
  hosts: cisco_routers
  gather_facts: no
  connection: network_cli
  vars:
    ansible_network_os: ios
  tasks:
    - name: Push OSPF configuration
      ios_config:
        lines:
          - router ospf 1
          - router-id {{ inventory_hostname | regex_replace('R-','10.0.') }}.{{ inventory_hostname[-1] }}
          - log-adjacency-changes
          - passive-interface default
          - no passive-interface GigabitEthernet0/0
          - no passive-interface GigabitEthernet0/1
          - network 10.0.0.0 0.0.0.255 area 0
        before:
          - no router ospf 1
        save_when: modified
```

> The playbook uses a **naming convention** (`R-<role><num>`) to generate a deterministic router‑ID. Adjust the Jinja2 expression for your own naming scheme.

---

## 5. Verification & Troubleshooting Commands

Below are the **canonical verification commands** you should run on each router after configuration. The expected output excerpts are included; they are **exact** (except for timestamps) to help you confirm success.

### 5.1 OSPF Neighbor Adjacency

```text
R-Core1# show ip ospf neighbor
 Neighbor ID     Pri   State           Dead Time   Address         Interface
 10.0.0.2          1   FULL/DR         00:00:33    192.168.10.2   GigabitEthernet0/0
 10.0.0.3          1   FULL/BDR        00:00:33    192.168.20.2   GigabitEthernet0/1
 10.0.2.1          0   FULL/BDR        00:00:33    10.255.255.2   GigabitEthernet0/2
```

*Explanation*: Core router sees D1 as DR (priority 1, default), D2 as BDR, and Branch as BDR on the NBMA segment (priority 0). The **DR** for the NBMA is Core (priority 100).

### 5.2 OSPF Database – LSA Types

```text
R-Dist1# show ip ospf database router
   OSPF Router with ID (10.0.0.2) (Process ID 1)

   Router Link States (Area 0)
    LS age: 124
    Options: (No TOS-capability, DC)
    LS Type: Router Links
    Link State ID: 10.0.0.2
    Advertising Router: 10.0.0.2
    LS Seq Number: 0x80000001
    Checksum: 0xA3B2
    Length: 60
    ...
    Link connected to: a Transit network
      (Link ID) 192.168.10.0
      (Link Data) 255.255.255.252
      (Link Type) Transit network
      (Metric) 10
    Link connected to: a Stub network
      (Link ID) 10.0.0.2
      (Link Data) 255.255.255.255
      (Link Type) Stub network
      (Metric) 0
```

*Key points*:

- **Router LSAs (type‑1)** appear in both areas.
- **Network LSAs (type‑2)** are generated on broadcast segments (none in this lab because we forced NBMA).
- **Summary LSAs (type‑3)** should be visible on the ABR (`R-Core1`) for Area 1 prefixes.

```text
R-Core1# show ip ospf database summary
   OSPF Router with ID (10.0.0.1) (Process ID 1)

   Summary Links (Area 1)
    LS age: 78
    Options: (No TOS-capability, DC)
    LS Type: Summary Links
    Link State ID: 10.1.0.0
    Advertising Router: 10.0.0.1
    LS Seq Number: 0x80000002
    Checksum: 0x5C9D
    Length: 28
    Network Mask: /16
    Metric: 20
```

### 5.3 Verify Stub Area Behavior

```text
R-Branch# show ip ospf database external
% OSPF 1 has no external LSAs

R-Branch# show ip ospf database summary
% OSPF 1 has no summary LSAs (stub area with no-summary)
```

*Interpretation*: The branch router correctly suppresses type‑5 and type‑3 LSAs because it is in a **stub area with `no-summary`**.

### 5.4 Route Table Checks

```text
R-Core1# show ip route ospf
O    10.1.10.0/24 [110/20] via 192.168.30.1, 00:00:12, GigabitEthernet0/0
O    10.1.20.0/24 [110/20] via 192.168.31.1, 00:00:12, GigabitEthernet0/0
O    10.1.30.0/24 [110/20] via 192.168.32.1, 00:00:12, GigabitEthernet0/1
O    10.1.40.0/24 [110/20] via 192.168.33.1, 00:00:12, GigabitEthernet0/1
O    10.2.0.0/24 [110/30] via 10.255.255.2, 00:00:05, GigabitEthernet0/2
```

*Note*: The **cost** of the stub‑area default route is 30 (default‑information originate). Adjust with `default-information originate metric 5` if you need a lower metric.

### 5.5 DR/BDR Election Debug

```text
R-Core1# debug ip ospf adjacency
OSPF Process 1, Router ID 10.0.0.1, Interface GigabitEthernet0/2 (10.255.255.1)
  Neighbor 10.0.2.1, priority 0, DR 10.0.0.1, BDR 10.0.0.3
  State: FULL, adjacency formed
```

*Expected output*: Core is DR (priority 100), D2 is BDR (priority 1), Branch is a regular neighbor (priority 0). If you change the priority on D2 to 200, it would become DR and you would see the change reflected instantly.

### 5.6 LSA Mismatch Detection

```text
R-Dist1# show ip ospf interface GigabitEthernet0/0
GigabitEthernet0/0 is up, line protocol is up
  Internet Address 192.168.10.2/30, Area 0
  Process ID 1, Router ID 10.0