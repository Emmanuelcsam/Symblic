# tests/misc

`test_automation_symblic_nodes.py` drives the Symblic node, the "Send to Studio" handoff and the run center of the
original host's automation engine (the backend of `web/studio/index.html`). That engine is not part of this
repository, so the module is skipped with the reason when it cannot be imported.

`test_symblic_frames_page.py` runs `tests/symblic_frames_check.js`, the Node.js check of the studio page's frame
validator (`web/studio/symblic-frames.js`); it needs only Node.js and is skipped without it.

    DASH_TEST=1 python3 -m unittest discover -s tests/misc -t .
