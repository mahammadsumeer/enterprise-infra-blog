---
title: "CCNA Lab: Implementing EIGRP Advanced Features, Stub Routing, and Route Summarization"
date: "2026-11-19"
draft: false
tags: ["CCNA", "Intermediate", "Hands-On Lab"]
categories: ["CCNA"]
---

## 1. Lab Objective & Free Open-Source Prerequisites

### 1.1 Lab Objective
The purpose of this hands‑on lab is to give a **CCNA‑level** engineer a production‑grade experience with the following EIGRP (Enhanced Interior Gateway Routing Protocol) capabilities:

| # | Feature | Why it matters in a real‑world network |
|---|---------|----------------------------------------|
| 1 | **EIGRP Stub Routing** | Reduces routing table size on edge routers, limits route advertisement to only necessary networks, and improves convergence time. |
| 2 | **EIGRP Route Summarization (Class‑less)** | Minimises the number of routing entries, conserves bandwidth on routing updates, and simplifies troubleshooting. |
| 3 | **EIGRP Authentication (MD5)** | Guarantees that only trusted routers can exchange routing information, mitigating rogue routing attacks. |
| 4 | **EIGRP Metric Weights Tuning** | Allows fine‑grained control over path selection based on bandwidth, delay, reliability, load, and MTU. |
| 5 | **EIGRP Passive Interfaces** | Prevents unnecessary routing updates on interfaces that only host end‑hosts (e.g., LANs). |

By the end of the lab you will have a fully functional, **production‑ready** EIGRP deployment that demonstrates all of the above features, and you will be able to verify, troubleshoot, and harden the configuration.

### 1.2 Free Open‑Source Prerequisites
| Component | Recommended Free Tool | Version (minimum) | Installation notes |
|-----------|----------------------|-------------------|--------------------|
| Network Emulator | **GNS3** (Graphical Network Simulator) | 2.2.30 | Supports Cisco IOSv, IOSvL2, and Cisco CSR1000v images. |
| Cisco IOS Images | **Cisco IOSv (v15.6M)** – free for educational use via Cisco DevNet | N/A | Load into GNS3; ensure at least 256 MB RAM per router. |
| Terminal Emulator | **PuTTY** (Windows) / **iTerm2** (macOS) / **gnome‑terminal** (Linux) | Latest | SSH/Telnet client for console access. |
| Text Editor | **Visual Studio Code** (free) | 1.85+ | Use the *Markdown All in One* extension for easier editing. |
| Documentation | **Cisco Docs** (EIGRP Configuration Guide) | Current | Keep open for reference. |
| Optional – Automation | **Ansible** (community edition) | 2.14+ | For later lab extensions (playbooks). |

All of the above are **free** or **community‑licensed** and run on Windows, macOS, or Linux. The lab can be built entirely within GNS3, which provides a realistic IOS CLI environment without the need for physical hardware.

---

## 2. Enterprise Architecture Topology

The topology mimics a small‑to‑medium enterprise with three sites (HQ, Branch‑1, Branch‑2) interconnected via a **hub‑and‑spoke** WAN. Each site contains a **core router** (EIGRP enabled) and a **distribution switch** that hosts LAN hosts. The HQ core also runs **EIGRP stub** to limit the advertisement of internal subnets to the WAN.

![Enterprise Architecture Topology](/images/eigrp-advanced-lab-topology.svg)

**Key points of the diagram:**

* All core routers run **EIGRP AS 100**.
* **R1** (HQ) is configured as an **EIGRP stub** router, advertising only the HQ LAN and a default route.
* **R2** and **R3** are **full‑mesh** EIGRP routers that receive the stub advertisement.
* The WAN links are **Serial** interfaces (simulated in GNS3) with **point‑to‑point** addressing.
* Each distribution switch is a **Layer‑2** device; hosts are simple PCs that will be used for ping/trace tests.

---

## 3. Addressing & Resource Inventory Table

