# ChatGPT and Gemini as typed browser providers

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

Symblic's checked asks and Forge's proposal teams can select ChatGPT web or
Gemini web on a registered device. Choose the engine, exact model or mode, and
node in the team controls. An empty model explicitly uses that account's
default. Selection does not sign in, install a runtime, or silently move the
request to another node. The [terminal guide](TERMINAL.md) covers the separate
project-agent workflow; [Forge](FORGE.md) covers operator review of proposals.

## Readiness and identity

Four facts remain distinct:

| Fact | What establishes it |
| --- | --- |
| Registered placement | The current agent/team catalogue exposes the engine and node. |
| Installed protocol | The selected node's installed browser module exposes typed-proposal v1 and the controller's exact combined source hash. |
| Loaded protocol | A running daemon advertises its import-time source hash, which must match the installed module and controller. Copying files does not update that daemon. |
| Account readiness | The chosen site is signed in on that device and permits the requested model or mode. An installed or running browser alone does not establish this. |

Gemini requires an exact enabled picker mode and verifies the visible active
selection before sending. ChatGPT requires the exact requested slug in the
authenticated account's model catalogue and records that request. The latter
does not expose an independently verified serving-model digest. Receipts retain
requested node/model and selection evidence separately; these are not a claim
that distinct selections imply independent models. Browser providers have no
separate supported effort knob; choose an exposed model or mode instead.

Runtime updates use the existing admitted **Browser → Machine → Install** path.
An update requires a positively idle/stopped runtime, no active web agent and
no unresolved browser or install hold. Unknown or busy runtimes stay untouched.
The source transfer includes both `chatgpt.js` and `typed-requests.cjs`. The operator
must sign in on a device whose account is not ready. The integration never copies
credentials or profiles. Verification may inspect installed metadata without
starting a browser or making a provider call.

Linux ARM64 nodes use native distribution Chromium when branded Chrome is not
installed; the installer does not send an amd64 Chrome package to those nodes.
Existing native Chromium is reused, with only missing runtime dependencies
installed. Browser source compatibility and account readiness still require
their separate checks; a successful install is not a successful provider answer.

## Exact request and fresh context

`symblic.providers.applicators.Applicators._web` calls `integration.host.symblic_web`, which records intent before
using the existing registered node-browser admission and node-local CLI. This
does not add a public ask relay or a new SSH dispatch path. The sign-in relay
continues to exclude `/ask`.

The typed-v1 start record contains only an exact request ID, site, model and full
prompt. Full prompt includes the supplied system/profile, instruction and
declared response schema. It is limited to 100,000 UTF-16 code units and is
refused rather than truncated. Every new request opens a fresh owned window;
ChatGPT uses a temporary conversation. No prior transcript, upload, existing
chat URL, shell command, file edit or coding-agent tool is admitted by this lane.
An output mentioning a command remains text. Checked asks still require their
native type/predicate checks. Forge output stays proposed until explicit
operator adoption and acceptance; a browser answer does not execute a project.

## Reconnect, cancellation and accounting

The host retains a private ledger under the existing denied `agents_data/`
store, in `typed-browser/`. Each node retains private request receipts under its
browser state directory, normally
`~/.local/share/dashboard-chatgpt/typed-requests/`. Intent and receipts use atomic
durable writes. No token or account profile is included in those receipts.

A repeated exact request observes the original ID; a changed payload with that
ID refuses. A lost acknowledgement or daemon restart leaves unfinished work
unknown. Reconnect polls the retained request and never submits it again.
Historical receipts whose source hash differs from the current protocol cannot
be adopted as current-protocol results, including through a host cache.

Cancel addresses only the exact ID/hash and its owned window. Confirmed window
closure does not prove provider-side cancellation or completion. A failed poll
or cancel remains unknown even if an authentication layer returns a generic
rejection. Only a proven initial pre-dispatch refusal is marked non-admitted and
refunded from the native model-call budget. Uncertain dispatches retain their
charge.

The existing whole-browser hold survives individual request success, failure or
cancellation. Only the normal reconciliation path, with stopped daemon, unit
and process/cgroup evidence, releases it. A connection error is not evidence
that a provider or browser stopped.

## Verification scope

`tests/integration/test_symblic_web.py` uses temporary ledgers and fake transports, including
a real native `Run` through `Applicators`, to check exact selection, fresh
requests, durable no-replay, cancellation, source drift, legacy host-effort
compatibility and refusal accounting. The browser's
`test/typed-requests.test.mjs` exercises private receipts and the actual CLI
against a fake loopback daemon, plus exact model-selection fixtures. These
establish adapter behavior without real account or model calls. Installed
metadata, loaded-daemon verification and any real provider result must be
reported separately.
