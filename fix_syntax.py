#!/usr/bin/env python3
import re
import glob

router_files = glob.glob("/opt/aitbc/apps/agent-management/src/app/routers/*.py")

for filepath in router_files:
    with open(filepath, "r") as f:
        content = f.read()

    original = content

    # Fix session dependency params without defaults
    # Pattern: session: Annotated[Session, Depends(get_session)]  (not followed by =)
    # Replace with: session: Annotated[Session, Depends(get_session)] = Depends()
    content = re.sub(
        r"session:\s*Annotated\[Session,\s*Depends\(get_session\)\](?!\s*=)",
        "session: Annotated[Session, Depends(get_session)] = Depends()",
        content,
    )

    # Fix current_user dependency params without defaults
    content = re.sub(
        r"current_user:\s*Annotated\[str,\s*Depends\(require_admin_key\(\)\)\](?!\s*=)",
        "current_user: Annotated[str, Depends(require_admin_key())] = Depends()",
        content,
    )

    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Fixed {filepath}")
    else:
        print(f"No changes {filepath}")