| Device | Interface | IP Address | Subnet Mask | Description |
|--------|-----------|------------|-------------|-------------|
| **R1 (HQ Core)** | Gig0/0 (to SW1) | 10.0.0.1 | /24 | HQ LAN |
| | Serial0/0 (to R2) | 172.16.1.1 | /30 | WAN to Branch‑1 |
| | Serial0/1 (to R3) | 172.16.2.1 | /30 | WAN to Branch‑2 |
| **SW1 (HQ Dist)** | VLAN10 (access) | 10.0.0.2 | /24 | Management VLAN |
| **PC1** | NIC | 10.0.0.10 | /24 | HQ host |
| **PC2** | NIC | 10.0.0.11 | /24 | HQ host |
| **R2 (Branch‑1 Core)** | Gig0/0 (to SW2) | 10.1.0.1 | /24 | Branch‑1 LAN |
| | Serial0/0 (to R1) | 172.16.1.2 | /30 | WAN to HQ |
| **SW2 (Branch‑1 Dist)** | VLAN10 | 10.1.0.2 | /24 | Management VLAN |
| **PC3** | NIC | 10.1.0.10 | /24 | Branch‑1 host |
| **R3 (Branch‑2 Core)** | Gig0/0 (to SW3) | 10.2.0.1 | /24 | Branch‑2 LAN |
| | Serial0/0 (to R1) | 172.16.2.2 | /30 | WAN to HQ |
| **SW3 (Branch‑2 Dist)** | VLAN10 | 10.2.0.2 | /24 | Management VLAN |
| **PC4** | NIC | 10.2.0.10 | /24 | Branch‑2 host |

### Additional Resources
* **EIGRP AS**: 100 (consistent across all routers)
* **Authentication Key**: `cisco123` (MD5)
* **Stub Configuration on R1**: Advertise only `10.0.0.0/24` and a default route (`0.0.0.0/0`).

---

## 4. Step‑by‑Step Configuration

> **NOTE** – All commands are **copy‑paste ready**. Use the `!` character to denote comment lines that you may delete after pasting if you prefer a clean config.

### 4.1 Common Baseline (All Routers)

```text
! -------------------------------------------------
! Basic hostname, no‑shutdown, and enable secret
! -------------------------------------------------
hostname <HOSTNAME>
no ip domain-lookup
enable secret 5 $1$Zr9p$Kf7VhJ3YcX8eY5f2cZp6R0
service timestamps log datetime msec
service password-encryption
!
! -------------------------------------------------
! Loopback for router ID (recommended)
! -------------------------------------------------
interface Loopback0
 ip address 192.168.<ID>.1 255.255.255.255
!
! -------------------------------------------------
! Enable IPv6 (optional, not used in this lab)
! -------------------------------------------------
ipv6 unicast-routing
!
! -------------------------------------------------
! Global EIGRP configuration (same AS on all routers)
! -------------------------------------------------
router eigrp 100
 eigrp router-id 192.168.<ID>.1
 eigrp log-neighbor changes
!
! -------------------------------------------------
! MD5 Authentication (key-chain)
! -------------------------------------------------
key chain EIGRP_KEY
 key 1
  key-string cisco123
!
! -------------------------------------------------
! Apply authentication to all interfaces later
! -------------------------------------------------
```

Replace `<HOSTNAME>` with `R1`, `R2`, or `R3` and `<ID>` with `1`, `2`, or `3` respectively.

### 4.2 R1 – HQ Core (Stub Router)

