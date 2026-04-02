# AITBC Requirements Migration Report

## Summary
- Files analyzed: 1
- Files migrated: 0
- Files kept: 1
- Errors: 0

## ⚠️ Files Kept (Specialized Dependencies)
### `/opt/aitbc/apps/coordinator-api/src/app/services/multi_language/requirements.txt`
- Coverage: 51.4%
- Uncovered packages: 16
  - **Translation Nlp**: 8 packages
    - `openai>=1.3.0`
    - `google-cloud-translate>=3.11.0`
    - `deepl>=1.16.0`
    - ... and 5 more
  - **Testing**: 1 packages
    - `pytest-mock>=3.12.0`
  - **Security**: 2 packages
    - `python-jose[cryptography]>=3.3.0`
    - `passlib[bcrypt]>=1.7.4`
  - **Other**: 5 packages
    - `Multi-Language Service Requirements`
    - `Dependencies and requirements for multi-language support`
    - `aioredis>=2.0.1`
    - ... and 2 more
