# tests/fixtures: recorded inputs and outputs that tests compare against

| File | Used by | What it is |
|---|---|---|
| `symblic_capsule_full_v4.json` | `tests/kernel/test_symblic_capsule_presentation.py` | A complete ask capsule (the exact request a model receives) in format version 4. |
| `symblic_catalog_v7_parity.json`, `symblic_catalog_v8_parity.json` | `tests/integration/test_symblic_catalog_focus.py` | The delegate template catalogue as earlier versions produced it; newer code must reproduce it. |
| `symblic_delegate_v5_parity.json` … `symblic_delegate_v8_parity.json` | `tests/delegate/test_symblic_delegate_proof_*.py`, `tests/adapters/test_symblic_proof_step_wire.py`, `tests/integration/test_symblic_catalog_focus.py` | Delegate compilations from earlier versions, for the same parity checks. |
| `symblic-editor-checks.json` | `tests/browser/symblic-editor-integration.mjs` | Editor diagnostics for fixed native and English sources. |
| `symblic-english-construction.json`, `symblic-english-atomic-construction.json` | `tests/browser/symblic-english-*construction-circuit.mjs` | English construction programs compiled by the real compiler, for the circuit view. |
| `symblic-english-pixels.json`, `symblic-english-pixel-vm.json`, `symblic-english-pixel-vm-v1.json`, `symblic-english-pixel-recovery.json` | `tests/browser/symblic-english-pixel-circuit.mjs`; `symblic-english-pixels.json` also `tests/english/` and `symblic/english/pixels.py` | Compiled pixel programs (current and version 1) and a recovery case. They embed the third-party acorn parser (MIT licence) as program text. |
| `symblic-pixel-program.json` | `tests/browser/symblic-pixel-vm.mjs`, `symblic-pixel-program.mjs`, `tests/english/test_symblic_english_pixel_checks.py`, `symblic/english/pixel_checks.py` | A recorded, explicitly test-only model artifact for the pixel interpreter. |

The fixtures are data, not code; regenerate one only together with the change that alters its producer, and
say so in the change.
