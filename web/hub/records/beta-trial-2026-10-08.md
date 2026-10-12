# Symblic heavy beta trial — 2026-10-08

Task from the operator: heavy beta of symblic#english. Test 1: English-statements script recreates Obsidian graph view (all features + 3D animation) as subsite of /symblic-beta gallery. Test 2: Kirby moves with arrow keys + jump, all animations. Constraints: least statements possible, absolutely no code written by me; fixes go to statements or to symblic itself, NEVER to generated output; reproducible runs. Use Forge + Claude Cloud + AGY as consultants. Send link when done.

## Key facts discovered
- English page lane: POST /api/symblicos/tasks/start (owner gate = loopback request without a proxy-forwarding header, port 8080 on the host). Payload: client_request_id (stable id, letters/digits/._:- up to 160), instruction (<=60000 chars), mode 'lines' = fresh agent session per nonblank line (<=64 lines, shared workspace), options {engine, model, effort, node, cwd, auto (default true), worktree}, context_note (<=12000 chars, shared).
- GET /api/symblicos/tasks/get?id=... ; tasks/control {id, action}; workspace/create {name} -> /srv/symblic/projects/<name> (managed git, baseline commit).
- Engines on the host: agy (mode accept-edits, model gemini-3.8-flash-high), claude, codex, mistral, gpt, gemini, local(ollama). Yesterday: cloud CLIs quota-blocked (claude until Oct 10), agy was the only working engine.
- Node v22 at ~/.nvm/versions/node/v22.17.0/bin/node (node --check works).
- Beta findings to watch: T1 trust prompts stall auto tasks (auto-trust watcher broken for symblic agents + codex regex miss); T3 false success claims (verify on disk myself); T2 no completion evidence; T7 empty cwd.
- Graph view target: modelled on the publicly visible behaviour of Obsidian's graph view and its settings panel (center, repel and link forces, link distance, node size, arrows, text fade, highlight on hover, filters for attachments/unresolved/orphan notes, color groups, drag to pin; here: pin/unpin). *Edited for publication:* a note on how the agent inspected the installed app was removed.
- PRIVACY: vault note names are personal data. Generated app uses FICTIONAL dataset only (stated in statements + README).
- Page serving: new static page + assets dir must be registered via the host's page-registration script (nav row). Static pages live on write; Python changes restart-gated (restart the host dashboard, warn first).
- Forge API: /api/symblic-forge/ (project/create, action, coach/preview, coach/propose, handoff). Run lane: /api/automation/symblic/ forge/run uses Ollama only. I use Forge as consultant for the statement list.
- AGY CLI: ~/.local/bin/agy ; claude: ~/.local/bin/claude + bin/claude-cloud.

## Plan
1. Create workspaces beta-graphview + beta-kirby via API.
2. Forge: create project, coach critique of statement list.
3. Consult agy (and claude if quota allows) on statement ambiguity.
4. Run Test 1 (mode lines, engine agy, node the host, cwd beta-graphview). Poll. Verify on disk (node --check, page fetch, headless if possible). Fix statements on failure, rerun.
5. Run Test 2 (Kirby) same way.
6. Apply output into checkout (Agents Work review+apply flow as in prior beta), register page via the host's registration script, link from symblic-beta.html, verify live journey, send link.
7. Record findings (trust watcher fix if hit — allowed: fix symblic product code).

## Statement scripts (final drafts below; iterations noted in run log)
See beta-graphview.english.txt and beta-kirby.english.txt scratchpad files.
