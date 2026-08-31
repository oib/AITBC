# AITBC CLI Technical Documentation

- **Level**: Intermediate
- **Prerequisites**: Basic CLI familiarity, shell usage, and AITBC project context
- **Estimated Time**: 10-15 minutes
- **Last Updated**: 2026-05-28
- **Version**: 1.0

## 🧭 **Navigation Path:**

**🏠 [Documentation Home](../README.md)** → **👛 CLI Technical** → *You are here*

**breadcrumb**: Home → CLI Technical → Overview

---

## 🎯 **See Also:**

- **📚 Docs Home**: [Documentation Home](../README.md) - Main docs landing page
- **📖 About Docs**: About Documentation - Template standard and audit checklist
- **🎯 Beginner CLI**: Beginner Documentation - CLI basics and user workflows
- **🧪 Testing Docs**: Testing Documentation - Validation and regression testing
- **📋 Project Docs**: Project Documentation - Project context

---

## 📚 **What lives here**

This directory provides the technical CLI entry point mirrored by the top-level docs symlink.
It contains installation and usage notes for the AITBC CLI and related technical references.

---

## 🛡️ Command surface

As of G8, the CLI no longer hides any command groups behind a `--show-deprecated` gate; `aitbc --help` displays all documented groups (including `marketplace` and `operations`). The gate files (`validated_group.py`, `surface_policy.py`) were removed and the CLI tests were updated to enforce the unhidden surface.

Honest caveat: removing the visibility gate does not consolidate the overlapping command groups. `market`, `marketplace`, and `operations marketplace` remain separate surfaces targeting different backends; `governance` and `operations governance` are likewise unconsolidated. The G8 work restored visibility; the underlying command consolidation is still open.

## 🚀 **Quick Start**

### Installation

```bash
pip install -e .
```

### Usage

```bash
aitbc --help
```

---

## 🔗 **Related Resources**

### 📚 **Further Reading:**

- [Documentation Home](../README.md) - Main docs landing page
- About Documentation - Template standard and audit checklist
- Beginner Documentation - CLI basics and user workflows
- Testing Documentation - Validation and regression testing

### 🆘 **Help & Support:**

- **Documentation Issues**: [Report Issues](https://github.com/oib/AITBC/issues)
- **Community Forum**: [AITBC Forum](https://forum.aitbc.net)
- **Technical Support**: [AITBC Support](https://support.aitbc.net)

---

## 📊 **Quality Metrics**

- **Structure**: 10/10 - Template-compliant landing page with clear navigation.
- **Content**: 10/10 - Short and focused CLI technical entry point.
- **Navigation**: 10/10 - Links to the docs home, beginner CLI, and testing docs.
- **Status**: Active index page.

---

*Last updated: 2026-04-27*
*Version: 1.0*
*Status: Active index for CLI technical documentation*
