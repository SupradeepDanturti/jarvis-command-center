# Foundation validation — 2026-10-03

- 13 backend tests passed locally on Windows/Python 3.14, including connection-file refresh and preservation of unrelated files.
- JavaScript syntax check and Python compilation passed.
- Headless Microsoft Edge browser check passed: device pairing, live telemetry rendering, all six pages, graph range selection, dropped connection/reconnection, 1280×800 landscape, 800×1280 portrait, 412×915 narrow portrait, no horizontal overflow, logout revocation, and no page errors or CSP violations.
- Screenshots were visually inspected locally; generated artifacts are excluded from Git.
- Actual host detected NVIDIA GeForce RTX 4060 Laptop GPU, 20 logical CPU threads, approximately 16 GB RAM, and battery/AC information. Values are live, not fixtures.
- Local server is reachable from the laptop at port 8000. Physical Redmi Wi-Fi access, firewall access, real application launches, and media-key behavior remain to be checked on the devices. Automated launch tests mock dispatch to avoid opening applications unexpectedly.
- Test tooling emits a Starlette warning recommending `httpx2` for a future test-client migration; tests currently pass with the pinned `httpx` dependency.

## Reproduce optional browser check

Install Playwright separately if needed, then run `node scripts/browser-smoke.cjs` while the local server is running. The script uses installed Edge in headless mode and reads the current ignored `.state/pairing-code.txt`. For a bundled Playwright package, set `G16_PLAYWRIGHT_PATH` to its package directory. Screenshots are written to ignored `artifacts/`.

## Background startup and port migration

- Installed `G16 Command Center` in Windows Task Scheduler with the current user's interactive, limited-privilege principal and a user-specific logon trigger.
- Verified the task starts `.venv/Scripts/pythonw.exe` and serves healthy HTTP responses on port 18761; the previous server on port 8000 was stopped and its listener is gone.
- Verified battery startup is allowed, switching to battery does not stop the task, execution time is unlimited, duplicate task starts are ignored, and failed launches retry three times at one-minute intervals.
- Actual Desktop resolves to the user's OneDrive Desktop; both that location and Downloads contain `G16 Command Center.txt` with the current pairing code and port-18761 URL. Files are maintained locally and excluded from the repository.
- Browser smoke checks passed against the background server on port 18761. PowerShell scripts parsed without errors; Python startup entry point compiled successfully.
- Reboot/logon behavior is configured and the task was started manually to validate its action; an actual laptop reboot was not performed.
