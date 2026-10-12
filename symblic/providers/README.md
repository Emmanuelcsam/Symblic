# symblic/providers: how an `ask` reaches a model

The kernel never talks to a model itself. For every model call the interpreter (`symblic/kernel/run.py`) hands
an **applicators object** one request and expects one reply. Any object with a `call(request) -> reply` method
works. This package ships one, `Applicators`, which needs only this repository and the Python standard library,
plus the pieces around it.

| Module | What it does |
| --- | --- |
| `applicators.py` | `Applicators`: runs `ollama:`, `command:` and `fake` applicator specs. Also `FakeApplicators`, configuration helpers, cancellation, and `python3 -m symblic.providers.applicators [--probe]` to show what your configuration reaches. |
| `ollama_call.py` | Which model weights answered an Ollama call: reads the server's model list before and after the request and turns that into a checked `model_identity` record. Also parses Ollama's token and time counters (`usage`). |
| `agent_teams.py` | Team profiles: a fixed list of members (applicators with a role and instructions) that each answer the same statement, lowered into ordinary Symblic votes. |

## Applicator specs

A program names who answers an ask with `by=`, for one ask or as a default:

```
use by="ollama:qwen3:4b".
ask n: Int "How many legs has a spider?" by "ollama:qwen3:4b@gpu" with effort=low
ask d: Text "Summarise the passage." by ["ollama:qwen3:4b", "command:my-agent"]
```

The general form is `engine[:model][@node][+effort][*weight]` (parsed by
`symblic.kernel.language.parse_applicator`). The shipped `Applicators` understands three engines:

### `ollama:MODEL[@HOST[:PORT]]`

