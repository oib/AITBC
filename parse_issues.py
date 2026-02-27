import re

with open("docs/10_plan/99_currentissue.md", "r") as f:
    content = f.read()

# We know that Phase 8 is completely done and documented in docs/13_tasks/completed_phases/
# We should only keep the actual warnings and blockers that might still be relevant, 
# and remove all the "Completed", "Results", "Achievements" sections.

# Let's extract only lines with warning/pending emojis
lines = content.split("\n")
kept_lines = []

for line in lines:
    if line.startswith("# Current Issues"):
        kept_lines.append(line)
    elif line.startswith("## Current"):
        kept_lines.append(line)
    elif any(icon in line for icon in ['⚠️', '⏳', '🔄']) and '✅' not in line:
        kept_lines.append(line)
    elif line.startswith("### "):
        kept_lines.append("\n" + line)
    elif line.startswith("#### "):
        kept_lines.append("\n" + line)

# Clean up empty headers
new_content = "\n".join(kept_lines)
new_content = re.sub(r'#+\s+[^\n]+\n+(?=#)', '\n', new_content)
new_content = re.sub(r'\n{3,}', '\n\n', new_content)

with open("docs/10_plan/99_currentissue.md", "w") as f:
    f.write(new_content.strip() + '\n')
