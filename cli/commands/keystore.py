import click
import importlib.util
from pathlib import Path


def _load_keystore_script():
    """Dynamically load the top-level scripts/keystore.py module."""
    root = Path(__file__).resolve().parents[3]  # /opt/aitbc
    ks_path = root / "scripts" / "keystore.py"
    spec = importlib.util.spec_from_file_location("aitbc_scripts_keystore", ks_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load keystore script from {ks_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@click.group()
def keystore():
    """Keystore operations (create wallets/keystores)."""
    pass

@keystore.command()
@click.option("--address", required=True, help="Wallet address (id) to create")
@click.option(
    "--password-file",
    default="/var/lib/aitbc/keystore/.password",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to password file",
)
@click.option(
    "--output",
    default="/var/lib/aitbc/keystore",
    show_default=True,
    help="Directory to write keystore files",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing keystore file if present",
)
@click.pass_context
def create(ctx, address: str, password_file: str, output: str, force: bool):
    """Create an encrypted keystore for the given address.

    Examples:
      aitbc keystore create --address aitbc1genesis
      aitbc keystore create --address aitbc1treasury --password-file keystore/.password --output keystore
    """
    pwd_path = Path(password_file)
    with open(pwd_path, "r", encoding="utf-8") as f:
        password = f.read().strip()
    out_dir = Path(output) if output else Path("/var/lib/aitbc/data/keystore")
    out_dir.mkdir(parents=True, exist_ok=True)

    ks_module = _load_keystore_script()
    ks_module.create_keystore(address=address, password=password, keystore_dir=out_dir, force=force)
    click.echo(f"Created keystore for {address} at {out_dir}")


# Helper so other commands (genesis) can reuse the same logic
def create_keystore_via_script(address: str, password_file: str = "/var/lib/aitbc/data/keystore/.password", output_dir: str = "/var/lib/aitbc/data/keystore", force: bool = False):
    pwd = Path(password_file).read_text(encoding="utf-8").strip()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ks_module = _load_keystore_script()
    ks_module.create_keystore(address=address, password=pwd, keystore_dir=out_dir, force=force)
