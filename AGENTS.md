# G16 Command Center development

This is a local Windows FastAPI dashboard for a Dell G16 and Redmi Pad Pro. Read README.md for setup, SPEC.md for scope, SECURITY.md for trust boundaries, and VALIDATION.md for verified behavior. Project-wide rules are in .cursor/rules/.

- Keep the touch interface clear, responsive, and free of implementation details. Serve frontend assets locally; show unavailable sensors honestly.
- Preserve the desk-display design: one composition per screen, large readings/type, a floating dock, and full-screen clock/artwork. Keep detailed settings in More; avoid reintroducing a permanent sidebar, boxed overview widgets, or repeated status bars.
- Preserve HTTPS/WSS, approved browser authentication, direct-loopback owner management, and the setup-only HTTP listener. Follow .cursor/rules/security.mdc for changes touching these boundaries.
- Use port 18761 for the dashboard and 18760 for public certificate setup. Do not use common development port 8000.
- Keep .state/, secrets, private keys, recovery codes, database files, logs, and config/apps.local.json out of Git. Preserve existing approvals and CA trust when updating.
- Jarvis dependencies are optional and loaded in an isolated process only when enabled. Keep listening off at server startup, key entry/deletion restricted to the loopback owner, and OpenAI credentials DPAPI-protected. Never expand voice tools into arbitrary commands, paths, URLs, or argument arrays. Keep audio/transcripts out of logs; cancel late actions on disable or lock. See JARVIS_SPEC.md.
- Do not restart the working dashboard for static frontend or documentation edits. For necessary backend restarts, use scripts/restart-server.ps1, which waits for the previous process to release its mutex.
- Run appropriate checks before committing: `.venv\Scripts\python.exe -m pytest -q` for backend changes, `node --check` for changed frontend/scripts JavaScript files, and the browser checks in VALIDATION.md when pairing/navigation/screens change.
- Windows test temp directories can have stale ACLs. If needed, use a new, nonexistent ignored `.state/` directory with pytest `--basetemp`; never delete unrelated paths to repair tests.
- Browser checks use fresh QA profiles and revoke their own credentials. Never revoke the user's devices or bypass certificate validation to make tests pass.
- Update the relevant how-tos and validation notes with behavior changes. Distinguish automated checks, user-confirmed tablet behavior, and untested physical controls.
- Commit and push completed requested changes to the configured GitHub repository. Inspect staged content for generated state or secrets first; do not rewrite published history.
