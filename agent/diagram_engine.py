import sys
import os
import subprocess
import uuid
from openai import OpenAI

def get_groq_client():
    host = "api." + "groq" + ".com"
    return OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url=f"https://{host}/openai/v1")

def generate_architecture_png(slug: str, title: str, domain: str, post_summary: str) -> str:
    """Uses LLM + mingrammer/diagrams + Graphviz to render an official vendor PNG diagram."""
    os.makedirs("static/images/diagrams", exist_ok=True)
    out_base = f"static/images/diagrams/{slug}"
    png_path = f"{out_base}.png"
    script_path = f"/tmp/{slug}_diag.py" if os.name != "nt" else f"{slug}_diag.py"

    client = get_groq_client()
    prompt = (
        f"Write a standalone Python script using the `diagrams` library (mingrammer/diagrams) to generate an architecture "
        f"diagram for:\nTitle: {title}\nDomain: {domain}\nContext: {post_summary[:2500]}\n\n"
        f"STRICT RULES:\n"
        f"1. Output ONLY raw Python code (no markdown fences, no explanations).\n"
        f"2. Use `with Diagram(\"{title}\", filename=\"{out_base}\", show=False, outformat=\"png\"):`\n"
        f"3. Import ONLY valid standard classes from `diagrams.aws.network`, `diagrams.aws.compute`, "
        f"`diagrams.azure.network`, `diagrams.gcp.network`, `diagrams.k8s.compute`, `diagrams.onprem.network`, "
        f"`diagrams.onprem.compute`, `diagrams.onprem.security`, or `diagrams.generic.network` (e.g., Router, Switch, Firewall, Server, Client, VPC, EC2, ELB).\n"
        f"4. Keep the script simple (5 to 10 nodes max) so it never fails to import or render."
    )

    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1500
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
    """Generates a valid EVE-NG .unl XML lab topology file for networking/security labs."""
    os.makedirs("static/labs", exist_ok=True)
    unl_path = f"static/labs/{slug}.unl"
    lab_uuid = str(uuid.uuid4())

    unl_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<lab name="{title}" id="{lab_uuid}" version="1" scripttimeout="300" lock="0">
  <topology>
    <nodes>
      <node id="1" name="Core-RTR-01" type="iol" template="iol" image="i86bi_linux_l3-adventerprisek9-ms.M" ethernet="4" serial="0" console="telnet" cpu="1" ram="512" left="240" top="140"/>
      <node id="2" name="Dist-SW-01" type="iol" template="iol" image="i86bi_linux_l2-adventerprisek9-ms.SSA" ethernet="4" serial="0" console="telnet" cpu="1" ram="512" left="140" top="280"/>
      <node id="3" name="Dist-SW-02" type="iol" template="iol" image="i86bi_linux_l2-adventerprisek9-ms.SSA" ethernet="4" serial="0" console="telnet" cpu="1" ram="512" left="360" top="280"/>
      <node id="4" name="Edge-FW-01" type="qemu" template="pfsense" image="pfsense-CE-2.7" ethernet="4" console="vnc" cpu="1" ram="1024" left="240" top="40"/>
    </nodes>
    <networks>
      <network id="1" type="bridge" name="Net-Core-Edge" left="240" top="90" visibility="0"/>
      <network id="2" type="bridge" name="Net-Core-SW1" left="190" top="210" visibility="0"/>
      <network id="3" type="bridge" name="Net-Core-SW2" left="300" top="210" visibility="0"/>
    </networks>
  </topology>
</lab>
"""
    with open(unl_path, "w", encoding="utf-8") as f:
        f.write(unl_xml)
    return f"/labs/{slug}.unl"
