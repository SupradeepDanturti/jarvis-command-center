# G16 Android app and Google Home integration

Status: **Planned — specification only; implementation deferred.**

Date: 2026-10-03. Target: Redmi Pad Pro in landscape, connected to the Dell G16.

## Goal and agreed scope

Package the existing G16 command surface as an Android app and add smart-home controls through **one Google Home account connection**. Keep the current visual design, laptop telemetry, game/app launchers, media controls, flip clock and ambient movies. Introduce **Connections** as the central place for external service connections, including future APIs.

Initial home devices are a **Govee lamp** and **Lefant M310Mop** robot vacuum. The exact Govee model is not yet known. The app must not require separate Govee, Lefant or Tuya logins/API keys. Existing manufacturer links within the user's Google Home account remain the source of device access.

This file does not authorize implementation now. The unfinished browser/Govee connection changes were removed. The running website remains the current shipped version.

## Feasibility and compatibility gate

An Android app can use Google's Home APIs to discover and control supported devices in an authorized home. A WebView wrapper alone is insufficient: native Android code must integrate the SDK and its permission flow. Ordinary browser tabs will not gain that SDK merely because the app exists. [Google Home APIs overview](https://developers.home.google.com/apis/android/overview)

Google documents lighting and robotic vacuum device types, but support for a category does not prove that either exact device exposes every desired command. Build the discovery prototype first and inspect the actual granted device types, traits, state and commands. A device working with Google Assistant voice commands is not sufficient evidence of Home API compatibility. [Supported Android device types](https://developers.home.google.com/apis/android/supported-device-types)

**Gate before full implementation:** authorize the user's Google Home account on the physical Redmi, discover the lamp and robot, then test at least one supported command for each. Record available and missing capabilities. If a device is not exposed, report that limitation and stop promising its controls; do not silently substitute a manufacturer connection.

The user must explicitly initiate physical command tests. Do not start the robot or change the lamp during automated discovery or unrelated checks.

## Proposed architecture

Use a hybrid Android app to preserve the existing interface rather than rewrite all ten screens.

- **Android shell:** Kotlin app, AndroidX WebView, lifecycle handling, fullscreen, landscape layout and foreground keep-awake.
- **Existing web interface:** load the approved laptop's HTTPS dashboard in the app's WebView. Reuse its current HTML/CSS/JavaScript and local artwork.
- **Native Google Home adapter:** SDK initialization, account/home consent, device discovery, state subscriptions, capability validation and commands.
- **Restricted message bridge:** the Connections interface calls a small set of typed native operations and receives sanitized device information. Google authorization data never enters JavaScript.
- **Windows backend:** continues providing laptop telemetry and registered controls over HTTPS/WSS on port 18761. It does not receive Google account passwords or become an undocumented Google API proxy.

Google Home commands execute through the native adapter on the tablet; laptop actions continue through the existing server. The bridge is available only to the trusted, approved dashboard inside the Android app. Chrome/Brave/desktop browsers keep their existing laptop functions; native-only connections show an accurate unsupported state there.

MVP depends on the laptop serving the dashboard. Independent smart-home operation with the laptop off, desktop access through a relay, and a bundled offline web interface are later design choices.

## Connections page and account flow

Add **More → Connections** in the existing floating navigation. Preserve the open composition and moving background; avoid a permanent sidebar or overview card grid.

1. Open the Android app and enter/confirm the trusted laptop address.
2. Approve the app's WebView as a new device through the existing laptop Device access flow. Do not copy a Chrome credential into the app.
3. Open Connections and choose **Connect Google Home**.
4. Launch the SDK's native account/permission UI. Select the Google account and home; explain the access being requested.
5. Discover authorized devices and display their real names, rooms, connectivity and available controls.
6. Remember the authorized connection according to SDK behavior. Recheck permissions and refresh state after app return/restart.

Google currently documents grants per home/structure, with one authorized structure at a time. Switching homes requires the corresponding permission flow. Reconfirm these constraints when implementation begins. [Android Permissions API](https://developers.home.google.com/apis/android/permissions)

Connections must distinguish Not connected, Connecting, Connected, Permission required, Unsupported device, Offline and Connection error. Cancelled consent leaves the service disconnected. Do not call a connection successful merely because an account picker closed or a cached device name exists.

Offer account/home switching, refresh and disconnect. Local disconnect immediately removes app controls and subscriptions; distinguish that from revoking the Google permission grant and provide the official revocation path. Changing or removing Google access must not unpair the laptop.

Future service adapters use this same page for authorization, connection health, capabilities and disconnect. Show only implemented services; future APIs must not appear as working integrations.

## Initial device controls

### Govee lamp

Desired controls: on/off, brightness, colour and white temperature. Display only those discovered through Google Home for the exact lamp. Respect actual capability ranges and colour modes; suppress unavailable controls. Manufacturer-specific scenes, segmented effects and music modes are outside MVP unless a later Google API capability supports them.

### Lefant M310Mop

Desired controls: start cleaning, pause/resume, stop and return to dock. Show battery, operating state, errors and supported cleaning modes only when reported by the SDK. Map controls to the actual discovered traits instead of assuming an on/off command means start/stop.

Maps, room selection, suction adjustment, mop settings, schedules and detailed cleaning history are outside MVP unless independently verified as available through Google Home.

### Shared behavior

- Show unavailable or unknown state honestly; never fabricate battery, brightness or cleaning activity.
- Disable unsupported and known-offline commands. Preserve a clearly marked last-known reading during interruptions.
- Show command progress and acknowledgement separately from reported physical state. A successful request does not prove the device finished an action.
- Prevent repeated taps while a command is pending, apply bounded timeouts and avoid automatic retries of physical commands.
- Subscribe to state changes while foregrounded; suspend collectors when hidden/disconnected and refresh when returning.
- Provide readable controls of at least 48 logical pixels. Preserve active interactions when telemetry or device state updates.

## Native bridge and connection contract

Proposed interface, to finalize after the prototype:

- `getConnectionStatus`: adapter availability, permission state, selected home and sanitized error.
- `connect`: launch native Google consent from a user gesture.
- `listDevices` / `subscribeDevices`: registered device IDs, names, rooms, supported actions, actual state and freshness.
- `execute`: registered device ID, allowlisted action and validated parameters; return a request ID and command result.
- `disconnect`: disable the local connection and clear subscriptions/cache without claiming Google consent was revoked.

Each message has a protocol version, request ID and bounded payload. Replies correlate with the request and expire with its lifecycle. Reject unknown methods/devices, unsupported actions, invalid values and stale permission/session state. Capability metadata comes from the SDK; callers cannot provide an arbitrary trait name, API URL, token or executable.

Normalize native and future backend adapters into one frontend connection model. Keep authorization, health, device capabilities and command results separate. There is no general-purpose native execution bridge.

## Security and trust

- Preserve existing HTTPS/WSS, approved devices, same-origin checks and owner-only device management. Do not change the device database, CA or startup task as a shortcut.
- Scope the WebView and bridge to the exact configured laptop origin: scheme, host and port. Verify the message origin and main frame; do not use wildcard origins or expose native operations to external pages/iframes.
- Prefer AndroidX origin-aware message APIs. Keep external links outside the bridge-enabled WebView. Disable unnecessary file/content access and release WebView debugging only in development builds. [Android native bridge security](https://developer.android.com/privacy-and-security/risks/insecure-webview-native-bridges)
- Revalidate laptop approval before enabling bridge operations. Disable pending operations when the session is revoked, unpaired or changed. A page's JavaScript flag alone is not an authentication proof.
- Use the SDK's native Google permission flow. Never collect Google passwords or place account credentials in the embedded webpage.
- Keep authorization in SDK/platform-managed storage. If application-managed secrets are unavoidable, use Android Keystore-backed encryption and exclude them from logs, backups, screenshots and Git.
- Android apps may not trust user-installed CAs by default. Plan explicit, narrowly scoped trust for this installation's public G16 CA; verify hostnames and expiry. Never proceed past a WebView TLS error or disable certificate checks. Confirm CA renewal/address-change behavior. [Android network security configuration](https://developer.android.com/privacy-and-security/security-config)
- Store only necessary device metadata; do not send home addresses, account tokens or complete Google responses to the Windows backend. Diagnostics must redact sensitive data.

## Tablet operation

Landscape is the primary and requested mode. Start validation at the Redmi's reported 1280×800 logical viewport and 2× pixel scale; measure the actual app viewport and system insets instead of assuming it equals the browser viewport.

Reuse fullscreen clock/ambient scenes, the floating dock and moving backgrounds. Handle Android navigation, back behavior, focus, multiwindow resizing and return from the native consent screen without losing the current screen or starting duplicate subscriptions/videos.

Keep the screen on while the approved app is visible, using Android's foreground keep-screen-on mechanism. Preserve a user opt-out; clear it when backgrounded. Coordinate the UI setting with native behavior so it reports actual state rather than relying solely on a browser wake lock. Do not request persistent CPU wake locks or override manual screen locking.

## Development and Google setup prerequisites

Before building, recheck the current SDK version, supported Android versions, required Google services, distribution terms and account/verification restrictions. Google's current setup guide describes Android 10+ development devices and SDK access through its developer site. Use the physical Redmi for the compatibility proof, not an assumed emulator substitute. Matter devices may require a supported Google hub; check the actual transport before requiring hardware. [SDK setup](https://developers.home.google.com/apis/android/sdk), [Google's Android codelab](https://developers.home.google.com/codelabs/home-apis-android-build-mobile-app)

Create an Android application identity and OAuth client with the package name and app signing certificate fingerprint; configure the intended account as a test user where required. Keep signing material and private configuration outside Git. Verify that consent actually completes before promising delivery: current Google documentation includes beta, verification and publication constraints. Personal sideload testing and Play Store publishing have different release requirements. [Android OAuth setup](https://developers.home.google.com/apis/android/oauth)

Use a dedicated signing identity whose updates preserve the app's private storage. Keep SDK libraries out of the repository when redistribution is not permitted; document a reproducible, pinned setup. No Android tools, SDKs, credentials or APK are installed/generated by this specification-only task.

## Delivery plan and acceptance gates

1. **Compatibility prototype:** set up SDK/OAuth, authorize the physical tablet, discover both devices, record traits and manually verify agreed commands. Do not proceed with unsupported-device promises.
2. **Android shell:** load the existing trusted dashboard, approve the new WebView device, verify TLS, telemetry, media dispatch, clock, movies and foreground keep-awake.
3. **Connections and bridge:** implement native consent, sanitized discovery, typed bridge, capability-driven lamp/robot controls, disconnect and truthful statuses.
4. **Lifecycle and security:** exercise cancelled/revoked permission, laptop revocation, Wi-Fi loss, cloud failures, app suspension/restart, repeated taps and untrusted-origin/iframe rejection.
5. **Private release:** produce a signed test APK, installation/update instructions and source documentation. Validate real controls on the Redmi with the user before calling the integration complete. Publication remains a separate task.

Automated checks use controlled SDK adapters and must not operate physical devices. Instrumentation verifies message origin/validation, permission gates, lifecycle cleanup, unsupported capabilities and command/state separation. Existing backend/browser checks protect the shipped laptop functions. Record physical device results separately from mock checks.

## Decisions to resolve when implementation starts

Exact Govee model; the controls Google actually exposes for Lefant M310Mop; Redmi Android/Google services versions; Google project and SDK availability; final package/signing identity; scoped CA-trust mechanism and stable laptop address; consent verification requirements; and whether offline operation or access from ordinary desktop browsers is needed later.

**Resume instruction:** start with the Google Home compatibility prototype for the two existing devices. Preserve one Google account connection, avoid separate manufacturer integrations, then build the Android shell and Connections page only after the capability gate passes.