One `POST /api/generate` to an [Ollama](https://github.com/ollama/ollama) server over HTTP (`stream: false`).

- `MODEL` is the exact Ollama model name, for example `qwen3:4b` or `llama3.2:1b`.
- `@HOST[:PORT]` picks the server, by the name you gave it in `SYMBLIC_OLLAMA_HOSTS` or by its `host:port`
  (port 11434 when omitted). Only servers listed in `SYMBLIC_OLLAMA_HOSTS` are ever contacted; any other
  `@HOST` is refused. Without `@HOST` the call goes to a listed server whose model list contains `MODEL`
  (the one with the fewest calls in flight from this process), or to the first listed server.
- The answer's JSON Schema is sent as Ollama's `format`, so decoding is constrained by a grammar. The schema is
  narrowed to what Ollama can express (`ollama_format`); a schema it cannot express is refused before any call.
- `temperature` and `seed` come from the request (the kernel sets them per sample and per retry).
- `num_ctx` (the context window) is sized to the prompt plus room for the reply, because Ollama silently cuts a
  prompt that does not fit. A prompt too large for the largest allowed window is refused instead.
- Before and after the request the server's `/api/tags` is read. The reply's `model_identity` says which
  manifest digest the server listed for the model at both reads (`observed`), that the listing changed during
  the call (`drift`), or why nothing could be observed (`unavailable`). This is what the server reported, not a
  cryptographic attestation of the weights it ran (see `ollama_call.py`).
- If the model is not installed on that server, or the server does not answer the listing, the call is refused
  before any generation, and the run gets the call back in its budget.

### `command:NAME`

Runs a local program you configured, for example a command-line coding agent:

```
export SYMBLIC_COMMAND_MY_AGENT='my-agent --print --no-color'
```

then `by="command:my-agent"`. `NAME` is upper-cased and every character other than a letter or digit becomes `_`
to find the variable. The command line is split like a shell would split it (Python's `shlex`) but never run
through a shell. **A name with no such variable is refused**: a program can never choose an arbitrary
executable.

What the command gets:

- **stdin**: the system text, a blank line, then the prompt. The prompt already ends with the exact answer
  format the kernel expects (a JSON object, or a fenced code block for `Code` answers).
- **environment**: yours, plus `SYMBLIC_SCHEMA_FILE` (a file holding the answer's JSON Schema, for tools that can
  enforce structured output), `SYMBLIC_EFFORT` (the requested effort word, possibly empty) and
  `SYMBLIC_COMMAND_NAME`.
- **working directory**: a fresh, empty temporary directory, deleted afterwards.

Exit status 0 means success, and stdout is the answer; anything else is a failed call whose message includes
the end of stderr. The call is bounded by `SYMBLIC_CALL_WALL_S`; on timeout, stop or cancellation the whole
process group is terminated. Remember that a command such as a coding-agent CLI may send the prompt to a cloud
service; that is why `command` does not count as a local applicator for local-only routing.

### `fake[:LABEL]`

Scripted answers for tests and dry runs: no model, no network, no process.

```python
from symblic.providers.applicators import Applicators, FakeApplicators
apps = Applicators(fake=FakeApplicators({'answer': 4}, by_label={'fake:b': lambda label, prompt, req: {'answer': 5}}))
```

Without a `fake=` argument every `fake` call fails on purpose (`by="fake:none"` therefore runs only the kernel).

### Everything else

`kernel` never answers an ask. The other engine names the language knows (`claude`, `codex`, `agy`, `mistral`,
`copilot`, `gemini`, `chatgpt`, `council`) are labels for model families and agent tools; the shipped
`Applicators` refuses them with a hint to configure the tool as `command:NAME`, or to pass your own
applicators object. They remain valid in programs because model lineage (which maker trained a model) is read
from these labels when votes count independent model families.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `SYMBLIC_OLLAMA_HOSTS` | `127.0.0.1:11434` | Comma-separated Ollama servers, each `[name=][http(s)://]host[:port]`. Example: `127.0.0.1:11434,gpu=192.0.2.10:11434`. |
| `SYMBLIC_COMMAND_<NAME>` | (none) | The command line for `command:<name>`. |
| `SYMBLIC_CALL_WALL_S` | `1800` | The longest one call may take, in seconds. |
| `SYMBLIC_OLLAMA_MAX_CTX` | `32768` | The largest context window (`num_ctx`) a call may ask for. |
| `SYMBLIC_OLLAMA_KEEP_ALIVE` | (not sent) | Sent as Ollama's `keep_alive` (`0` unloads the model after each call). |

Settings are read when an `Applicators` object is made (pass `environ={...}` to use other values). A malformed
setting raises `ConfigError` at once instead of being ignored. Environment proxies are not used and HTTP
redirects are not followed.

## The request and the reply

A request is a dict with `app` (the parsed spec), `system`, `prompt`, `schema`, `sample`, `temperature`, `seed`,
`effort`, `tools`, `key` (the call's hash), `stop` (a `threading.Event`), `context_manifest`, and optionally
`ollama_limits` (`num_predict`, `num_ctx`, `timeout_seconds`) and `deadline` (an absolute `time.time()` for the
run's total Ollama budget).

A reply is a dict with `ok`, and then `json` and/or `text` (the answer), or `error`; `fatal` (a retry cannot
help), `refused` (no model saw the prompt, so the call does not count against the budget), `ms`, `node`,
`model`, `usage` (only what the provider reported) and `model_identity`.

To use any other provider, write a class with `call(self, request) -> reply` that follows this contract and pass
an instance to `Run(..., applicators=...)` (see `symblic/kernel/embed.py`).

## What is not here

The private system Symblic was developed in placed calls across a cluster of machines, waited for capacity,
watched temperatures and memory, reached browser-based chat services and ran multi-agent councils. Those parts
belonged to that host, used its private services, and are not included. `Applicators` accepts the old keyword
arguments `thermal`, `allow_web` and `avoid` so older callers keep working, but they change nothing.

`agent_teams.py` still describes a `project` lane and a capability catalogue for teams of coding agents run by an
agent hub; this repository ships no such hub, so those parts only validate data.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/providers -t .
```

The Ollama tests run against a small fake Ollama server the test starts on `127.0.0.1`, and the command tests
run a short Python script; no model and no external network are used.
