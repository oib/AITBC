# Documentation Merge Plan for docs/project/

## Overview
This document outlines the plan to merge markdown files from `/opt/aitbc/docs/project/` into other doc directories or merge into other md files.

## Files to Merge

### Main Files
1. **1_files.md** → `docs/reference/REPOSITORY_STRUCTURE.md`
   - Repository file structure documentation
   - Fits well in reference section

2. **2_roadmap.md** → `docs/ROADMAP.md`
   - Development roadmap (93KB)
   - Should be at root level for easy access

3. **3_infrastructure.md** → `docs/infrastructure/INFRASTRUCTURE.md`
   - Infrastructure documentation (35KB)
   - Merge with existing infrastructure docs

4. **SECURITY.md** → `docs/security/SECURITY.md`
   - Security policy
   - Merge with existing security docs

5. **PROJECT_STRUCTURE.md** → `docs/archive/GPU_PROJECT_STRUCTURE.md`
   - GPU acceleration project structure (appears outdated/stale)
   - Move to archive

6. **WORKING_SETUP.md** → `docs/guides/getting-started/WORKING_SETUP.md`
   - Working setup documentation
   - Move to getting started guides

### Summary Files
7. **E2E_TEST_CREATION_SUMMARY.md** → `docs/reports/E2E_TEST_CREATION_SUMMARY.md`
   - Test creation summary
   - Move to reports

8. **SQLMODEL_METADATA_FIX_SUMMARY.md** → `docs/reports/SQLMODEL_METADATA_FIX_SUMMARY.md`
   - SQLModel metadata fix summary
   - Move to reports

9. **GITHUB_PULL_SUMMARY.md** → `docs/reports/GITHUB_PULL_SUMMARY.md`
   - GitHub pull summary
   - Move to reports

### User-Facing Files
10. **GIFT_CERTIFICATE_newuser.md** → `docs/guides/getting-started/GIFT_CERTIFICATE.md`
    - Gift certificate for new users
    - Move to getting started guides

11. **user_profile_newuser.md** → `docs/guides/getting-started/USER_PROFILE.md`
    - User profile for new users
    - Move to getting started guides

### Node Documentation
12. **aitbc.md** → `docs/infrastructure/NODE_AITBC.md`
    - AITBC server deployment guide
    - Move to infrastructure

13. **aitbc1.md** → `docs/infrastructure/NODE_AITBC1.md`
    - AITBC1 server deployment guide
    - Move to infrastructure

### Subdirectories
14. **ai-economics/** → `docs/ai-economics/`
    - AI economics documentation
    - Move to main docs level

15. **cli/** → Merge with `docs/cli/`
    - CLI documentation
    - Merge with existing CLI docs

16. **completion/** → `docs/completion/`
    - Completion documentation
    - Move to main docs level

17. **infrastructure/** → Merge with `docs/infrastructure/`
    - Infrastructure documentation
    - Merge with existing infrastructure docs

18. **planning/** → Merge with `docs/planning/`
    - Planning documentation
    - Merge with existing planning docs

19. **requirements/** → `docs/requirements/`
    - Requirements documentation
    - Move to main docs level

20. **workspace/** → `docs/development/workspace/`
    - Workspace documentation
    - Move to development

### Files to Keep
- **README.md** - Well-structured project documentation hub
  - Keep as is, serves as landing page

## Execution Order
1. Create target directories if needed
2. Merge subdirectories first
3. Merge main files
4. Update references
5. Delete original files
6. Update project/README.md to reflect changes
