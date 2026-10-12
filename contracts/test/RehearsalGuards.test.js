/**
 * BR-11 hardening — unit tests for the guard helpers. Pure filesystem/env
 * tests: no chain, no key material (test keys are generated hex, never
 * literals). Covers BR-10 findings: symlink keys-dir bypass, key-file mode,
 * malformed-key content echo, record-path protection, mandatory chain id,
 * the getAddress-via-Array.map regression, and the negative-check error gate.
 */
import { expect } from "chai";
import { getAddress } from "viem";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  assertSingleSigCannotExecute,
  normalizeAddresses,
  readSignerKey,
  resolveKeysDir,
} from "../scripts/rehearsal/lib.js";
import {
  readDeployerKeyFile,
  requireChainIdForKeyFile,
  resolveDeployRecord,
} from "../scripts/rehearsal/deploy-guards.js";

function tmpdir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "br11-guards-"));
}

function writeKey(dir, name, mode = 0o600, content = "ab".repeat(32) + "\n") {
  const file = path.join(dir, name);
  fs.writeFileSync(file, content, { mode });
  return file;
}

describe("RehearsalGuards (BR-11)", function () {
  it("resolveKeysDir refuses a symlink named rehearsal-sepolia pointing elsewhere", function () {
    const base = tmpdir();
    fs.mkdirSync(path.join(base, "custody"));
    fs.symlinkSync(path.join(base, "custody"), path.join(base, "rehearsal-sepolia"), "dir");
    expect(() => resolveKeysDir({ REHEARSAL_KEYS_DIR: path.join(base, "rehearsal-sepolia") }))
      .to.throw(/resolves to/);
    // A real directory with the right name still passes.
    const real = path.join(tmpdir(), "rehearsal-sepolia");
    fs.mkdirSync(real);
    expect(resolveKeysDir({ REHEARSAL_KEYS_DIR: real })).to.equal(real);
  });

  it("key readers refuse files with group/other mode bits", function () {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rehearsal-sepolia-x"));
    const loose = path.join(dir, "rehearsal-sepolia");
    fs.mkdirSync(loose);
    const key = writeKey(loose, "signer1.key", 0o640);
    expect(() => readSignerKey(loose, 1)).to.throw(/permission bits/);
    expect(() => readDeployerKeyFile(key)).to.throw(/permission bits/);
    fs.chmodSync(key, 0o600);
    expect(readSignerKey(loose, 1)).to.match(/^0x[0-9a-f]{64}$/);
    expect(readDeployerKeyFile(key)).to.match(/^0x[0-9a-fA-F]{64}$/);
  });

  it("readDeployerKeyFile rejects garbage without echoing the content", function () {
    const file = writeKey(tmpdir(), "k", 0o600, "garbage-xyzzy-not-a-key\n");
    let err;
    try {
      readDeployerKeyFile(file);
    } catch (e) {
      err = e;
    }
    expect(err).to.be.instanceOf(Error);
    expect(err.message).to.not.contain("garbage-xyzzy");
    expect(err.message).to.match(/64-hex secp256k1/);
  });

  it("requireChainIdForKeyFile refuses before the key file is touched", function () {
    expect(() => requireChainIdForKeyFile({ DEPLOYER_KEY_FILE: "/k" })).to.throw(/BRIDGE_REQUIRE_CHAIN_ID/);
    expect(() => requireChainIdForKeyFile({})).to.not.throw();
    expect(() => requireChainIdForKeyFile({
      DEPLOYER_KEY_FILE: "/k",
      BRIDGE_REQUIRE_CHAIN_ID: "11155111",
    })).to.not.throw();
  });

  it("resolveDeployRecord protects the real records only on the key-file path", function () {
    const contractsDir = path.join(tmpdir(), "contracts");
    fs.mkdirSync(contractsDir);
    const env = { DEPLOYER_KEY_FILE: "/k" };
    // Missing BRIDGE_DEPLOY_RECORD with a key file: refuse.
    expect(() => resolveDeployRecord(env, contractsDir, "sepolia")).to.throw(/BRIDGE_DEPLOY_RECORD/);
    // Real-record basename: refuse.
    expect(() => resolveDeployRecord(
      { ...env, BRIDGE_DEPLOY_RECORD: "/tmp/deployments-bridge-sepolia.json" },
      contractsDir, "sepolia"
    )).to.throw(/real deployments file/);
    // Inside contracts/ next to the real records: refuse.
    expect(() => resolveDeployRecord(
      { ...env, BRIDGE_DEPLOY_RECORD: path.join(contractsDir, "rehearsal.json") },
      contractsDir, "sepolia"
    )).to.throw(/inside contracts/);
    // Legitimate scratch path: accepted.
    expect(resolveDeployRecord(
      { ...env, BRIDGE_DEPLOY_RECORD: "/var/tmp/br9b/record.json" },
      contractsDir, "sepolia"
    )).to.equal(path.resolve("/var/tmp/br9b/record.json"));
    // Unset DEPLOYER_KEY_FILE: byte-identical defaults — env override verbatim,
    // then the network-named template verbatim.
    expect(resolveDeployRecord(
      { BRIDGE_DEPLOY_RECORD: "rel/out.json" }, contractsDir, "sepolia"
    )).to.equal("rel/out.json");
    expect(resolveDeployRecord({}, contractsDir, "sepolia"))
      .to.equal(`${contractsDir}/deployments-bridge-sepolia.json`);
  });

  it("normalizeAddresses yields plain EIP-55 for mixed-case input on a non-1 chain", async function () {
    // Regression for the phase-B footgun: .map(getAddress) fed the array index
    // to viem's EIP-1191 chainId parameter. Hardhat runs chainId 31337 here,
    // so a leaked ambient/chain argument would show immediately.
    const raw = [
      "0x5f659b20a89279c815b5b8b98b423e26e2737032", // lower
      "0xD7011E3E289B2E0B6CAD0B9A29CE18B0290E3D3C", // upper
      "0x7bD563129fe0822bb413B8c20cdda1187a7091d2", // mixed
    ];
    const got = normalizeAddresses(raw);
    const want = raw.map((a) => getAddress(a));
    expect(got).to.deep.equal(want);
    for (const a of got) expect(a).to.match(/^0x[0-9a-fA-F]{40}$/);
  });

  it("assertSingleSigCannotExecute rethrows unrelated errors", async function () {
    const deadKit = {
      createTransaction: async () => ({ fake: true }),
      signTransaction: async (t) => t,
      executeTransaction: async () => {
        throw new Error("RPC endpoint unreachable");
      },
    };
    await assertSingleSigCannotExecute(deadKit, [{ to: "0x" + "0".repeat(40), value: "0", data: "0x" }], "unused")
      .then(() => { throw new Error("should have rethrown"); })
      .catch((e) => expect(e.message).to.contain("RPC endpoint unreachable"));
    // ...but the pinned missing-signature refusal is accepted.
    const sigKit = {
      createTransaction: async () => ({ fake: true }),
      signTransaction: async (t) => t,
      executeTransaction: async () => {
        throw new Error("There is 1 signature missing");
      },
    };
    const err = await assertSingleSigCannotExecute(sigKit, [{ to: "0x" + "0".repeat(40), value: "0", data: "0x" }], "unused");
    expect(err.message).to.contain("signature missing");
  });
});
