# Approved device access

The HTTPS dashboard serves telemetry and controls only to approved browsers. The login shell and health endpoint remain public; unauthenticated devices cannot read hardware data, launch apps, send media controls, or open the telemetry WebSocket. This is an application allowlist, not a claim that other computers cannot reach the network port.

## Add your Redmi

1. Copy **G16 Dashboard CA.cer** from the laptop's Downloads folder to the tablet using a trusted transfer (such as USB), or download it at `http://LAPTOP_IP:18760`. With an HTTP download, compare the installed certificate's actual SHA-256 fingerprint with the trusted laptop connection file before using it.
2. In Android settings, install it as a **CA certificate**. Search settings for “CA certificate”; menus vary by Android/HyperOS version. If opening the downloaded file shows “Install CA certificates in Settings,” close that message and install through Settings instead. Install this public certificate, never a private key.
3. Open the `https://` tablet address in **G16 Command Center.txt**. Certificate validation must succeed; do not bypass browser security warnings.
4. Name the browser, then tap **Request approval**. Its fingerprint appears while it waits.
5. On the laptop, open **https://localhost:18761**. For first-time laptop access, enter the setup/recovery code from the connection text file.
6. Open **More → Device access → Approved devices** (`https://localhost:18761/#devices`), match the tablet's displayed name and fingerprint, then approve it. This list is also available on System.

The browser now reconnects without a code, including after laptop/server restarts. Approval lasts up to 180 days. Use the same browser/profile and address; clearing cookies, using a different browser, or changing the hostname/IP requires fresh approval. A router DHCP reservation can keep the Wi-Fi address stable.

## Remove a device

Use **More → Device access → Approved devices → Revoke access** on the laptop at localhost. Revocation immediately denies new requests and closes its live WebSocket within roughly one second. Unpairing from the device revokes that browser too. Each browser has its own credential, so revoking one does not disconnect the others.

## Boundaries

- Device approvals and revocations require an approved owner browser **and** a direct loopback connection. They cannot be performed by the tablet or through forwarded-client headers. The background server disables proxy-header trust.
- Knowing the recovery code does not authorize a remote device; it creates only a pending request that still needs laptop approval. Remote devices can also request approval without a code.
- Pending requests expire after ten minutes and are limited per address and globally. Unknown/expired/revoked credentials are denied.
- A random 256-bit browser credential is stored in an HttpOnly, SameSite=Strict, Secure cookie over HTTPS. The SQLite registry stores only its SHA-256 hash, device metadata, and approval status. Credentials are not URL parameters or localStorage values.
- SQLite here stores device access only. Server logs remain rotating files, and telemetry history remains in memory.
- Approved browsers can report only their own display dimensions, orientation, scale and fullscreen state over same-origin HTTPS. Device identity comes from the authenticated cookie; the request cannot select another device. Reports contain no credentials or hardware identifiers, are bounded to 128 current reports, expire from memory after five minutes, and are removed on revocation/logout. Only a direct-loopback owner can read device reports. These are browser-reported layout diagnostics, not proof of physical hardware identity.
- The game catalog, local game artwork, library refresh, and game launch require approved browser authentication. Refresh/launch also enforce same-origin requests. Launch requests contain only a detected ID; paths, URLs, arguments, and artwork paths come from trusted laptop records. Steam/Epic URI identifiers are generated/encoded by the server; other games use executable argument arrays without a shell.
- Ambient media and app logos are public static assets without credentials or personal game artwork. Scene/time-format preferences use localStorage; authentication credentials remain exclusively in HttpOnly cookies.
- This recognizes browser credentials, not immutable physical hardware. A copied/stolen browser profile can impersonate it. Keep the laptop/tablet locked and revoke a device if lost.
- Passkeys are not implemented in this release. WebAuthn needs a supported HTTPS origin and stable domain. Synced passkeys can also be available on multiple devices; they do not inherently enforce a physical-device allowlist.
- Bluetooth transport is not implemented. Pairing Bluetooth by itself does not authenticate HTTP or WebSocket requests.

## Laptop voice access

Jarvis starts disabled and acquires the laptop microphone only after an approved browser enables it. Approved browsers can view its bounded in-memory latest request/reply and change the capture input. Stereo Mix/loopback inputs are excluded. Closing the browser leaves the worker running; turning it off releases the microphone and inference process. Windows lock pauses listening and prevents action dispatch; a server restart starts it off.

Only a direct-loopback owner can save/delete the OpenAI API key. It is encrypted with user-scoped Windows DPAPI beneath the existing ACL-protected private state, never returned by an API, and never stored in JavaScript/localStorage. The password field clears after submission. API exceptions are reduced to generic messages; recordings/transcripts/keys are not logged. The key is passed to the child through Windows process initialization memory, never as a shell argument or environment variable. OpenAI requests use the fixed official HTTPS API endpoint.

Local wake detection is not speaker authentication. After activation, a short clip is uploaded for transcription, followed by command text for interpretation. Audio remains in memory and is discarded; only the most recent text exchange is kept in memory until disable. Model-selected actions undergo exact argument validation against existing trusted app/media registrations. No arbitrary executable/path/URL/argument/shell interface is provided. Action dispatch is refused after worker cancellation or Windows lock; completed actions are never retried because a reply request fails.

Optional runtime models are downloaded from fixed publisher URLs, checked against pinned SHA-256 hashes, and stored in private ignored state. Existing dashboard pairing, TLS and setup-only HTTP boundaries are unchanged. See [JARVIS_SPEC.md](JARVIS_SPEC.md) for component licenses and remaining physical validation.

## Local certificate and private files

`scripts/setup-https.ps1` creates a private local CA and server certificate, installs the public CA into the current Windows user's trust store, and exports only the public `.cer` file to Desktop/Downloads. Android trust requires the one-time installation above. The certificate identifies localhost and the laptop's current network addresses.

Private state is in ignored `.state/private/`, with Windows ACLs limited to the current account, SYSTEM and administrators. The CA signing key is protected with Windows DPAPI for this user. The server key remains in the protected directory for unattended HTTPS startup. Never export keys or copy the private state into a public/shared location.

The server refreshes its leaf certificate when network addresses change or renewal is needed. Clients still need to use an address matching its certificate; old cookies do not migrate to a new hostname/IP. Certificate trust persists across normal restarts. If the CA needs replacement, device trust must be renewed explicitly.

The background process also serves a setup-only HTTP listener on port 18760, containing public certificate download and instructions. It has no authentication credentials, hardware readings or Windows controls. An HTTP download can be substituted by a network attacker, so verify the installed CA fingerprint against the laptop's trusted file, or transfer the certificate over USB.

To remove Windows trust later, locate **G16 Command Center Local CA** in the current user's Trusted Root Certification Authorities and remove only that certificate. Remove the corresponding installed CA on Android too. Do not delete private state while the server is running.

References: [WebAuthn](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API), [browser cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie), [Web Bluetooth](https://developer.mozilla.org/en-US/docs/Web/API/Web_Bluetooth_API).
