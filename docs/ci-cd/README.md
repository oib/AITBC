# CI/CD Documentation

This directory contains CI/CD pipeline and DevOps documentation.

## 📚 Documentation Files

### [CI-CD-Pipeline-Guide.md](./CI-CD-Pipeline-Guide.md)

> **Not implemented.** This is a foreign template describing a yarn/Next.js
> pipeline (Stripe, Linear, `dev` branch) that was never adopted here — see
> the banner at the top of the file. AITBC's real CI is
> `.github/workflows/ci.yml` + `.gitea/workflows/ci.yml` on `main`.
- Pull request process

**Use this when**: Setting up CI/CD or understanding the deployment workflow.

## 🔗 Related Documentation

- [CONTRIBUTING.md](../CONTRIBUTING.md) - Git workflow and commit standards
- [Security Architecture](../security/SECURITY_FIRST_ARCHITECTURE.md) - Security in CI/CD

## 🎯 CI/CD Agents

- **RTE** (Release Train Engineer) - PR creation and CI validation
- **TDM** (Technical Delivery Manager) - Coordination and blocker resolution

## ⚠️ Important Notes

1. **Always rebase before PR** - `git rebase origin/dev`
2. **Run ci:validate locally** - `yarn ci:validate` before pushing
3. **Use force-with-lease** - `git push --force-with-lease`
4. **Follow PR template** - `.github/pull_request_template.md`
