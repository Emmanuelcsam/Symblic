# Declared JSON output shape

The implementation is checked with fake providers and isolated native execution. No model-quality improvement has been measured.

An explicit schema may be attached to the native Code JSON type:

```symblic
ask result: Code json schema "{\"type\":\"object\",\"properties\":{\"answer\":{\"type\":\"integer\"}},\"required\":[\"answer\"],\"additionalProperties\":false}" "Return answer as the integer one.".
```

The schema is a literal, not an interpolated prompt or file reference. This opt-in declaration requires one original JSON reply document. It preserves the exact reply text, including whitespace, Unicode spellings and numeric lexemes. It does not strip fences, unwrap an `answer` property, canonicalize strings or reconstruct text from a provider's parsed object. Ordinary `Code` and `Code json` retain their existing behavior.

The type is still a string value. Parsing and validating it does not execute its contents. A valid shape is not evidence that the answer is correct, that a proposed requirement matches the operator's intent, or that generated code is safe. MICA still applies its original objective/export/output/budget checks, proposal representation decoder, graph checks, sandboxed unit tests and independent original acceptance tests.

The finite schema subset supports primitive types, scalar constants/enums, closed object properties and required names, arrays with homogeneous items, string/item lengths, integer bounds and at most eight complete `anyOf` alternatives. Constants/enums may contain strings, booleans, null and bounded integer values. `{}` admits any bounded JSON value. References, patterns, unknown keywords, noninteger numeric schema bounds, conditional keywords and mixed properties/anyOf nodes are refused. `title` and `description` are nonbinding text annotations.

Schema admission is bounded to 32KiB, 16 schema levels and 4,096 schema nodes. Replies are bounded to 400,000 characters, 1.6MB UTF-8, 32 data levels, 50,000 values and 250,000 validation steps. Numeric tokens have a 1,236-character bound and a bounded decimal exponent. Resource exhaustion is an incomplete check: it is reported as resource/verification unknown, retains any already spent call and supplies no failed-quality observation or automatic repair opportunity. Malformed JSON or a completed negative shape check is a rejected candidate. Duplicate keys and invalid Unicode scalars are rejected.

The full declared schema enters the existing native capsule, context budget, provider request, call key and durable request journal before dispatch. Prompt display may factor identical schema subtrees into local `$defs` descriptions; the statement displays the schema hash. The actual provider receives the complete expanded schema, and the original budget counts that complete argument as well as all displayed text. No fallback removes a refused schema.

The current local Ollama adapter supplies its existing `format` argument. Tests inspect that adapter's pure planning seam with fake dependencies; no new provider client or authority store is added. Other providers' decoding support and real-model quality have not been established by these checks.

New MICA root asks use the existing version-3 proposal shape and original `expected_value` representation. Historical legacy proposal decoding and ordinary unstructured Code asks remain available. Graph grammar includes explicit complete variants for omitted assumptions, optional deterministic construction/version and module output paths; this avoids the existing adapter forcing optional fields to become required. Scoped refinement may omit wrapper examples because the host retains the original examples. It preserves optional unchanged assumptions and declared construction, including null; helper and final graph checks remain authoritative. An exhausted original unit budget refuses refinement before choosing or reserving a planner, with no added call or failed-quality observation.

New MICA requests that omit `context_chars` default to 32,768 characters, including the full schema cost. Explicit budgets and every already normalized/frozen 24,000- or 40,000-character request keep their original value; this does not change native language defaults or raise an existing run allowance. The default also participates in routing eligibility: a worker declaring less than 32,768 characters is ineligible for a new default request. An explicit smaller budget is usable only when the complete native capsule fits.

The parser policy and helper version are pinned through kernel/execution identity. MICA and Forge provenance include the helper source. Portable export derives the required closure from the execution registry. The conformance closure includes `symblic/kernel/json_schema.py`. Any future guest allowlist must include it when packaging this parser; old frozen guest/pilot releases are unchanged. This is a local source compatibility check, not security attestation.

The closure review also found that the existing optional JavaScript normalizer was not completely pinned by portable execution. The candidate registers its Python import identity and required source, includes its JavaScript asset in the process snapshot, and binds the Python/JavaScript/Acorn hashes into the kernel identity. Its normalization behavior and JavaScript bytes are unchanged. Fresh processes refuse old execution receipts after any of those executable bytes change. This intentionally changes kernel identity; historical read-only artifact behavior is unchanged, while execution/resume must use its original coherent runtime.
