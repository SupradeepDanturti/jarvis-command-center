# Personal tools and memory

Implementation record · 2026-10-04 · extends [the assistant foundation](ASSISTANT_FOUNDATION.md).

## Enable Sheets

1. In your existing Google Cloud project, enable the **Google Sheets API**.
2. On the approved PC browser at **https://localhost:18761**, open **More → Connections**. Enable assistant access and choose **Reconnect Google**, granting Calendar and Sheets access. Reuse the saved Desktop client; no new JSON is needed. Partial grants enable only the granted service.
3. Open **More → Sheets**. Register a friendly name, a Google Sheets link or ID, and a range such as `Sheet1!A1:D20`. Quoted tab names are supported. Up to twenty ranges per Google account are stored; each covers at most 100 rows, 20 columns and 1,000 cells.
4. Choose **Read range**. Edit individual cells, then **Preview change**. Check the sheet ID, target range, cell types and exact values before choosing **Apply these values**.

Google's `spreadsheets` scope grants spreadsheet-wide content access; Jarvis's executor separately limits tools to owner-registered ranges. Switching accounts hides the other account's registrations. Drive browsing, spreadsheet creation, append, tab management and evaluated formula entry are not implemented. [Scope boundaries](https://developers.google.com/workspace/sheets/api/scopes).

Updates start at the registered range's top-left cell and replace only supplied cells. RAW writes keep formula-looking strings literal. Multiline/tab-containing values are preserved in individual cell editors. Dashboard previews skip unedited cells, retaining their existing formulas and types. Numeric/boolean reads retain their types; select Text, Number or Yes/no when editing. Agent proposals use null to leave cells unchanged, following Google’s [ValueRange rules](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values). Previews last five minutes, stay in server memory, are consumed before dispatch and are discarded on stop, account/profile/memory/registration changes or restart. No automatic retry occurs. If a response fails after dispatch, the outcome is uncertain: check Google Sheets before preparing another change. Other editors may change the sheet after your read; this milestone does not claim compare-and-swap/ETag protection. [Read values](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/get), [update values](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/update).

## View and edit memory

Open **More → Memory** on the approved PC browser. Add a fact with **Remember this**, edit existing text with **Save changes**, approve/discard suggested facts, or **Forget** one. **Forget all saved facts** and **Clear conversation history** require a second confirming click. Preferences stay separate in **Personalization**. Personal edits stop the active voice session to remove stale context; enable listening again in **More → Jarvis** when ready.

Facts are bounded to 200 entries of 500 characters. Duplicates are reused; a full store refuses new facts instead of evicting unrelated ones. Common credential patterns are refused; do not save passwords, keys or provider records. Memory lives in private SQLite tables, rather than a plaintext prompt file. Use the UI instead of editing database files.

**Preferences and working context** shows preferences, current recent conversation and the exact last personal selection prepared before a voice turn. **Download memory and context** exports every fact/proposal plus these views to a personal JSON file, without OAuth/OpenAI credentials. Full retained conversation history is separately paginated on the Jarvis screen (up to 500 exchanges). The export is not a complete live tool transcript or hidden model reasoning.

Forgetting a fact removes it from future selection and stops the worker. Earlier conversations may still mention it until you explicitly clear history. Forgetting cannot retract previously sent model requests or alter Google data. The database uses SQLite secure deletion, within the existing private Windows ACL directory; the database itself is not DPAPI-encrypted.

## Let Jarvis use and add memory

Enable **Use personal context with Jarvis** in Memory after reading its disclosure. Saved consent starts off by default and is separate from the startup-off assistant and microphone switches. Selected facts, preferences and requested Calendar/Sheets results can then reach OpenAI for voice answers. Responses can include provider-derived information and join bounded private history. Personal exchanges/live reply text are visible only to the direct-loopback HTTPS owner, and are excluded from model context while assistant access or personal consent is off. Speech is audible near the PC; wake detection is not speaker authentication.

Say **“Jarvis, remember that I prefer morning meetings.”** The fixed parent saves the exact fact from the current transcript without an extra model interpretation. Inferred/rephrased facts use `remember_fact` to create pending proposals, excluded from retrieval until approved. Provider content is untrusted and is never automatically mirrored into facts.

Ask **“What do you remember about my meetings?”**, **“Brief me for today”**, or **“Read my Weekly tracker.”** Sheet edits use `propose_sheet_update`; review/apply them on the PC. Voice memory overwrite/deletion and unattended sheet writes are not implemented.

Each voice turn refreshes the last six eligible conversation exchanges and up to twenty facts selected by lexical relevance and recency. Pending proposals are excluded. The last selection is a transient server snapshot visible to the owner. `search_memory` retrieves other relevant saved facts on request. Context carries no Google tokens or client configuration. It is supplied as bounded data, not privileged model instructions. [Agent definitions and local context](https://developers.openai.com/api/docs/guides/agents/define-agents).

## Harness and limits

All harness additions are in `backend/agent/`: `memory.py`, `sheets.py`, `personal_tools.py`, plus existing service, routes, fixed Google adapter and voice runner. Audio/process transport remains outside that folder. SDK imports stay inside the isolated enabled voice worker.

Typed model tools are `calendar_today`, `list_sheets`, `read_sheet`, `propose_sheet_update`, `remember_fact` and `search_memory`. `assistant_context` is a worker-only request, outside the model's registry. SDK sheet discovery must precede a read/proposal. The four-step runner, physical-control limit and one-read budget remain bounded, with separate sheet-discovery/proposal and memory slots. No generic HTTP, shell, file tools, subagents or hidden memory stores are added.

Network reads run outside the voice cancellation lock and recheck assistant/worker generations, desktop lock, deadlines and consent before delivery. Local provider requests disable retries, redirects and proxy inheritance. Writes require same-origin HTTPS owner approval of one concrete preview and recheck authorization before dispatch. Account changes, personal edits and stop discard stale context/previews; already-dispatched Google writes cannot be recalled.

Saved facts, preference/consent rows and account-bound sheet registration metadata share ignored `.state/private/voice/history.sqlite3`. OAuth secrets stay in DPAPI ciphertext and access tokens stay in memory. Dashboard provider payloads and write previews are transient. No personal content enters localStorage, logs or Git. Consent explicitly governs sending account data to the voice model; dashboard reads alone never make a model call.

Gmail, Google Health onboarding, Calendar writes/selection, durable responsibilities and specialist delegation remain later milestones.

## Verification

Automated backend and fresh-browser QA use mocked Google/account/memory operations. They exercise memory bounds/persistence/retrieval, direct remember versus proposed facts, permission/account isolation, RAW values, preview expiry/consumption, uncertain outcomes/no retries, cancellation, redaction, owner-only personal conversation reads, safe rendering, and landscape/portrait/narrow layouts. Browser QA uses trusted certificates and revokes only its own credential.

The owner reports the earlier Google connection works. Live Sheets re-consent/read/write, physical microphone personalization and Windows lock transitions are not confirmed by automated checks. The existing connection and downloaded client have not been inspected through test tools.