```text
! -------------------------------------------------
! Hostname and basic interface config
! -------------------------------------------------
hostname R1
!
interface GigabitEthernet0/0
 description Link to HQ Distribution Switch
 ip address 10.0.0.1 255.255.255.0
 no shutdown
!
interface Serial0/0
 description WAN to Branch-1 (R2)
 ip address 172.16.1.1 255.255.255.252
 encapsulation ppp
 no shutdown
!
interface Serial0/1
 description WAN to Branch-2 (R3)
 ip address 172.16.2.1 255.255.255.252
 encapsulation ppp
 no shutdown
!
! -------------------------------------------------
! Apply MD5 authentication to all EIGRP interfaces
! -------------------------------------------------
interface GigabitEthernet0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 EIGRP_KEY
!
interface Serial0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 EIGRP_KEY
!
interface Serial0/1
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 EIGRP_KEY
!
! -------------------------------------------------
! EIGRP Stub configuration
! -------------------------------------------------
router eigrp 100
 eigrp stub connected summary-only
 eigrp stub receive-only
 eigrp stub static
 eigrp stub redistributed
!
! -------------------------------------------------
! Summarize the WAN subnets (optional, for demonstration)
! -------------------------------------------------
router eigrp 100
 eigrp topology base
 eigrp topology metric weights 0 1 0 0 0
!
! -------------------------------------------------
! Passive interface for management VLAN (if any)
! -------------------------------------------------
interface GigabitEthernet0/0
 passive-interface
!
! -------------------------------------------------
! End of R1 configuration
! -------------------------------------------------
```

**Explanation of key lines:**

* `eigrp stub connected summary-only` – Advertises only directly‑connected networks (the HQ LAN) and a summary (default) route.
* `eigrp stub receive-only` – Prevents R1 from sending updates to neighbors; it only receives.
* `eigrp stub static` and `eigrp stub redistributed` – If you later add static routes or redistributed routes, they will be advertised automatically.
* `passive-interface` on the LAN interface stops unnecessary EIGRP hellos on a LAN that only hosts end‑devices.

### 4.3 R2 – Branch‑1 Core (Full‑mesh)

```text
! -------------------------------------------------
! Hostname and interface config
! -------------------------------------------------
hostname R2
!
interface GigabitEthernet0/0
 description Link to Branch-1 Distribution Switch
 ip address 10.1.0.1 255.255.255.0
 no shutdown
!
interface Serial0/0
 description WAN to HQ (R1)
 ip address 172.16.1.2 255.255.255.252
 encapsulation ppp
 no shutdown
!
! -------------------------------------------------
! Apply MD5 authentication
! -------------------------------------------------
interface GigabitEthernet0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 EIGRP_KEY
!
interface Serial0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 EIGRP_KEY
!
! -------------------------------------------------
! EIGRP configuration – enable, summarize, and tune metric
! -------------------------------------------------
router eigrp 100
 network 10.1.0.0 0.0.0.255
 network 172.16.1.0 0.0.0.3
 eigrp router-id 192.168.2.1
!
! Summarize the Branch‑1 LAN when advertising to HQ
! (Class‑less summarization)
!
interface Serial0/0
 ip summary-address eigrp 100 10.1.0.0 255.255.255.0
!
! Metric weights – give bandwidth higher priority
! (K1=1, K2=0, K3=1, K4=0, K5=0)
!
router eigrp 100
 eigrp topology metric weights 1 0 1 0 0
!
! -------------------------------------------------
! Passive interface for LAN (optional)
! -------------------------------------------------
interface GigabitEthernet0/0
 passive-interface
!
! -------------------------------------------------
! End of R2 configuration
! -------------------------------------------------
```

### 4.4 R3 – Branch‑2 Core (Full‑mesh)

