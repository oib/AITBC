# ARCHIVED: peertube-transcoder

**Status**: INACTIVE / ARCHIVED (planned for reactivation after v0.5)
**Date**: 2026-06-18
**Audit Session**: v0.4.25 Apps Audit

## Reason for Archival

This app has been identified as inactive during the v0.4.25 apps audit. The following factors led to this determination:

1. **No systemd service**: There is no `aitbc-peertube-transcoder.service` unit file, and the service is not registered in systemd.
2. **Stub implementation**: `main.py` contains only a stub `/transcode` endpoint that returns mock data. The implementation notes explicitly state: "For now, this is a stub."
3. **No active integration**: The app is not imported as a module anywhere in the codebase. The only references are in the CLI marketplace commands and historical release notes.
4. **Planned for future release**: This app is scheduled for full implementation and activation in a release after v0.5. It is retained in the codebase to preserve the API design and integration points.

## App Directory Contents

| File | Description |
|------|-------------|
| `main.py` | Stub FastAPI service (1 file, ~76 lines). Returns fake transcoding results. |
| `README.md` | Original app documentation |
| `DEPRECATED.md` | This file |

## Service Reference

- **Expected port**: 8220
- **Expected service name**: `aitbc-peertube-transcoder.service` (does not exist)
- **Wrapper script**: None

## Planned Reactivation (Post-v0.5)

To reactivate this app after v0.5, the following must be completed:

1. Replace the stub `main.py` with a real implementation that integrates with PeerTube runner.
2. Create a systemd service file (`aitbc-peertube-transcoder.service`) and register it with systemd.
3. Update `apps/peertube-transcoder/README.md` to reflect `active` status.
4. Remove this `DEPRECATED.md` file.

## Migration / Replacement

Until reactivation, there is no replacement for PeerTube transcoding functionality. If video transcoding is needed in the interim, consider:

- Reusing the `apps/ffmpeg` service, which provides real GPU-accelerated video processing.
- Implementing a new transcoding service from scratch based on actual PeerTube runner integration.

## Audit Notes

- Total apps audited: 26
- Active apps with services: 21
- Shared libraries (no service expected): 2 (`shared-core`, `shared-domain`)
- Apps without services but with real code: 2 (`pool-hub`, `zk-circuits`)
- **Inactive apps marked**: 1 (`peertube-transcoder`, archived pending v0.5+ reactivation)
