import os
import re
import json
from datetime import date
from github import Github, Auth
from openai import OpenAI
from diagram_engine import generate_architecture_png, generate_eveng_unl

GROQ_HOST = "api." + "groq" + ".com"
MODEL_NAME = "openai/gpt-oss-120b"

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url=f"https://{GROQ_HOST}/openai/v1",
)

def push_binary_or_text_to_github(file_path: str, content_bytes: bytes, commit_message: str):
    auth = Auth.Token(os.getenv("GH_PAT"))
    g = Github(auth=auth)
    repo = g.get_repo(os.getenv("GITHUB_REPOSITORY"))
    try:
        contents = repo.get_contents(file_path)
        repo.update_file(contents.path, commit_message, content_bytes, contents.sha)
        print(f"[UPDATED] {file_path}")
    except Exception:
        repo.create_file(file_path, commit_message, content_bytes)
        print(f"[CREATED] {file_path}")

def sanitize_mermaid(text: str) -> str:
    def fix_line(line):
        stripped = line.strip()
        if stripped.startswith(("graph ", "flowchart ", "sequenceDiagram", "subgraph", "end", "%%", "classDef", "style")):
            return line
        line = re.sub(r'([A-Za-z0-9_]+)\[([^"\]\n]+)\]', lambda m: f'{m.group(1)}["{m.group(2).strip()}"]', line)
        line = re.sub(r'([A-Za-z0-9_]+)\(([^"\)\n]+)\)', lambda m: f'{m.group(1)}("{m.group(2).strip()}")', line)
        line = re.sub(r'\|([^"\|\n]+)\|', lambda m: f'|"{m.group(1).strip()}"|', line)
        return line

    lines = text.splitlines()
    in_mermaid = False
    out = []
    for line in lines:
        if line.strip().startswith("```mermaid"):
            in_mermaid = True
            out.append(line)
        elif in_mermaid and line.strip() == "```":
            in_mermaid = False
            out.append(line)
        elif in_mermaid:
            out.append(fix_line(line))
        else:
            out.append(line)
    return "\n".join(out)

def publish_next_lab():
    curriculum_path = "agent/curriculum.json"
    with open(curriculum_path, "r", encoding="utf-8") as f:
        curriculum = json.load(f)

    next_topic = next((item for item in curriculum if not item["done"]), None)
    if not next_topic:
        print("All curriculum topics completed!")
        return

    slug = next_topic["slug"]
    title = next_topic["title"]
    domain = next_topic["domain"]
    level = next_topic["level"]
    print(f"Generating [{level}] {domain}: {title}...")

    today = date.today().isoformat()
    file_path = f"content/posts/{slug}.md"

    system_prompt = (
        "You are a Principal Enterprise Network, Cloud, and DevSecOps Architect (CCIE, AWS SAP, CISSP, CKA). "
        "Output ONLY raw, complete Hugo Markdown starting with --- YAML frontmatter. "
        "Do NOT wrap the response in ```markdown fences. Write at least 1,500 words of deep technical content. "
        "CRITICAL MERMAID RULE: Always wrap every Mermaid node and edge label in double quotes, e.g., "
        "A[\"Client VM (Ubuntu)\"] -->|\"HTTPS (443)\"| B[\"Router (IOS-XE)\"]."
    )

    user_prompt = (
        f"Write a complete, production-grade hands-on lab in Hugo Markdown.\n"
        f"Start your response immediately with this exact YAML frontmatter:\n"
        f"---\n"
        f"title: \"{title}\"\n"
        f"date: \"{today}\"\n"
        f"draft: false\n"
        f"tags: [\"{domain}\", \"{level}\", \"Hands-On Lab\"]\n"
        f"categories: [\"{domain}\"]\n"
        f"---\n\n"
        f"Below the frontmatter, write detailed sections covering:\n"
        f"## 1. Lab Objective & Free Open-Source Prerequisites\n"
        f"## 2. Enterprise Architecture Topology (include a ```mermaid diagram with double-quoted labels)\n"
        f"## 3. Addressing & Resource Inventory Table\n"
        f"## 4. Step-by-Step Configuration (complete copy-pasteable commands/code with inline comments)\n"
        f"## 5. Verification & Troubleshooting Commands (with expected terminal outputs)\n"
        f"## 6. Security Hardening & Production Best Practices"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=8000
    )

    markdown_content = next(iter(response.choices)).message.content.strip()
    if markdown_content.startswith("```markdown"):
        markdown_content = markdown_content[len("```markdown"):].strip()
    if markdown_content.endswith("```"):
        markdown_content = markdown_content[:-3].strip()

    markdown_content = sanitize_mermaid(markdown_content)

    if len(markdown_content) < 1500 or not markdown_content.startswith("---"):
        raise ValueError(f"Generated article too short or invalid ({len(markdown_content)} chars). Aborting commit.")

    # Generate official Diagram-as-Code PNG and EVE-NG .unl topology file
    png_url = generate_architecture_png(slug, title, domain, markdown_content[:2500])
    unl_url = generate_eveng_unl(slug, title, domain)

    addon_blocks = []
    if png_url:
        local_png = f"static{png_url}"
        if os.path.exists(local_png):
            with open(local_png, "rb") as img_f:
                push_binary_or_text_to_github(local_png, img_f.read(), f"Add architecture diagram for {slug}")
            addon_blocks.append(f"### Official Architecture Diagram\n![{title} Architecture]({png_url})")

    if unl_url:
        local_unl = f"static{unl_url}"
        if os.path.exists(local_unl):
            with open(local_unl, "rb") as unl_f:
                push_binary_or_text_to_github(local_unl, unl_f.read(), f"Add EVE-NG lab topology for {slug}")
            addon_blocks.append(f"> **📥 Hands-On Lab Topology File:** [Download EVE-NG `.unl` Lab File]({unl_url}) *(Import directly into EVE-NG Community Edition)*")

    if addon_blocks:
        injection = "\n\n" + "\n\n".join(addon_blocks) + "\n\n"
        sec2 = re.search(r'(## 2\.[^\n]+\n)', markdown_content)
        if sec2:
            idx = sec2.end()
            markdown_content = markdown_content[:idx] + injection + markdown_content[idx:]

    push_binary_or_text_to_github(file_path, markdown_content.encode("utf-8"), f"Publish lab: {title}")

    next_topic["done"] = True
    push_binary_or_text_to_github(curriculum_path, json.dumps(curriculum, indent=2).encode("utf-8"), f"Mark topic #{next_topic['id']} as published")

if __name__ == "__main__":
    publish_next_lab()
