with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/utils/__init__.py", "r") as f:
    content = f.read()

# Fix the output() function to accept a title keyword argument since it's used in many commands
content = content.replace(
    """def output(data: Any, format_type: str = "table"):""",
    """def output(data: Any, format_type: str = "table", title: str = None):"""
)

content = content.replace(
    """            table = Table(show_header=False, box=None)""",
    """            table = Table(show_header=False, box=None, title=title)"""
)

content = content.replace(
    """                table = Table(box=None)""",
    """                table = Table(box=None, title=title)"""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/utils/__init__.py", "w") as f:
    f.write(content)
