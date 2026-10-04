# Personal Jarvis: connected, personalized and proactive

Planning record · 2026-10-04 · Initial connection/profile/primary-calendar foundation implemented; broader milestones remain planned. See [the foundation record](ASSISTANT_FOUNDATION.md).

## Direction and user decisions

Evolve the existing Jarvis Command Center into a personal agent inspired by Meta Muse and OpenAI dots. The user wants Google Calendar, Gmail, Google Sheets and **Google Health API connected to their Google account**, full service capabilities, and personalization. Google Health is the intended cloud service; Health Connect is not a substitute selected by the user.

The experience should remember useful preferences, handle requests across services, maintain ongoing goals, and return when something meaningful changes. Keep the existing Jarvis identity, concise completed-action replies, optional local voice, floating dock, and full-screen clock/artwork. This document is a build plan, not a claim that accounts are connected or features are shipped.

Meta describes Muse as a personal agent with connected services, persistent context, goals and a reviewable activity trail. OpenAI describes dots as agents that continue assigned work between conversations and bring back results or decisions. These are product references, not assumptions that their proprietary services can be embedded in this app. [Meta Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/), [Meet dots](https://learn.chatgpt.com/docs/dots).

The current app supplies the voice/control foundation. It does not yet have Google OAuth, personal-data adapters, durable tasks, editable long-term memory or background personal briefings. The current voice worker's four-step runner, single hardware-read slot and short physical-action timeout cannot simply be reused for a multi-service background agent.

## The personal experience

Examples of intended behavior, using real connected data once available:

- “Brief me for today.” Combine today's agenda, relevant inbox items and active responsibilities; add health summaries only when connected and requested by the configured briefing.
- “Find time for three workouts this week.” Consult availability and the user's saved preferences, offer specific slots, and create events when authorized.
- “Log this expense in my budget sheet.” Resolve the chosen spreadsheet, validate the target columns and append the supplied values once.
- “Reply to this email saying I can meet on Thursday.” Resolve the actual thread and recipient, check availability when requested, prepare the reply and apply the user's sending policy.
- “Help me stay consistent with sleep.” Track a user-defined goal against available sleep records and offer useful observations, without inventing readings or diagnoses.
- “Keep track of this project.” Maintain the responsibility, relevant sources, deadlines, completed steps and the next decision across conversations.
- “Remember that I prefer workouts after work.” Save a user-supplied preference with its source; “Forget that” removes it and prevents old summaries from reintroducing it.

The assistant should explain why a suggestion matters. It should not interrupt repeatedly, infer a habit from one event, or silently turn a third-party email into a new goal. API access and standing instructions are separate: full capability allows the requested operations, while individual requests and scoped standing policies determine when to use them.

## Personalization and memory

Provide **More → Personalization** and conversational equivalents. Onboarding can collect the preferred form of address, tone, language, timezone, typical work hours, quiet hours, briefing time, interests and current goals. Use America/Toronto as the suggested timezone for this installation; let the owner change it. Do not invent work hours, health targets or personal preferences to fill an empty screen.

Keep three kinds of context distinct:

1. **Profile:** explicit preferences such as concise answers, name, timezone and notification choices.
2. **Responsibilities:** goals or recurring work the user assigned, with a scope, sources, permitted actions, stop condition and next review.
3. **Working context:** short-lived source material needed for the active request. Fetch it again when freshness matters rather than accumulating an inbox or health-record mirror.

User-supplied durable memory belongs in bounded tables inside the existing ignored private voice SQLite file, rather than an unbounded transcript/vector store. Proposed initial limits are 200 profile facts and 100 active responsibilities. Store provenance, last revision and whether a fact is explicit or a proposed inference. Automatically save explicit “remember” requests; offer inferred preferences for review before making them durable. Retrieved email, event, cell and health text cannot rewrite the profile or permission policy.

Expose “What do you remember?”, edit, forget, clear and export controls to the loopback owner. Forgetting a fact must remove it from retrieval, task notes and reusable summaries; do not promise deletion from third-party providers or already-sent messages. Existing bounded conversation retention remains separate from long-term profile facts. Do not indefinitely preserve Google-derived payloads or summaries by putting them in memory: apply provider retention rules, minimize stored text and keep links/identifiers where appropriate. [Workspace data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy).

The identity/voice and the profile are also separate. Personalization changes how Jarvis helps the user; it need not replace the installed synthetic voice or alter the saved introduction. Keep occasional “sir” and understated wit configurable. Speak brief results while showing richer source-linked details in the dashboard.

## Connections and Google authorization

Reuse the **More → Connections** direction already recorded in [the Android plan](ANDROID_APP_SPEC.md). Calendar, Gmail, Sheets and Google Health are Windows backend adapters; Google Home remains a separate native Android SDK project. Connecting a Google account to this local app is separate from connecting a plugin to Codex/ChatGPT.

Use one visible Google account connection with per-service capabilities and actual granted permissions. Start with one Google account; bind tokens to its verified identity and never mix old-account caches or pending actions after account switching. Support partial consent, reconnect, expired/revoked grants and disconnected services. A completed account picker is not proof the relevant API works.

For the Windows installation, prototype a **Desktop OAuth client** with PKCE, an unpredictable single-use state and a short-lived callback bound only to 127.0.0.1 on an OS-assigned port. This is a dedicated authorization receiver, with no dashboard/data/control routes; do not put OAuth on the public certificate listener or expose a callback on the LAN. Dashboard HTTPS/WSS stays on 18761 and public certificate setup stays on 18760. Start the flow only from an authenticated direct-loopback owner action, expire it on cancellation/timeout and close the receiver when finished. Tokens are never dashboard cookies.

Google documents installed-app loopback redirects and PKCE, but **does not support incremental authorization for installed apps**. Adding a service must explicitly reauthorize the complete selected scope set and reconcile the scopes actually granted; do not promise seamless incremental consent. Google Health's setup examples use a Web Server client, so validate Desktop-client compatibility with the real Health API project before claiming one shared client works for all four services. If that gate fails, record the required separate client/redirect design before implementation. Google sign-in must use an external system browser, never an embedded WebView. [Installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [Health account setup](https://developers.google.com/health/setup).

Encrypt OAuth credentials and refresh tokens with Windows user-scoped DPAPI under the existing ACL-protected `.state/private/` directory. Keep access tokens short-lived in memory, send them only in authorization headers to fixed provider hosts and never expose them to the model, frontend, logs or Git. Owner-only connection management includes disconnect and deletion. Distinguish local disabling from provider grant revocation; revoking a shared Google grant can affect every connected service.

## Calendar capabilities

Read calendars and events, resolve availability, detect conflicts, and create, update or delete events. Preserve timezones, all-day dates, recurrence and exceptions. Show the chosen calendar and exact event time before an ambiguous request can become a write. Adding attendees or changing notification behavior is an explicit part of the action, not a hidden side effect.

Use the calendar-list read scope for selection, event-read scope for an initial read milestone and `calendar.events` when event management is implemented. Broader calendar ownership/sharing management requires the separate calendar scopes and an actual implemented feature; full event management does not require blanket calendar administration. Google offers narrower owned-calendar scopes if the user later limits access. [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth).

Typed operations: list calendars, list events, check availability, prepare event change and apply event change. Resolve calendar/event IDs server-side; event descriptions are untrusted content. Use event revisions/ETags to reject stale changes. Inserts need a stable operation identity so a lost reply cannot create duplicate appointments. API success is reported as “Meeting added for Thursday at three”; an unknown timeout is “I couldn't confirm the result” until reconciliation.

## Gmail capabilities

Search and read messages/threads, summarize, compose replies, manage drafts, send, label, archive, mark read/unread and move items to trash. Use `gmail.readonly` for the first read milestone and `gmail.modify` for this full mailbox-management feature set. `gmail.send` supports sending-only configurations. `gmail.compose` is also a restricted scope; creating a Gmail draft is not automatically a low-permission operation. Avoid `https://mail.google.com/` unless immediate permanent deletion is explicitly implemented; trash meets normal deletion needs. [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes).

Bound searches and body retrieval; do not ingest the entire mailbox by default. Resolve a reply against a returned thread/message ID and validate recipients, headers and attachment policy. Messages and signatures can contain hostile instructions; they never authorize forwarding, sending or fetching their links. Implement text-only sending first; attachment access is separate scope and validation work.

Sending follows the user's configured policy and actual instruction. An explicit complete send request can authorize its concrete message; a request to draft authorizes drafting. When the agent generates unspecified wording, recipients or a proactive message, finish the concrete preview before asking for a decision. Support specific standing rules instead of forcing the same question for every routine action. Broad account consent alone is not an instruction to message people. Duplicate prevention and uncertain-send reconciliation must survive process restarts; never blindly resend after a network timeout.

Gmail read/modify scopes are restricted. Google documents a personal-use verification exception, but OAuth Testing grants generally expire after seven days. A public distribution or transmitting restricted data through a third-party service requires a separate verification/policy assessment; don't assume the public GitHub repository or personal-use exception settles every deployment. The assistant must disclose any source text sent to its model for an answer, with user control and a provider-compatible data policy. [Verification exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification), [Testing token lifetime](https://support.google.com/cloud/answer/15549945?hl=en).

## Sheets capabilities

Read ranges, find rows, append entries, update cells, manage tabs and create spreadsheets. For the user's requested full Sheets content access, `spreadsheets` supports the read/write/create milestone. If access is later limited to files explicitly selected or created with Jarvis, use Google's recommended `drive.file` approach and implement a real selection/grant flow; pasting an arbitrary spreadsheet ID does not grant per-file access. Sheets permissions cannot be limited to an individual tab by OAuth alone. File sharing/deletion and broad Drive browsing are separate Drive features, not hidden consequences of adding cell editing. [Sheets scopes](https://developers.google.com/workspace/sheets/api/scopes).

Initially the owner registers spreadsheet links and friendly names. Discovery of every spreadsheet can later add an appropriate metadata scope and a filtered Drive listing; do not request full Drive access merely to find sheets. Only the backend resolves registered IDs and bounded A1 ranges. Validate headers, row shapes, allowed types and requested transformations. Default supplied text to RAW to avoid accidentally executing spreadsheet formulas; formula entry must be explicit. Include the changed range and before/after preview for broad edits. Sheets lacks a general exactly-once append guarantee: use an operation-ID column in Jarvis-managed logs or reconcile before retrying.

## Google Health: intended route and access gate

The user specifically selected **Google Health API with Google account sign-in**. Google announced the Fitbit app transition to Google Health and a migration path for Google Fit users. This does not mean every Fit record or every Google Health app feature is automatically exposed through the API. [Google Health announcement](https://blog.google/products-and-platforms/products/google-health/google-health-app/).

As checked on 2026-10-04, the official Health API pages say **new projects are not currently being onboarded**. Legacy Fitbit Web API support ended September 30 and shutdown is scheduled for October 30, 2026. Do not build a new dependency on the legacy Fitbit or Fit REST APIs. Gate this integration on actual project enablement, OAuth consent and a successful read of the user's data. [Current API availability](https://developers.google.com/health), [Health setup](https://developers.google.com/health/setup).

The Google account must first have an active Google Health profile linked through the mobile app. Google OAuth success alone cannot establish that profile. The first milestone should verify profile access and available data before scheduling any background reads. [Profile prerequisite](https://developers.google.com/health/setup).

Start with activity, sleep and supported health measurements, using the documented category scopes such as `googlehealth.activity_and_fitness.readonly`, `googlehealth.sleep.readonly` and `googlehealth.health_metrics_and_measurements.readonly`. Add corresponding write scopes only alongside implemented data-type write operations. Full access cannot create update/delete methods the API does not expose for a particular record type. Display source, units, interval/timezone, last sync and missing data honestly; never represent a cloud-sync gap as zero steps or a live measurement. [Data types and supported operations](https://developers.google.com/health/data-types).

Build a useful Health view for sleep/activity trends and user-requested journaling; health access needs a visible health/fitness feature, clear disclosure and controlled third-party use. Keep raw data out of logs and general permanent memory, and apply opt-in model processing for health summaries. No diagnosing, treatment decisions or fabricated targets. [Health developer/data policy](https://developers.google.com/health/policies/health-api-developer-user-data-policy).

If project access is unavailable, retain an accurate unavailable status in the plan and ship the other services independently. Health Connect on Android is a possible separately chosen fallback, requiring a native app on the device with the records; it is not a Windows cloud API and is not silently substituted. [Fit migration paths](https://developer.android.com/health-and-fitness/health-connect/migration/fit).

## Agent, jobs and action execution

Keep the optional voice process as an input/output channel. Add a separate opt-in assistant worker so durable jobs can continue while a voice turn is idle; microphone listening remains off at server startup. The worker's enabled state and permissions are visible and independent from the microphone switch. Server lock stops personal speech and interactive writes; explicitly configured read-only background checks may continue only under their separate background policy.

Use a planner that receives bounded relevant memory and selected tool results, and an executor that independently validates operations. Do not solve workflow limits by blindly raising the current four-step runner budget or adding generic API/HTTP/shell tools. Preserve the existing one-physical-PC-control limit. Google workflows get separate bounded read/write budgets, deadlines and a cancellation generation, with a persisted ledger of operations.

Proposed task states: planned, running, waiting for input, completed, failed, outcome unknown, paused and cancelled. Track provider resource IDs/revisions, the exact proposed payload, consent/policy revision and a stable operation ID. Pausing/disconnecting/locking invalidates pending authorizations before each mutation. A completed action isn't replayed because its model reply or audio fails. Cross-service work is not atomic: surface partial completion rather than “undoing” unrelated writes automatically.

Typed tools should be small and service-specific, with bounded arguments. Separate preparation from application for ambiguous or generated changes. Bind an approval to the payload hash, target account, operation type and expiry; any changed recipient/time/cell range needs a new decision. The model cannot create its own grant, approve itself or let retrieved content define tool names/endpoints. Policy decisions must be enforced in the parent/executor, not only in the prompt.

Add durable local jobs for assigned responsibilities. Start with bounded polling and provider change tokens where available. Cloud webhooks generally need reachable infrastructure; a private LAN dashboard is not automatically a callback target. Do not expose the dashboard to the internet to add notifications. Rate limits, quota failures, backoff, freshness and deduplication belong in adapters.

Each job has explicit sources, cadence/event criteria, timezone, quiet hours, budget, allowed operations and an end/review condition. Notify on meaningful changes, completion, failure or a decision; keep unchanged checks quiet. Scheduling one job does not enable unlimited monitoring of every connected account. Closing a browser does not cancel assigned background work; stopping the assistant or responsibility does. Show “Nothing scheduled” honestly when appropriate.

## Runtime and storage boundaries

The first version runs on the Windows PC. Background work stops when the PC is off or asleep, and the dashboard still needs the laptop. Muse and dots have cloud execution; reproducing that availability requires a later always-on host/cloud design with its own credentials, data policy and deployment decision. Do not promise 24/7 availability or remote access from the current LAN setup.

Use the existing DPAPI/ACL primitives for credentials. Keep durable task metadata, policy revisions and operation ledger in ignored private state. Personal-data caches should be in memory or short-lived with explicit expiry. Store minimal redacted action metadata instead of copying messages/events/health payloads into logs. Limit the fields sent to the cloud model to what the current request needs, with an in-context disclosure of that processing. Provider policies also cover derived data; encryption alone does not authorize indefinite retention.

Existing approved browsers should not automatically receive every connected inbox or health record. Separate dashboard approval from owner-authorized access to personal assistant content. Owner connection/permission/memory management stays direct-loopback-only. The owner can explicitly allow selected approved devices to read personal views or approve concrete actions; guest/ordinary telemetry displays receive only non-sensitive status. Revocation stops their subscriptions and pending actions without resetting other devices or CA trust.

## Interface

Keep the current desk-display composition. More holds Connections, Personalization, Responsibilities and Activity. Conversation supports both text and optional voice, backed by the same task/profile state. Home can surface a compact, explicitly enabled daily briefing; do not turn it into an always-visible grid of provider widgets. Health/agenda detail gets its own clear screen only when its adapter works.

Activity distinguishes an operation actually applied from a draft, pending decision or uncertain provider result. Include relevant source links, timestamps and a concise reason for a suggestion. Account setup errors should explain the next user step without exposing tokens or internal exceptions. Approval previews use readable touch targets and show the real recipient/time/range; detailed provider configuration stays in More.

## Implementation sequence

1. **Foundation and first useful agenda:** Connections, owner-only OAuth/DPAPI storage, actual scopes/account identity, Calendar read and “Brief me for today”; include the minimal personalization profile and separate assistant enable/stop controls. Validate real consent before claiming connectivity.
2. **Personal context and responsibilities:** editable memory, forget semantics, durable bounded jobs, activity, quiet hours, budgets and local-PC availability. Prove a responsibility survives restart without replaying actions or automatically enabling a microphone.
3. **Calendar writes and Sheets:** typed prepare/apply flow, scoped standing policies, stale-change protection, operation ledger, exact timezone handling, registered spreadsheets and duplicate-safe expense logging.
4. **Gmail management:** bounded search/read, disclosure/model data handling, replies/drafts/send, labels/archive/trash, payload-bound decisions and ambiguous-send reconciliation. No automated live email sends during QA.
5. **Google Health:** perform the project/profile compatibility gate in parallel with earlier planning; implement supported read/write data types only once actual API access works. Keep Calendar/Gmail/Sheets shipping independent of onboarding availability.
6. **Broader agent behavior:** combine services into responsibilities, tune model planning/latency/cost with evaluations, add relevant proactive suggestions, and assess optional always-on hosting or the separately planned Android shell. Browser automation, purchases and arbitrary local commands are separate capability decisions, not implicit additions.

Every milestone uses a feature branch/PR, updated how-tos and validation notes. Leave merges to the human owner unless a specific PR is explicitly authorized.

## Validation gates and setup information

Automated checks must cover owner/origin/device boundaries, OAuth state/PKCE/expiry/replay/partial scopes, token redaction and DPAPI failures, account switching, cancellation, prompt injection from each provider, strict tool arguments, operation deduplication, stale writes, recurrence/DST, Sheets formula handling, Gmail MIME/recipients, offline/quota failures, retention/forget and background quiet hours. Use mocked provider writes and fresh QA browser credentials; never delete or revoke the owner's data/grants as a test shortcut.

For real acceptance, connect the user's chosen Google account, perform an authorized bounded read per service, verify exactly the requested write against an explicitly selected test resource, and confirm stop/disconnect behavior. OAuth scope consent is required in Google's browser flow; repository planning cannot substitute for it. Health acceptance also needs actual records, an active Google Health profile and enabled project access. Report physical voice/tablet behavior separately from provider and browser checks.

Before the first runtime build reaches account connection, obtain a Google Cloud project and OAuth client configured for this personal app; enable Calendar, Gmail and Sheets, and determine whether Google Health can be enabled for that project. Keep downloaded client configuration private, outside Git. Google credentials/passwords must not be pasted into conversation. No account has been connected or private provider data accessed during this research.
