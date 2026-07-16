# v3.6.0 — Safer Setup And Updates

This release makes On Board easier to run as one central MCP checkout shared by
many projects.

## Highlights

- Added a local linked-project registry at `.onboard/linked-projects.json`.
- Added `setup-project.sh --list-linked` and `setup-project.sh --all-linked`.
- Added `doctor.sh --list-linked` and `doctor.sh --all-linked`.
- Added `update.sh --list-linked` and `update.sh --refresh-linked`.
- Made `update.sh` safer: it skips unrelated folders, backs up overwritten files, and does not refresh project files unless explicitly requested.
- Reworked setup around `python3 onboard_server.py`, a tracked launcher path that normally runs the local `.venv` directly and rebuilds it only if missing.
- Replaced noisy end-turn hooks with lightweight startup mini-brief hooks.
- Expanded agent roles and ticket controls for multi-agent workflows.

## Upgrade

```bash
bash update.sh
bash update.sh --refresh-linked
```

`--refresh-linked` preserves each project's registered hook mode. Restart your
MCP clients after updating.
