# Laptop PCB Explorer and Maker

## How to open the tool

Open the file `index.html` in a web browser.

## Features

### Core
- 3D PCB visualization — `pcb-render.js`
- Interactive board explorer — `index.html`, `pcb-render.js`, `pcb-input.js`, `pcb-info.js`
- PCB maker/designer — `index.html`, `pcb-maker.js`

### Explorer
- Component rendering (3D boxes and cylinders) — `pcb-render.js`
- Camera navigation (pan, rotate, zoom) — `pcb-render.js`, `pcb-input.js`
- Component selection (click/tap) — `pcb-input.js`, `pcb-render.js`
- Component highlighting — `pcb-render.js`, `pcb-info.js`
- Component info panel with stats — `pcb-info.js`
- Category color legend — `pcb-info.js`
- Search components by name, id, or category — `pcb-info.js`
- Walkthrough mode (cycle through all components) — `pcb-info.js`
- Spin/auto-rotate mode — `pcb-render.js`
- Traces visualization — `pcb-render.js`
- Labels overlay — `pcb-render.js`
- Pick mode for component identification — `pcb-render.js`
- Focus camera on selected component — `pcb-render.js`
- Reset view — `pcb-render.js`

### Maker
- Grid-based part placement — `pcb-maker.js`
- Parts palette (resistor, capacitor, inductor, chip, connector, crystal, header, mounting hole) — `pcb-maker.js`
- Part rotation in 90° increments — `pcb-maker.js`
- Trace creation between parts — `pcb-maker.js`
- Part dragging on grid — `pcb-maker.js`
- Part deletion — `pcb-maker.js`
- Export design to JSON file — `pcb-maker.js`
- Import design from JSON file — `pcb-maker.js`
- Parts list with type counts — `pcb-maker.js`

### Data
- Board core data (CPU, RAM, PCH, VRMs, BIOS, EC, WiFi) — `pcb-data.js`
- Board parts data (capacitors, resistors, inductors, crystals, audio, I/O, connectors, mechanical) — `pcb-parts.js`
- Network connections between components — `pcb-parts.js`

The board is a fictional educational reference design generated from nine English statements by fresh Mistral sessions, with no real product data.
