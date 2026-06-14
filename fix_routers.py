#!/usr/bin/env python3
import re
import glob

router_files = glob.glob("/opt/aitbc/apps/agent-management/src/app/routers/*.py")

for filepath in router_files:
    with open(filepath, "r") as f:
        content = f.read()

    original = content

    # 1. Remove 'from sqlalchemy.orm import Session' when sqlmodel Session is also imported
    lines = content.split("\n")
    new_lines = []
    has_sqlmodel_session = any("from sqlmodel import" in line and "Session" in line for line in lines)
    for line in lines:
        if line.strip() == "from sqlalchemy.orm import Session" and has_sqlmodel_session:
            continue
        new_lines.append(line)
    content = "\n".join(new_lines)

    # 2. Fix session: Session=Depends(Annotated[Session, Depends(get_session)])
    # -> session: Annotated[Session, Depends(get_session)]
    content = re.sub(
        r"session:\s*Session\s*=\s*Depends\(Annotated\[Session,\s*Depends\(get_session\)\]\)",
        "session: Annotated[Session, Depends(get_session)]",
        content,
    )

    # 3. Fix current_user: str=Depends(require_admin_key())
    # -> current_user: Annotated[str, Depends(require_admin_key())]
    content = re.sub(
        r"current_user:\s*str\s*=\s*Depends\(require_admin_key\(\)\)",
        "current_user: Annotated[str, Depends(require_admin_key())]",
        content,
    )

    # 4. Fix client_id: str = Depends(require_client_key())
    content = re.sub(
        r"client_id:\s*str\s*=\s*Depends\(require_client_key\(\)\)",
        "client_id: Annotated[str, Depends(require_client_key())]",
        content,
    )

    # 5. Fix session.execute(select(...)).all() for return types that expect list[T]
    # Replace session.execute(query).all() with list(session.exec(query).all())
    # But only when it appears in return statements or variable assignments that are returned
    # Actually let's just replace session.execute( with session.exec( in router files
    content = content.replace("session.execute(", "session.exec(")

    # 6. Fix list(session.exec(query).all()) where workflows = session.exec(query).all() followed by return list(workflows)
    # Actually we already changed session.execute to session.exec, so now we need:
    # return list(workflows) where workflows = session.exec(query).all()
    # With sqlmodel exec().all() returns list already, so return list(workflows) is fine

    # 7. In agent_router.py: fix request shadowing
    content = content.replace(
        "request = AgentExecutionRequest(workflow_id=workflow_id,",
        "execution_request_obj = AgentExecutionRequest(workflow_id=workflow_id,"
    )
    content = content.replace(
        "orchestrator.execute_workflow(request, current_user)",
        "orchestrator.execute_workflow(execution_request_obj, current_user)"
    )

    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Fixed {filepath}")
    else:
        print(f"No changes {filepath}")
