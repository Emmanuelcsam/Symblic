"""symblic.os: an EXPERIMENTAL prototype of an operating-system layer driven by Symblic.

The working core is a terminal engine (terminal_server.py) that executes a fixed set of whole English
sentences as bounded file and process effects inside one root folder, compiles (never runs) Symblic
source, and writes a durable receipt for every instruction. Around it: the English intake (intake.py),
the filesystem boundary (fs_boundary.py), file and process effects (file_effects.py,
process_effects.py), receipts (receipts.py), the wire protocol (protocol.py), the compiler bridge
(compiler_bridge.py), an offline smoke suite (acceptance.py), scripted demonstrations
(demonstrations.py), a declared security surface (security_boundary.py), the folder layout (paths.py),
service templates (service_defs.py), and an image builder plus a QEMU boot check whose guest daemon is
a stub (image_builder.py, guest_daemon.c, virtual_boot.py). roadmap.py lists what an OS would still need.

See README.md in this folder for what works, what is a stub and how to run the tests. Parts that only
ran on the original host live in integration/host/ (symblicos_*.py). Importing this package has no
side effects.
"""