```text
! -------------------------------------------------
! Hostname and interface config
! -------------------------------------------------
hostname R3
!
interface GigabitEthernet0/0
 description Link to Branch-2 Distribution Switch
 ip address 10.2.0.1 255.255.255.0
 no shutdown
!
interface Serial0/0
 description WAN to HQ (R1)
 ip address 172.16.2.2 255.255.255.252
 encapsulation ppp
 no shutdown
!
! -------------------------------------------------
! Apply MD5 authentication
! -------------------------------------------------
interface GigabitEthernet0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 EIGRP_KEY
!
interface Serial0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 EIGRP_KEY
!
! -------------------------------------------------
! EIGRP configuration – enable, summarize, and tune metric
! -------------------------------------------------
router eigrp 100
 network 10.2.0.0 0.0.0.255
 network 172.16.2.0 0.0.0.3
 eigrp router-id 192.168.3.1
!
! Summarize the Branch‑2 LAN when advertising to HQ
!
interface Serial0/0
 ip summary-address eigrp 100 10.2.0.0 255.255.255.0
!
! Metric weights – same as R2 for consistency
!
router eigrp 100
 eigrp topology metric weights 1 0 1 0 0
!
! -------------------------------------------------
! Passive interface for LAN (optional)
! -------------------------------------------------
interface GigabitEthernet0/0
 passive-interface
!
! -------------------------------------------------
! End of R3 configuration
! -------------------------------------------------
```

### 4.5 Distribution Switches (Layer‑2)

The distribution switches are simple VLAN‑10 access switches. No routing is required, but we configure an IP address for management.

```text
! -------------------------------------------------
! Example for SW1 (HQ)
! -------------------------------------------------
enable
configure terminal
hostname SW1
!
interface Vlan10
 ip address 10.0.0.2 255.255.255.0
 no shutdown
!
interface range FastEthernet0/1 - 24
 switchport mode access
 switchport access vlan 10
 spanning-tree portfast
!
exit
!
! Save config
write memory
!
```

Repeat the same pattern for **SW2** (`10.1.0.2/24`) and **SW3** (`10.2.0.2/24`).

### 4.6 Host Configuration (PCs)

On each PC, assign the static IPs shown in the inventory table and set the default gateway to the respective core router’s LAN IP.

* **PC1** – IP `10.0.0.10/24`, GW `10.0.0.1`
* **PC2** – IP `10.0.0.11/24`, GW `10.0.0.1`
* **PC3** – IP `10.1.0.10/24`, GW `10.1.0.1`
* **PC4** – IP `10.2.0.10/24`, GW `10.2.0.1`

You can use the OS network GUI or the command line (`ipconfig` / `ifconfig` / `netsh`) – no router‑side configuration is required.

---

## 5. Verification & Troubleshooting Commands

### 5.1 Basic Connectivity Checks

| Command | Expected Output | Purpose |
|---------|----------------|---------|
| `ping 10.0.0.1` from PC1 | Replies from 10.0.0.1 | Verify LAN reachability to R1 |
| `ping 10.1.0.1` from PC1 | Replies after crossing WAN | Verify end‑to‑end across EIGRP |
| `traceroute 10.2.0.10` from PC1 | 1️⃣ 10.0.0.1 (R1) <br> 2️⃣ 172.16.2.1 (R1‑Serial) <br> 3️⃣ 172.16.2.2 (R3‑Serial) <br> 4️⃣ 10.2.0.1 (R3) <br> 5️⃣ 10.2.0.10 (PC4) | Show path across stub and full‑mesh routers |
| `show ip route eigrp` on R2 | Shows routes: `10.0.0.0/24` (via 172.16.1.1), `10.2.0.0/24` (via 172.16.1.1) and default `0.0.0.0/0` (via 172.16.1.1) | Confirm that R2 learned stub routes from R1 |
| `show ip eigrp neighbors` on any router | Lists neighbor IP, interface, hold time, and uptime | Verify adjacency formation |
| `show ip eigrp topology` on R3 | Displays DUAL entries, metric values, and successor/feasible successors | Validate DUAL calculations |

#### Sample Output – `show ip eigrp neighbors` on R2

```text
R2#show ip eigrp neighbors
EIGRP-IPv4 Neighbors for AS(100)
H   Address          Interface       Hold   Uptime   SRTT   RTO  Q  Seq
0   172.16.1.1       Serial0/0       13    00:12:34  20    100  0  5
```

### 5.2 Stub Verification

On **R1**, the stub status can be confirmed:

