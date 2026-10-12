# Checked small-model cup and chart

Qwen3:4b-instruct generated every implementation function in this bundle through Symblic, served by Ollama on a CPU-only machine. The author supplied objectives, decomposition, validators, orchestration and the STL encoder. Accepted functions and meshes were never hand repaired. These are finite synthetic feature tests, not a general model benchmark.

The cup was split into four functions: centered rectangle corners, oriented ring joins, upward/downward caps, and final assembly. The target is **100 × 80 × 100 mm**, with **2 mm walls and base**, an open **96 × 76 × 98 mm** cavity, and **84,992 mm³** of material. STL itself carries no unit field; import these coordinates as millimeters. An alternate **37 × 29 × 53 mm** case uses 1.5 mm walls and a 3.25 mm base, giving **12,890 mm³** of material.

- [Target binary STL](target-cup.stl), [alternate STL](alternate-cup.stl), and exact mesh data ([target](target-mesh.json), [alternate](alternate-mesh.json)). Each mesh has 16 shared vertices, 28 triangles and 42 edges.
- [Model-written cup functions](cup.js), with unchanged individual source files and hashes in [the evidence record](evidence.json).
- [Accessible synthetic chart](chart.svg), [browser preview](chart-preview.png) and [model-written chart function](chart.js). A, B and C represent 2, 5 and 3 ms; bar heights are 40, 100 and 60 pixels above a common zero baseline.

Native checks exercised three cup dimension sets. An independent exact-rational checker verified boundary planes, areas, outward winding, two opposite incidences per shared edge, connectivity, positive volume and the open cavity. Both exported STLs were decoded and revalidated. Two valid oracle fixtures and six corrupted fixtures checked agreement between the native and independent validators; four additional mesh mutations were rejected for each exported size. This does **not** establish printability, material suitability, strength, watertightness of a physical print or machine safety.

The decomposed cup required 12 actual model calls across retained attempts. Earlier ring-join and assembly failures remained failed; only verified functions were reused. The chart took two calls in the corrected round, after an earlier one-call trial had failed. The evidence record includes every call in this decomposed build family, usage counters, reply/receipt hashes, rejected attempts and original native identities. The full raw run records were not published; their counts and hashes are in the evidence record. Manifest observations identify what Ollama reported before/after calls; they are not attestation of loaded weights.

Run the independent checks without models:

```sh
python3 examples/small-model-builds-20261007/verify.py
```

The playback programs `examples/41-small-model-cup.sym` and `examples/42-small-model-chart.sym` execute the exact accepted functions and their checks with zero model calls. Playback produces a new validation receipt under the current runtime; it does not recreate or relabel the original generation receipts.

```sh
tools/symblic run examples/41-small-model-cup.sym --max-calls 0 --dir /tmp/new-cup-playback
tools/symblic run examples/42-small-model-chart.sym --max-calls 0 --dir /tmp/new-chart-playback
```

Use a new private run directory each time. The original native runtime requires its existing Node sandbox and refuses unavailable dependencies.

The additional [Snake state function](snake.js) passed eight native checks after two calls, including growth, one-cell movement, frozen inputs and independent returned cells. This is a game-state component, not a complete game. The [category totals program](totals.js) passed seven checks in one call, including empty/prototype-looking category names, signed amounts and Unicode scalar ordering. The playback program `examples/43-small-model-programs.sym` runs both sets of checks. The same bounded round rejected three pricing-page candidates; those failures remain in the evidence record and no failed page is published.
