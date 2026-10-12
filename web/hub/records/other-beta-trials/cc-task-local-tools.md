Fix a production defect in the Symblic local-model lane (single file: src/agentcli-local.js).

DEFECT (observed live 2026-10-08): When the selected Ollama model does not support tool calling (observed with the deepseek-r1 family, e.g. deepseek-r1:7b), ensureAlias() creates and verifies the symblic-ctx8192 alias successfully, agentcli starts, and then EVERY LLM request fails at runtime with an Ollama 400: "registry.ollama.ai/library/symblic-ctx8192-<digest>:latest does not support tools". The session then sits wedged at an idle prompt with the error only in the scrolled terminal; the caller (Symblic task coordinator) sees the step as awaiting_review forever with no surfaced reason. Tool-capable models (qwen family, llama3.1, gemma3) work through the same path.

REQUIRED FIX: Refuse tool-less models at admission, before any alias use or inference. In ensureAlias(), after fetching /api/show for the SOURCE model (the alias verification already fetchies /api/show for the alias), inspect the show response for tool capability. Current Ollama /api/show returns a "capabilities" object with a boolean "tools" field. Rules:
1. If capabilities.tools is explicitly false, throw a clear, actionable error BEFORE creating or reusing the alias, e.g.: 'This model does not support tool calling; admitted local coding requires tool-calling models. Select a tool-capable model (for example a qwen2.5, qwen3 or llama3.1 tag).'
2. If the show response has no capabilities information at all (older Ollama), do NOT refuse: absent evidence must not break currently working models. Only a definite negative refuses.
3. The refusal must happen even when a ready alias receipt already exists (an existing alias of a tool-less model must not bypass the check), but the refusal must not delete or unload anything.
4. Preserve the existing receipt/verification/unload machinery exactly; this is an admission gate only. No changes to the 8192 context value, the guard, or unrelated behavior.
5. Keep the file's existing style (strict mode, no new dependencies beyond fs/os/path/crypto/child_process already imported, no network beyond the existing loopback Ollama requests).

DELIVERABLE: the patched agentcli-local.js (and check script only if applicable), with a short summary of the exact refusal condition and where it fires.
