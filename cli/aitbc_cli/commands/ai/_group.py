"""The ``aitbc ai`` click group.

Kept in a leaf module so command submodules can register against it without
importing this package's ``__init__`` — ``__init__`` imports the submodules to
attach their commands, and a submodule importing the group back from the
package would close an import cycle.
"""

import click


@click.group(
    epilog="""Examples:

  aitbc ai submit --prompt 'transcribe audio'

  aitbc ai status --job-id job-123"""
)
def ai():
    """Submit, pay for, and inspect AI jobs and services through the coordinator."""
    pass
