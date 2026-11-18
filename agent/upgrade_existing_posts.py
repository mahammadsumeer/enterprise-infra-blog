import os
import glob
import re
from dotenv import load_dotenv
from diagram_engine import generate_architecture_png, generate_eveng_unl

load_dotenv()

def upgrade_all_posts():
    for md_path in sorted(glob.glob("content/posts/*.md")):
        slug = os.path.splitext(os.path.basename(md_path))[0]
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        if "/images/diagrams/" in content:
            print(f"[SKIP] Already upgraded: {slug}")
            continue

        title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
        title = title_match.group(1) if title_match else slug.replace("-", " ").title()
        domain = "Cloud & Networking"

        print(f"[UPGRADING] {slug}...")
        png_url = generate_architecture_png(slug, title, domain, content[:2500])
        unl_url = generate_eveng_unl(slug, title, domain)

        addon_blocks = []
        if png_url:
            addon_blocks.append(f"### Official Architecture Diagram\n![{title} Architecture]({png_url})")
        if unl_url:
            addon_blocks.append(f"> **📥 Hands-On Lab Topology File:** [Download EVE-NG `.unl` Lab File]({unl_url}) *(Import directly into EVE-NG Community Edition)*")

        if addon_blocks:
            injection = "\n\n" + "\n\n".join(addon_blocks) + "\n\n"
            sec2 = re.search(r'(## 2\.[^\n]+\n)', content)
            if sec2:
                idx = sec2.end()
                content = content[:idx] + injection + content[idx:]
            else:
                parts = content.split("---", 2)
                if len(parts) == 3:
                    content = f"---{parts[1]}---{injection}{parts[2]}"

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[DONE] Upgraded {slug} with diagram & .unl file!")

if __name__ == "__main__":
    upgrade_all_posts()
