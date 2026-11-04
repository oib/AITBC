import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { resolveRpc, resolveRecord, readDeployerKey } from "./guards.js";

describe("resolveRpc", () => {
  it("allows http/https on exact loopback hostnames", () => {
    for (const u of ["http://127.0.0.1:8545", "http://localhost:8545", "https://localhost", "http://[::1]:8545"]) {
      assert.equal(resolveRpc({ RPC_URL: u }), u);
    }
  });
  it("refuses lookalike hosts that fooled the old unanchored regex", () => {
    for (const u of ["http://127.0.0.1.evil.example", "http://localhost.evil.example", "http://localhost@evil.example"]) {
      assert.throws(() => resolveRpc({ RPC_URL: u }), /refusing|invalid/);
    }
  });
  it("refuses non-loopback and non-http(s)", () => {
    for (const u of ["https://sepolia.infura.io/v3/x", "ftp://127.0.0.1", "http://127.0.0.1:8545@evil.example", "http://user:pw@127.0.0.1:8545", "http://user:pw@localhost:8545"]) {
      assert.throws(() => resolveRpc({ RPC_URL: u }), /refusing|invalid/);
    }
  });
});

describe("readDeployerKey", () => {
  it("refuses a key file with mode other than 0600", () => {
    const f = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "k")), "k");
    fs.writeFileSync(f, "a".repeat(64));
    fs.chmodSync(f, 0o644);
    assert.throws(() => readDeployerKey(f), /0600/);
    fs.chmodSync(f, 0o600);
    assert.equal(readDeployerKey(f), `0x${"a".repeat(64)}`);
  });
});

describe("resolveRecord", () => {
  it("refuses paths inside contracts/ or named deployments.json", () => {
    const here = path.resolve(import.meta.dirname, "../..");
    assert.throws(() => resolveRecord({ DEPLOY_RECORD: `${here}/x.json` }), /inside contracts/);
    assert.throws(() => resolveRecord({ DEPLOY_RECORD: "/tmp/deployments.json" }), /named like/);
    assert.equal(resolveRecord({ DEPLOY_RECORD: "/tmp/r.json" }), "/tmp/r.json");
  });
});
