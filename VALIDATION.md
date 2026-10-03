# Foundation validation — 2026-10-03

- 11 backend tests passed locally on Windows/Python 3.14.
- JavaScript syntax check and Python compilation passed.
- Headless Microsoft Edge browser check passed: device pairing, live telemetry rendering, all six pages, graph range selection, dropped connection/reconnection, 1280×800 landscape, 800×1280 portrait, 412×915 narrow portrait, no horizontal overflow, logout revocation, and no page errors or CSP violations.
- Screenshots were visually inspected locally; generated artifacts are excluded from Git.
- Actual host detected NVIDIA GeForce RTX 4060 Laptop GPU, 20 logical CPU threads, approximately 16 GB RAM, and battery/AC information. Values are live, not fixtures.
- Local server is reachable from the laptop at port 8000. Physical Redmi Wi-Fi access, firewall access, real application launches, and media-key behavior remain to be checked on the devices. Automated launch tests mock dispatch to avoid opening applications unexpectedly.
- Test tooling emits a Starlette warning recommending `httpx2` for a future test-client migration; tests currently pass with the pinned `httpx` dependency.

## Reproduce optional browser check

Install Playwright separately if needed, then run `node scripts/browser-smoke.cjs` while the local server is running. The script uses installed Edge in headless mode and reads the current ignored `.state/pairing-code.txt`. For a bundled Playwright package, set `G16_PLAYWRIGHT_PATH` to its package directory. Screenshots are written to ignored `artifacts/`.
