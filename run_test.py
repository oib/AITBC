from click.testing import CliRunner
from aitbc_cli.commands.wallet import wallet
import pathlib
import json

runner = CliRunner()
mock_wallet_dir = pathlib.Path("/tmp/test_wallet_dir_qwe")
mock_wallet_dir.mkdir(parents=True, exist_ok=True)
wallet_file = mock_wallet_dir / "test_wallet.json"
with open(wallet_file, "w") as f:
    json.dump({"test": "data"}, f)

result = runner.invoke(wallet, ['delete', 'test_wallet', '--confirm'], obj={"wallet_dir": mock_wallet_dir, "output_format": "json"})
print(f"Exit code: {result.exit_code}")
print(f"Output: {result.output}")
