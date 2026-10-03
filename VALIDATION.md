# Foundation validation — 2026-10-03

- 20 backend tests passed locally on Windows/Python 3.14, including connection-file refresh, approved-device authorization, revocation, credential persistence, certificate renewal and isolated certificate-download routes.
- JavaScript syntax check and Python compilation passed.
- Headless Microsoft Edge browser check passed: device pairing, live telemetry rendering, all seven pages including Device access, graph range selection, dropped connection/reconnection, 1280×800 landscape, 800×1280 portrait, 412×915 narrow portrait, no horizontal overflow, logout revocation, and no page errors or CSP violations.
- Screenshots were visually inspected locally; generated artifacts are excluded from Git.
- Actual host detected NVIDIA GeForce RTX 4060 Laptop GPU, 20 logical CPU threads, approximately 16 GB RAM, and battery/AC information. Values are live, not fixtures.
- Local server is reachable over trusted HTTPS on port 18761. The user confirmed the physical Redmi was approved and its dashboard works after certificate setup. Real application launches and media-key behavior still need an on-device check. Automated launch tests mock dispatch to avoid opening applications unexpectedly.
- Test tooling emits a Starlette warning recommending `httpx2` for a future test-client migration; tests currently pass with the pinned `httpx` dependency.

## Reproduce optional browser check

Install Playwright separately if needed, then run `node scripts/browser-smoke.cjs` while the local server is running. The script uses installed Edge in headless mode and reads the current ignored `.state/private/pairing-code.txt`. For a bundled Playwright package, set `G16_PLAYWRIGHT_PATH` to its package directory. Screenshots are written to ignored `artifacts/`. Run `node scripts/security-smoke.cjs` to validate LAN browser approval/revocation; set `G16_TABLET_URL` to the laptop's current HTTPS LAN address if it differs from the development machine.

## Background startup and port migration

- Installed `G16 Command Center` in Windows Task Scheduler with the current user's interactive, limited-privilege principal and a user-specific logon trigger.
- Verified the task starts `.venv/Scripts/pythonw.exe` and serves healthy HTTP responses on port 18761; the previous server on port 8000 was stopped and its listener is gone.
- Verified battery startup is allowed, switching to battery does not stop the task, execution time is unlimited, duplicate task starts are ignored, and failed launches retry three times at one-minute intervals.
- Actual Desktop resolves to the user's OneDrive Desktop; both that location and Downloads contain `G16 Command Center.txt` with the current pairing code and port-18761 URL. Files are maintained locally and excluded from the repository.
- Browser smoke checks passed against the background server on port 18761. PowerShell scripts parsed without errors; Python startup entry point compiled successfully.
- Reboot/logon behavior is configured and the task was started manually to validate its action; an actual laptop reboot was not performed.

## HTTPS and approved browsers

- Trusted HTTPS health and browser checks passed at localhost and the Wi-Fi IPv4 address. Browser certificate errors were not bypassed. Windows CA trust was explicitly confirmed by the user.
- Browser tests verified that an unknown LAN browser cannot access apps/telemetry, requires laptop approval, reconnects after page reload without a code, cannot manage other devices, and loses REST/WS access after revocation.
- Device credentials persisted when reopening the SQLite store and were denied after revocation; raw browser tokens were absent from database bytes.
- A separate HTTP setup-only listener was tested on port 18760. It returns the public CA download and instructions; credential, telemetry, control, and private-key paths return 404.
- Private-state Windows ACLs contain only this user's account, SYSTEM and administrators. The CA signing key is protected with user-scoped Windows DPAPI; only the public certificate is exported to Desktop/Downloads.
- The old HTTP tablet bookmark produced an empty response on the new TLS-only port. The user was guided to certificate installation through Android Settings and the HTTPS address.
