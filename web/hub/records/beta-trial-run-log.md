# Beta trial FINAL state (2026-10-08 evening)

## Both tests completed and deployed
- GRAPH task-e84d63615eeffa5fb2800fd8c11ca529: all 8 steps completed. 8 statements -> 8 fresh AGY sessions, zero code from me.
- KIRBY run2 task-5a01358e3c72da875f5ca269dbc8fe0e: all 4 steps completed (run1 cancelled after agy dispatch 503 wedge).
- Workspaces: /srv/symblic/projects/beta-graphview (vault-data.js, graph-engine.js, graph-render.js, graph-input.js, graph-ui.js, index.html, verify.txt, README.md), /srv/symblic/projects/beta-kirby (kirby.html, kirby.js, verify.txt, README.md).

## Independent verification I ran (output untouched)
- Data: 80 notes/6 folders(min 13)/8 attachments/5 orphans(not attachments)/12 distinct unresolved/180 links/0 self-links.
- Engine behavior in node: all API, 200 nodes (80+12 ghosts+108 tag nodes), alpha freeze <0.01, reheat, pin/unpin semantics, positions schema.
- node --check all 6 JS files pass (matches agent-written verify.txt).
- Live headless chrome over HTTP: graph page renders (408 colors, WebGL2 context, no console errors); all 21 DOM feature checks PASS (panel, toggles, 5 force sliders, search, 4 filters, focus depth, both canvases, footer). Kirby page: pink body/red feet/sky/ground colors confirmed by pixel analysis; keyboard harness drives 82 frames through walk->friction->jump with zero exceptions; keydown/keyup/blur listeners present.
- Screenshots: /tmp/graphview-live.png, /tmp/kirby-live.png.

## Deployment (static, live on write)
- web/hub/demos/graphview/ + symblic-beta-kirby/ (copies of generated output + README + verify).
- Nav rows added via the host's registration script --nav (166 rows now). Gallery symblic-beta.html header nav now links both subsites.
- Live: http://127.0.0.1:8080/symblic-beta-graphview/ (200), /symblic-beta-kirby/ (200), both render.
- Public: (the public site of the original host, since retired) and /symblic-beta-kirby/ (gallery: /symblic-beta).

## Symblic product fixes this session
1. the host's agent-idle check for agy: seeded sessions (last_user_input_step_index=-1) no longer vetoed; test added; its 17 tests passed. Root cause of yesterday's T2. Restarted the dashboard.
- Pending: the host's full check run (824 modules selected because the live checkout had thousands of uncommitted files from others).

## Findings list for the user (final)
- F1 statement-authoring: fresh agents cannot resolve "the current folder"; absolute paths per statement are mandatory for reproducibility.
- F2 (FIXED, product): agy native completion adapter dead for seeded sessions -> the T2 root cause.
- F3: fresh agents can wedge on their own unbounded background searches; no watchdog. Statement/context bans mitigate; product could add a step wall-clock.
- F5: dispatch-time engine failure (agy eligibility 503) leaves step active with idle terminal forever; no retry/failure state. Recovered by cancel+resubmit (Kirby run2 succeeded).
- F6 (minor): ~500 stale agy presence lock files accumulate.
- F7 (minor): one Kirby agent created undeclared extra files (preview PNGs, test_states.html) then cleaned them; statement discipline "only the named files" was violated but harmless here.

## Reproducibility
- Statement scripts: /tmp/beta-graphview.english.txt (8 statements), /tmp/beta-kirby.english.txt (4 statements); context notes recorded in the task receipts (client_request_ids beta20261008-graphview-run2, beta20261008-kirby-run2). Rerunning the same statements reproduces the same file set (validated by run2 after run1 cancellation producing identical file targets).
- Forge project forge-cd06d83313104db7b556af7b5a2d07d4 holds the structured idea; AGY reviewed the statement list pre-run (15 fixes applied).
