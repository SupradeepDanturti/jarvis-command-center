# Personal assistant foundation

Implementation record · 2026-10-04

This is the first runnable slice of [the personal assistant plan](PERSONAL_ASSISTANT_PLAN.md): Google installed-app OAuth, owner-only primary-calendar reads, editable briefing preferences, and an account-access switch separate from the microphone. Discoverable/full-file Sheets access, reviewed RAW updates, bounded facts and opt-in voice tools now extend this slice; see [personal tools and memory](ASSISTANT_TOOLS_MEMORY.md). Calendar writes/selection, Gmail, Health, background responsibilities and specialist delegation remain future milestones.

## Set up Google on the PC

1. Update normal dependencies with the README procedure, including the pinned Windows timezone database.
2. Open **https://localhost:18761** in the approved owner browser; choose **More → Connections**.
3. In [Google Cloud Console](https://console.cloud.google.com/), create/select a project and enable the **Google Calendar API**, **Google Sheets API** and **Google Drive API** (for spreadsheet discovery).
4. Configure **Google Auth Platform → Branding** and **Audience**. For personal testing, add your Google account as a test user. Organization policies may constrain available clients/accounts.
5. Under **Clients**, create an OAuth client with application type **Desktop app** and download its JSON. A web client, API key or service-account JSON is not accepted. Keep the downloaded original private and out of Git.
6. Expand **Set up Google access** in Connections and choose that JSON. Only the required installed-client values are encrypted; caller endpoint/redirect metadata is discarded. Reimporting replaces the client and disconnects the previous local account.
7. Select **Enable assistant**, then **Connect Google**. Allow the new tab, choose your account and grant Calendar, Sheets and Drive metadata access. Existing connections need one reconnect for the added permission, using the saved client. Return to Jarvis after sign-in to see the verified account and outcome.
8. Set your form of address, city timezone (for example `America/Toronto`) and briefing style in **More → Personalization**. These affect the agenda briefing; they also personalize voice replies when personal-context consent is enabled in Memory.
9. Select **More → Today → Brief me for today**. It fetches primary-calendar events overlapping the current day in your saved timezone. Google expands recurring events. All-day end dates remain exclusive. At most 100 events are fetched once; pagination or malformed time records produce an explicit partial-agenda warning.

External OAuth apps in Testing normally have seven-day authorizations/refresh tokens for Calendar scopes. Reconnect when expired. Publishing an app or broadening scopes has separate verification/policy requirements; this build does not publish or verify a Google Cloud app. [Testing rules](https://support.google.com/cloud/answer/15549945?hl=en), [installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [Calendar quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python).

The access switch always starts off after a server restart. Enabling it does not start a microphone, worker job or schedule. Stopping it invalidates pending operations and clears the access token; saved account authorization remains for a later explicit enable. Personal views currently require the approved direct-loopback owner. Tablet telemetry approval does not grant personal-data access.

**Disconnect from this PC** deletes local account tokens and retains the encrypted client. **Remove saved client and connection** deletes the encrypted file. Both cancel pending consent/read operations. Neither revokes Google's grant; remove Jarvis in [Google account connections](https://myaccount.google.com/connections) to revoke it too. Revoking a grant can affect other services authorized through the same OAuth client.

## Harness and context

All agent orchestration, tool definitions, provider operations, profile access and persona prompts live in `backend/agent/`. The optional SDK still loads only inside the enabled isolated voice worker. Audio capture, physical device adapters and dashboard transport stay separate.

- `voice_agent.py`, `voice_actions.py`, `jarvis_prompt.txt`, `jarvis_intro.txt`: existing bounded voice runner, typed desktop tools and persona, relocated together.
- `google.py`: fixed Google token, user-info, primary-calendar, Sheets values/metadata and spreadsheet-only Drive search operations; no caller URL/header API, redirects, proxy inheritance or retries.
- `service.py`: encrypted connection store, PKCE/state receiver, account generation, cancellation, read budget and deterministic agenda briefing.
- `profile.py`: bounded owner-authored address/timezone/style in one private SQLite row.
- `routes.py`: HTTPS/owner checks, same-origin mutations, redacted validation and late revocation checks.

The planned main Jarvis agent owns conversation and coordination. Specialists get explicit assignments, relevant selected profile/facts and source results, deadlines, budgets and permission envelopes. They keep their own task context and return bounded summaries, evidence, pending decisions and proposed memory changes. They do not inherit every conversation or credential, or write authoritative permission grants. The main agent/executor verifies completion and commits allowed updates. Simple commands remain in a single runner.

Keep four distinct kinds of information: editable durable profile/facts; bounded conversation context; task-local notes/checkpoints; and the permission/action ledger. A shared durable store is not a shared unlimited prompt. Secrets remain in the executor vault. Provider content is untrusted data and requires retention/consent handling rather than automatic promotion into permanent memory.

Public dots documentation describes parallel delegation, selected task context, relevant ChatGPT memory and separate persistent notes; it does not specify a note-file layout. Muse documents a main chat, side chats, editable memory files and a separate Sentinel action/credential boundary, but not its full context-sharing algorithm. These inform the design, rather than establishing identical internals. [dots context and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory), [Muse design](https://introducing.muse.ai/), [Muse security](https://research.meta.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse).

## Privacy and acceptance

Installed-client values and refresh tokens are user-scoped DPAPI ciphertext in ignored `.state/private/voice/google.dpapi`; access tokens are memory-only. Preferences occupy a separate row in the existing ACL-protected voice `history.sqlite3`. Clearing voice history does not erase preferences; **Forget preferences** deletes only that row. Dashboard provider reads remain transient and do not make model calls. The opt-in voice extension sends requested results and selected facts to OpenAI; its personal replies are retained in bounded owner-only conversation history. See [tools and memory privacy](ASSISTANT_TOOLS_MEMORY.md).

Consent uses external Google sign-in, S256 PKCE, single-use random state and the complete implemented scope set (`openid`, `email`, `calendar.events.readonly`, `spreadsheets`). The receiver binds only `127.0.0.1` on an OS-assigned port; it closes after completion, cancel, lock, revoked owner approval or five minutes. It uses neither dashboard port nor an embedded sign-in view. Installed-app incremental authorization is not used. Actual granted scopes are recorded; partial grants cannot enable Calendar. Google's authenticated user-info endpoint supplies a verified email and stable subject; switching accounts invalidates earlier operations/tokens.

Automated tests mock Google transport and also exercise a real local consent receiver. Browser QA uses trusted HTTPS/fresh profiles, mocks every Google/account write and revokes only its own browser. The owner reports the Google connection works. A live Calendar agenda read, Sheets re-consent/write and physical voice personalization are not independently confirmed by these automated checks. Physical tablet, lock-screen transitions, audio/desktop controls and background jobs are not newly validated by these checks. Google Health onboarding and Desktop-client compatibility remain a separate gate.
