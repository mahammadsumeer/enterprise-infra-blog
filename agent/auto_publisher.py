import os
import json
from datetime import date
from github import Github, Auth
from openai import OpenAI

GROQ_HOST = "api." + "groq.com"
MODEL_NAME = "openai/gpt-oss-120b"

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url=f"https://{GROQ_HOST}/openai/v1",
)

def push_to_github(file_path: str, content: str, commit_message: str):
    auth = Auth.Token(os.getenv("GH_PAT"))
    g = Github(auth=auth)
    repo = g.get_repo(os.getenv("GITHUB_REPOSITORY"))
    try:
        contents = repo.get_contents(file_path)
        repo.update_file(contents.path, commit_message, content, contents.sha)
        print(f"[UPDATED] {file_path}")
    except Exception:
        repo.create_file(file_path, commit_message, content)
        print(f"[CREATED] {file_path}")

def publish_next_lab():
    curriculum_path = "agent/curriculum.json"
    with open(curriculum_path, "r", encoding="utf-8") as f:
        curriculum = json.load(f)

    next_topic = next((item for item in curriculum if not item["done"]), None)
    if not next_topic:
        print("All curriculum topics completed!")
        return

    print(f"Generating [{next_topic['level']}] {next_topic['domain']}: {next_topic['title']}...")

    today = date.today().isoformat()
    file_path = f"content/posts/{next_topic['slug']}.md"

    system_prompt = (
        "You are a Principal Enterprise Network, Cloud, and DevSecOps Architect (CCIE, AWS SAP, CISSP, CKA). "
        "Output ONLY raw, complete Hugo Markdown starting with --- YAML frontmatter. "
        "Do NOT wrap the response in ```markdown fences. Write at least 1,500 words of deep technical content."
    )

    user_prompt = (
        f"Write a complete, production-grade hands-on lab in Hugo Markdown.\n"
        f"Start your response immediately with this exact YAML frontmatter:\n"
        f"---\n"
        f"title: \"{next_topic['title']}\"\n"
        f"date: \"{today}\"\n"
        f"draft: false\n"
        f"tags: [\"{next_topic['domain']}\", \"{next_topic['level']}\", \"Hands-On Lab\"]\n"
        f"categories: [\"{next_topic['domain']}\"]\n"
        f"---\n\n"
        f"Below the frontmatter, write detailed sections covering:\n"
        f"## 1. Lab Objective & Free Open-Source Prerequisites\n"
        f"## 2. Enterprise Architecture Topology (include a ```mermaid diagram)\n"
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

    # Strip accidental outer markdown fences if present
    if markdown_content.startswith("```markdown"):
        markdown_content = markdown_content[len("```markdown"):].strip()
    if markdown_content.endswith("```"):
        markdown_content = markdown_content[:-3].strip()

    # Guardrail: Refuse to publish empty or truncated articles
    if len(markdown_content) < 1500 or not markdown_content.startswith("---"):
        raise ValueError(f"Generated article too short or invalid ({len(markdown_content)} chars). Aborting commit.")

    push_to_github(file_path, markdown_content, f"Publish lab: {next_topic['title']}")

    next_topic["done"] = True
    push_to_github(curriculum_path, json.dumps(curriculum, indent=2), f"Mark topic #{next_topic['id']} as published")

if __name__ == "__main__":
    publish_next_lab()
