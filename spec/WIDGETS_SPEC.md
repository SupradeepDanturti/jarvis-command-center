# Optional native widgets

Implemented 2026-10-04. All widget code and visuals are written for this dashboard. No code, assets or dependencies are imported from Xeneon-Edge-iFrame-Widgets.

## Interface

- **More → System & controls → Tablet settings → Optional widgets** holds the switches, clock choice and explicit city search/selection. All switches start off in a new browser. Preferences and city selection are browser-local, without credentials.
- Extra clock faces add Minimal, Analog and Moon phase to Flip. Extras off preserves the original Flip face. Focus and Rest links remain available through Clock/More. Compact landscape controls keep the face selector and immersive/wake buttons. Moon phase is a mean-cycle estimate, explicitly approximate.
- **More → Widgets** appears only when Weather/AQI or F1 is enabled. Tabs select one composition per screen with the existing floating dock. Disabled widgets are absent from tabs and swipe navigation; disabled Widgets deep links open settings.
- Weather uses Celsius, km/h, three-day high/low/rain forecasts and city-local sunrise/sunset. Conditions, update times and independent modelled US AQI/PM readings show missing data honestly.
- F1 shows the next future timed race in the current UTC season, circuit/location, optional qualifying, local start time and countdown. PC response time plus browser monotonic elapsed time drives the countdown. No lap, result, race-in-progress or live timing claim. Missing start times are omitted; no upcoming race is a distinct state.
- Immersive view, screen wake lock and local backgrounds work on these screens. Both views contain the composition within the available screen height. Readings scroll internally when space is tight, with header/footer controls fixed above the dock in normal view. The immersive exit is inline in the header. Fresh active Jarvis has a separate strip between header and readings; idle listening is hidden.
- Display behavior offers Widgets in slow rotation, displaying the selected enabled widget. Both online widgets off causes rotation to skip Widgets. Existing manual hold, pin, visibility, presentation, Focus and Rest blockers remain; rotation starts off.

## Data boundaries

The tablet sends authenticated requests only to the PC. Frontend CSP is unchanged: no third-party scripts, fonts, artwork, iframe pages or feed requests. HTTPS/WSS approval, direct-loopback owner management and setup-only HTTP port 18760 remain intact.

- `POST /api/widgets/locations`: strict bounded printable city query; explicit search, maximum five normalized results.
- `POST /api/widgets/weather` and `/api/widgets/air-quality`: finite numeric geographic coordinates rounded to three decimals. Authentication and same-origin checks precede provider work; extra fields, URLs, keys and paths fail validation.
- `GET /api/widgets/f1`: authenticated current-season schedule without browser provider parameters.
- Fixed HTTPS endpoints: Open-Meteo geocoding/forecast/air quality and Jolpica F1. Encoded query parameters, no redirects, no browser-cookie forwarding, public proxy or arbitrary fetch API.
- Six-second socket timeout, eight-second coroutine deadline, 512 KiB JSON cap, four pending provider requests, shared identical fetches and 30 new requests per minute globally. Browser requests time out after 12 seconds.
- No startup polling. Only a visible, approved, enabled Widgets screen polls once per minute. Leaving/hiding, Rest and unpairing abort browser requests; generation checks reject late replies. Unpairing clears browser feed caches. Explicit city search works in settings independently of Weather enablement.
- Shared 32-entry memory cache: weather TTL 15 minutes, air quality 30 minutes, locations/F1 one hour; failures cool down one minute. Provider errors become generic states and are never logged. No location/feed history is written to disk.
- Labelled cached weather expires after one hour, AQI after two hours and schedules after one day. Outdated observation timestamps fail parsing. Numeric ranges/finite values are checked; missing fields remain null. Provider strings render as text; upstream markup, images, URLs and commands are discarded.
- Shutdown cancels pending tasks and clears caches. External data never enters Jarvis tools, conversation or control dispatch.

## Sources and limits

- [Open-Meteo forecast](https://open-meteo.com/en/docs), [air quality](https://open-meteo.com/en/docs/air-quality-api), [geocoding](https://open-meteo.com/en/docs/geocoding-api) and [terms](https://open-meteo.com/en/terms). Free API use is non-commercial. The selected city's rounded coordinates are sent to providers; search sends the typed query. UI attribution names Open-Meteo, CAMS and GeoNames. Internet is required; no key is requested.
- [Jolpica races](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/races.md). Availability/schedule changes depend on the provider. Next-season lookup and live timing are outside this version.
- [NASA moon phase reference](https://eclipse.gsfc.nasa.gov/phase/phases1901.html): 2000-01-06 18:14 UT new moon and a 29.530588-day mean cycle anchor the approximate original moon drawing. Individual cycles vary. No NASA image is imported for this clock.

## Verification

Backend tests cover authorization, remote HTTP, origins/revocation, strict inputs, fixed-provider query encoding, reply caps/redirect refusal, corrupt/stale/missing readings, real timed events, shared fetches, caller cancellation, pending/cache/rate bounds, cooldowns and shutdown. Automated provider calls are mocked.

`scripts/widgets-smoke.cjs` uses a fresh trusted Edge profile and provider fixtures. It covers defaults, city choice without losing unsaved toggles, hostile text, clock faces/12-hour labels, enable/disable, deep links, persistence, failures, late replies, visibility, normal/immersive views with idle and speaking Jarvis, internal scrolling, clear header/exit/footer and dock, nine touch sizes, local-only frontend requests and CSP. `scripts/desk-policy-smoke.cjs` checks enabled rotation and disabled skipping with fake time. QA revokes only its own credentials; no physical control/voice writes.

Live provider parsing is checked separately with a public city fixture. Physical Redmi appearance, performance and network-loss recovery require owner confirmation; desktop viewport checks do not establish these.
