import os
import sys
import subprocess
import uuid
from openai import OpenAI

def get_groq_client():
    host = "api." + "groq" + ".com"
    return OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url=f"https://{host}/openai/v1")

def is_networking_lab(slug: str, title: str, domain: str) -> bool:
    text = f"{slug} {title} {domain}".lower()
    net_keywords = ["ccna", "vlan", "ospf", "bgp", "osi", "firewall", "iptables", "nmap", "network", "routing", "switching", "cisco", "segmentation"]
    cloud_keywords = ["aws", "azure", "gcp", "terraform", "kubernetes", "eks", "aks", "gke", "transit-gateway", "vpc"]
    if any(k in text for k in cloud_keywords) and not any(k in text for k in ["ccna", "ospf", "vlan", "cisco"]):
        return False
    return any(k in text for k in net_keywords)

def generate_architecture_png(slug: str, title: str, domain: str, post_summary: str) -> str:
    """Renders nested Cloud Cluster diagrams OR EVE-NG grid-style Cisco topologies matching reference styles."""
    os.makedirs("static/images/diagrams", exist_ok=True)
    out_base = f"static/images/diagrams/{slug}"
    png_path = f"{out_base}.png"
    script_path = f"/tmp/{slug}_diag.py" if os.name != "nt" else f"{slug}_diag.py"

    net_mode = is_networking_lab(slug, title, domain)
    client = get_groq_client()

    if net_mode:
        style_rules = (
            "EVE-NG NETWORK TOPOLOGY STYLE:\n"
            "- Set `graph_attr = {\"bgcolor\": \"#F8FAFC\", \"splines\": \"line\", \"rankdir\": \"LR\", \"nodesep\": \"1.1\", \"ranksep\": \"1.4\", \"fontname\": \"Arial\"}`\n"
            "- Set `edge_attr = {\"color\": \"#2B6CB0\", \"penwidth\": \"1.8\", \"fontsize\": \"10\", \"fontcolor\": \"#1A202C\"}`\n"
            "- Import Cisco icons from `diagrams.cisco.router` (Router) and `diagrams.cisco.switch` (Layer2Switch, Layer3Switch) or `diagrams.cisco.security` (Firewall).\n"
            "- Label nodes cleanly like `R1`, `R2`, `SW1`, `FW1`.\n"
            "- Use `Edge(label=\"10.2.0.0/16\", headlabel=\".2 (e0/0)\", taillabel=\".1 (e0/1)\")` so interface names and IP subnets appear on links just like EVE-NG."
        )
    else:
        style_rules = (
            "ENTERPRISE CLOUD ARCHITECTURE STYLE:\n"
            "- Set `graph_attr = {\"bgcolor\": \"white\", \"splines\": \"ortho\", \"pad\": \"0.5\", \"nodesep\": \"0.7\", \"ranksep\": \"0.9\"}`\n"
            "- Use nested `with Cluster(\"AWS Cloud / Azure / GCP\"):` -> `with Cluster(\"VPC 10.0.0.0/16\"):` -> `with Cluster(\"Availability Zone A\"):` and `with Cluster(\"Web Subnet 10.0.0.0/24\"):`.\n"
            "- Import official vendor icons from `diagrams.aws.network`, `diagrams.aws.compute`, `diagrams.aws.database`, `diagrams.azure.network`, `diagrams.gcp.network`, or `diagrams.k8s.compute`.\n"
            "- Show clear tiered flow: Users -> DNS/CDN -> Load Balancer -> Auto Scaling Web/App Subnets -> Multi-AZ Database."
        )

    prompt = (
        f"Write a standalone Python script using `diagrams` (mingrammer/diagrams) for:\n"
        f"Title: {title}\nContext: {post_summary[:2500]}\n\n"
        f"{style_rules}\n\n"
        f"STRICT TECHNICAL RULES:\n"
        f"1. Output ONLY raw Python code (no markdown fences, no explanations).\n"
        f"2. Use `with Diagram(\"{title}\", filename=\"{out_base}\", show=False, outformat=\"png\", graph_attr=graph_attr):`\n"
        f"3. Import `Diagram, Cluster, Edge` from `diagrams`.\n"
        f"4. Keep to 6–12 nodes max and use only valid standard classes so it renders with zero errors."
    )

    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1800
    )
    code = next(iter(resp.choices)).message.content.strip()
    if code.startswith("```python"):
        code = code[len("```python"):].strip()
    if code.startswith("```"):
        code = code[3:].strip()
    if code.endswith("```"):
        code = code[:-3].strip()

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        subprocess.run([sys.executable, script_path], check=True, timeout=30)
        if os.path.exists(png_path):
            return f"/images/diagrams/{slug}.png"
    except Exception as e:
        print(f"[WARN] Diagram render skipped for {slug}: {e}")
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)
    return ""

def generate_eveng_unl(slug: str, title: str, domain: str) -> str:
    """Generates an EVE-NG .unl file ONLY for Networking/Security labs (skips Cloud/DevOps labs)."""
    if not is_networking_lab(slug, title, domain):
        return ""
    os.makedirs("static/labs", exist_ok=True)
    unl_path = f"static/labs/{slug}.unl"
    lab_uuid = str(uuid.uuid4())

    unl_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<lab name="{title}" id="{lab_uuid}" version="1" scripttimeout="300" lock="0">
  <topology>
    <nodes>
      <node id="1" name="R1" type="iol" template="iol" image="i86bi_linux_l3-adventerprisek9-ms.M" ethernet="4" serial="0" console="telnet" cpu="1" ram="512" left="240" top="140"/>
      <node id="2" name="R2" type="iol" template="iol" image="i86bi_linux_l3-adventerprisek9-ms.M" ethernet="4" serial="0" console="telnet" cpu="1" ram="512" left="420" top="80"/>
      <node id="3" name="R3" type="iol" template="iol" image="i86bi_linux_l3-adventerprisek9-ms.M" ethernet="4" serial="0" console="telnet" cpu="1" ram="512" left="420" top="200"/>
      <node id="4" name="SW1" type="iol" template="iol" image="i86bi_linux_l2-adventerprisek9-ms.SSA" ethernet="4" serial="0" console="telnet" cpu="1" ram="512" left="120" top="140"/>
    </nodes>
    <networks>
      <network id="1" type="bridge" name="10.1.0.0/16" left="180" top="140" visibility="0"/>
      <network id="2" type="bridge" name="10.2.0.0/16" left="330" top="110" visibility="0"/>
      <network id="3" type="bridge" name="10.3.0.0/16" left="330" top="170" visibility="0"/>
    </networks>
  </topology>
</lab>
"""
    with open(unl_path, "w", encoding="utf-8") as f:
        f.write(unl_xml)
    return f"/labs/{slug}.unl"
