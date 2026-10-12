# integration

Glue between Symblic and the host system it was built in. Everything here is in `host/`: the original host's
HTTP routes, job launchers, pages and scripts for Symblic, kept for reference. None of it runs on its own; see
`host/README.md` for what each module did and what a host would have to provide, and `tests/integration/` for
their tests (most run against fakes).

A few `symblic` package modules import from `host/` on the code path of a host feature (saved programs, browser
applicators, English run records, Forge handoffs); `host/README.md` lists them. `tools/symblic preview` runs the
preview half of `host/symblic_engine.py`, which works without a host; `tools/symblic memory` reaches
`host/symblic_memory_api.py`, which needs one.