```text
R1#show ip eigrp stub
EIGRP Stub Router
  Stub Configured: connected, summary-only, receive-only, static, redistributed
  Stub Advertised: connected, summary-only, static, redistributed
```

On **R2** and **R3**, you should see that the default route (`0.0.0.0/0`) is learned from R1:

```text
R2#show ip route eigrp
...
S* 0.0.0.0/0 [1/0] via 172.16.1.1, 00:00:12, Serial0/0
```

### 5.3 Summarization Check

The summary address you configured on the serial interfaces should appear in the routing table as a single entry:

```text
R2#show ip route eigrp
...
C   10.1.0.0/24 is directly connected, GigabitEthernet0/0
S   10.2.0.0/24 [1/0] via 172.16.1.1, 00:00:12, Serial0/0
```

Because we used `ip summary-address eigrp 100 10.2.0.0 255.255.255.0` on R2’s serial, the **branch‑2** network appears as a **summary** (if there were multiple sub‑nets, they would collapse into one entry).

### 5.4 Authentication Failure Test

To prove MD5 authentication is active, deliberately change the key on **R3** (e.g., `key-string wrongkey`) and reload the interface. You should see:

```text
R3#show ip eigrp interfaces
Interface       Peers   Retrans  SIA   Hello   Hold   Uptime
Serial0/0       0       0        0     5       15     00:00:00

R3#show logging | include EIGRP
*Mar 19 12:34:56.123: %EIGRP-5-ADJDOWN: Adjacent router 192.168.1.1 (Serial0/0) down due to authentication failure
```

Fix the key on both sides and the adjacency will re‑establish.

### 5.5 Troubleshooting Checklist

| Symptom | Likely Cause | Command(s) to Diagnose |
|---------|--------------|--------------------------|
| No EIGRP neighbors | Interface down, mismatched AS, missing authentication | `show ip interface brief`, `show ip eigrp interfaces`, `show running-config | include eigrp` |
| Stub routes missing on branch routers | Stub not configured, or `receive-only` missing on R1 | `show ip eigrp stub` on R1; `show ip route eigrp` on branch |
| Excessive routes (no summarization) | `ip summary-address` not applied, or wrong mask | `show ip eigrp topology` and verify summary entries |
| High CPU on core routers | Unnecessary hellos on LAN; missing `passive-interface` | `show processes cpu sorted | include EIGRP` |
| Authentication failures | Key mismatch, wrong key ID, or missing `key-chain` | `show logging | include EIGRP`, `show running-config | section key` |

---

## 6. Security Hardening & Production Best Practices

### 6.1 Authentication & Encryption
* **MD5 is mandatory** for any production EIGRP deployment. Use a **key-chain** with a unique key ID per router to simplify rotation.
* Store the key‑chain in a **read‑only** location on the router (`service password-encryption` already protects the key‑string in the config).
* Rotate keys every **90 days**. Use the `key chain` command to add a new key with a higher ID, then remove the old one after all neighbors have re‑authenticated.

### 6.2 Interface Hardening
| Action | Rationale |
|--------|-----------|
| `passive-interface default` + `no passive-interface <WAN>` | Stops EIGRP hellos on all interfaces except those that truly need them (WAN). |
| `no ip redirects` on WAN interfaces | Prevents the router from sending ICMP redirects that could be abused. |
| `no ip source-route` globally | Disables source‑routing, a known security risk. |
| `ip verify unicast source reachable-via rx` on LANs | Enables Unicast Reverse Path Forwarding (uRPF) to mitigate spoofed traffic. |

### 6.3 Route Filtering
* Use **distribute‑list** or **prefix‑list** on the stub router to **explicitly** control which networks are advertised. Example:

```text
ip prefix-list HQ-STUB seq 5 permit 10.0.0.0/24 le 32
ip prefix-list HQ-STUB seq 10 permit 0.0.0.0/0
router eigrp 100
  eigrp stub receive-only
  distribute-list prefix HQ-STUB out Serial0/0
```

