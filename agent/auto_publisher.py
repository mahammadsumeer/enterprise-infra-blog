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

tools = [
    {
        "type": "function",
        "function": {
            "name": "push_to_github",
            "description": "Creates or updates a file in the Hugo blog GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                    "commit_message": {"type": "string"}
                },
                "required": ["file_path", "content", "commit_message"]
            }
        }
    }
]

def publish_next_lab():
    curriculum_path = "agent/curriculum.json"
    with open(curriculum_path, "r", encoding="utf-8") as f:
        curriculum = json.load(f)

    next_topic = next((item for item in curriculum if not item["done"]), None)
    if not next_topic:
        print("All curriculum topics completed! Add new topics to agent/curriculum.json.")
        return

    print(f"Generating [{next_topic['level']}] {next_topic['domain']}: {next_topic['title']}...")

    today = date.today().isoformat()
    file_path = f"content/posts/{next_topic['slug']}.md"

    system_prompt = (
        "You are a Principal Enterprise Network, Cloud, and DevSecOps Architect (CCIE, AWS SAP, CISSP, CKA). "
        "Write deep-dive, production-grade educational labs with valid YAML frontmatter, Mermaid.js diagrams, "
        "IP/Resource tables, step-by-step configurations with inline comments, and verification commands."
    )

    user_prompt = (
        f"Create '{file_path}' using push_to_github.\n"
        f"YAML frontmatter must include:\n"
        f"title: '{next_topic['title']}'\n"
        f"date: '{today}'\n"
        f"draft: false\n"
        f"tags: ['{next_topic['domain']}', '{next_topic['level']}', 'Hands-On Lab']\n"
        f"categories: ['{next_topic['domain']}']\n\n"
        f"Required Sections:\n"
        f"1. Lab Objective & Prerequisites (Free/Open-Source tools like GNS3, EVE-NG, VirtualBox, AWS/Azure/GCP Free Tier)\n"
        f"2. Enterprise Architecture Topology (using a ```mermaid diagram)\n"
        f"3. Addressing & Resource Inventory Table\n"
        f"4. Step-by-Step Configuration (complete copy-pasteable commands/code)\n"
        f"5. Verification & Troubleshooting Commands\n"
        f"6. Security Hardening & Production Best Practices"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "push_to_github"}},
        temperature=0.3,
        max_tokens=8000
    )

    msg = response.choices.message
    if msg.tool_calls:
        args = json.loads(msg.tool_calls.function.arguments)
        push_to_github(args["file_path"], args["content"], args["commit_message"])
        next_topic["done"] = True
        updated_json = json.dumps(curriculum, indent=2)
        push_to_github(curriculum_path, updated_json, f"Mark topic #{next_topic['id']} as published")

if __name__ == "__main__":
    publish_next_lab()