* On branch routers, apply **route‑maps** to filter inbound updates if you need to block certain external routes (e.g., a rogue default route).

### 6.4 Logging & Monitoring
* Enable **EIGRP logging** for adjacency changes:

```text
logging buffered 100000
logging console informational
debug eigrp packets
debug eigrp fsm
```

* Forward logs to a **Syslog server** (e.g., `logging host 192.168.100.10`) for centralized analysis.
* Use **SNMPv3** with authentication and encryption to monitor EIGRP metrics without exposing community strings.

### 6.5 Redundancy & High Availability
* In a true production environment, replace the single‑point‑to‑point serial links with **dual‑homed** connections (e.g., MPLS L3VPN or DMVPN) and enable **EIGRP load balancing** (`variance` command) to use both paths.
* Consider **EIGRP over IPv6** for future‑proofing; the same concepts apply, but IPv6 eliminates NAT complications.

### 6.6 Documentation & Change Management
* Store the **entire configuration** in a version‑controlled repository (Git). Tag each release with a meaningful version (e.g., `v1.0‑EIGRP‑Stub‑Prod`).
* Maintain a **change‑request** log that records:
  * Date / Engineer
  * Reason for change (e.g., key rotation, topology addition)
  * Pre‑change backup (`copy running-config startup-config` + `archive tar /x:config.tar`)
  * Post‑change verification steps (as listed in Section 5)

### 6.7 Backup & Recovery
* Schedule a **daily automated backup** using `archive`:

```text
archive
 path flash:/archive
 write-memory
 time-period 1440
 maximum 30
```

* Test restoration on a **lab router** before applying to production.

### 6.8 Compliance Checklist (ISO 27001 / NIST 800‑53)

| Control | Implementation |
|---------|----------------|
| **AC‑17 Remote Access** | EIGRP is limited to internal interfaces; no external access. |
| **SC‑7 Boundary Protection** | MD5 authentication + ACLs on WAN interfaces (`ip access-group WAN-ACL in`). |
| **CM‑6 Configuration Settings** | All configurations are stored in Git, reviewed via pull‑request workflow. |
| **AU‑6 Audit Review** | Syslog server aggregates EIGRP logs; periodic review by SOC. |
| **IA‑5 Authenticator Management** | Keys rotated quarterly; stored encrypted in configuration. |

---

### 6.9 Lab Clean‑Up (Optional)

When you have finished the lab, you may want to reset the GNS3 project:

```text
write erase
reload
```

Or simply **stop** the GNS3 project and delete the topology file if you need to free up disk space.

---

## 7. Extending the Lab (Optional Advanced Topics)

1. **DMVPN with EIGRP** – Replace the point‑to‑point serial links with a dynamic multipoint VPN hub (R1) and spoke routers (R2, R3). This demonstrates EIGRP over GRE/IPsec.
2. **EIGRP over IPv6** – Duplicate the IPv4 configuration using `router eigrp 100` under the `ipv6` context, and enable `ipv6 eigrp stub`.
3. **Ansible Playbook** – Automate the entire configuration using an Ansible role that pushes the CLI commands via `network_cli` connection.
4. **NetFlow / sFlow Integration** – Enable flow export on the core routers to monitor traffic patterns across the WAN.
5. **BGP Redistribution** – If the enterprise also runs BGP for Internet connectivity, practice redistributing EIGRP routes into BGP with proper route‑maps and filters.

---

### Closing Remarks

This lab walks you through **every** step required to deploy a **secure, scalable, and production‑ready** EIGRP environment that leverages stub routing, class‑less summarization, and authentication. By following the configuration, verification, and hardening guidelines you will not only pass the CCNA exam objectives but also acquire the practical skills needed to design and operate real‑world enterprise networks.

Happy labbing, and remember: **Documentation, security, and repeatable automation are the three pillars of a resilient network.**