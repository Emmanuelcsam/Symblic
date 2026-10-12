# Symblic Beta Graph View

A self-contained, interactive 3D Obsidian-style graph visualization web application built with plain ECMAScript 2020 and WebGL2.

---

## 1. How to Open the App

The application is completely self-contained with no build steps, bundling, or external dependencies. It can be opened directly from disk or via a local static HTTP server.

### Direct File Path (Recommended)
Open `index.html` directly in any modern web browser supporting WebGL2:

- **Browser URL**:
  ```text
  file:///srv/symblic/projects/beta-graphview/index.html
  ```

- **Linux Command Line**:
  ```bash
  # Using default browser
  xdg-open file:///srv/symblic/projects/beta-graphview/index.html

  # Or using Chrome / Chromium
  google-chrome /srv/symblic/projects/beta-graphview/index.html

  # Or using Firefox
  firefox /srv/symblic/projects/beta-graphview/index.html
  ```

### Local Static HTTP Server (Optional)
If running under an HTTP server is preferred:

```bash
cd /srv/symblic/projects/beta-graphview
python3 -m http.server 8000
```
Then navigate to:
```text
http://localhost:8000/
```

*Note: The app requires no build step (`npm install`, webpack, vite, etc.), no CDN connections, no remote fonts, and no external libraries.*

---

## 2. Implemented Features by File

Every feature in the application is implemented across six modular, self-contained files:

### `index.html`
- **Application Shell & Dual-Canvas Layout**: Hosts the primary WebGL2 canvas (`#graph-canvas`) and transparent 2D text overlay canvas (`#label-canvas`).
- **Dark Theme UI Styling**: Obsidian-inspired dark interface with custom CSS variables (`--bg-color`, `--panel-bg`, `--panel-border`, `--text-color`, `--text-muted`, `--accent-color`).
- **Frosted Glass Settings Panel**: Floating `#settings-panel` positioned in the top-right corner featuring backdrop blur (`backdrop-filter: blur(12px)`), rounded borders, and custom scrollbar styling.
- **Application Footer**: Fixed `#graph-footer` displaying status branding (`Symblic beta`).
- **Runtime Orchestration & Render Loop**: Loads script files in correct dependency order, instantiates `GraphEngine` and `GraphRender`, binds input handlers via `attachGraphInput`, mounts UI controls via `mountGraphUI`, and drives the continuous `requestAnimationFrame` loop.

### `vault-data.js`
- **Vault Note Dataset (`VAULT_DATA`)**: Structured array of note objects simulating an Obsidian personal knowledge vault.
- **Note Metadata Schema**: Each entry includes a unique `id`, human-readable `name` (including notes and file attachments), category `folder`, array of `tags`, and outgoing `links`.
- **Folder Categorization**: Organizes notes across six distinct folders (`Atlas`, `Chronicles`, `Lexicon`, `Research`, `Systems`, and `Theory`).
- **Specialized Node Archetypes**:
  - **File Attachments**: Identifiable files with extensions (`.png`, `.pdf`).
  - **Orphan Notes**: Notes with zero incoming and zero outgoing links.
  - **Unresolved Link Targets**: Outgoing link references pointing to notes outside the dataset.
  - **Tag Identifiers**: Categorical tags linking related notes.

### `graph-engine.js`
- **3D Force-Directed Simulation Engine (`GraphEngine`)**: Physics simulation calculating node dynamics in three-dimensional space.
- **Graph Topology Builder (`initialize`)**:
  - Instantiates primary nodes for each vault note.
  - Instantiates ghost nodes for unresolved link targets.
  - Instantiates tag nodes for each unique tag in the vault.
  - Generates links for note-to-note connections, note-to-ghost connections, and note-to-tag connections.
  - Calculates degree/link count per node.
- **Spherical Fibonacci Initialization**: Distributes initial 3D positions across a golden-spiral sphere to prevent overlapping coordinates.
- **Configurable Physics Parameters (`getParameter`, `setParameter`)**:
  - `centerStrength`: Gravitational attraction force pulling all nodes toward the coordinate origin.
  - `linkStrength`: Hooke's law spring force pulling connected nodes toward equilibrium distance.
  - `linkDistance`: Rest distance / equilibrium length between linked nodes.
  - `repelStrength`: Inverse-square Coulomb-like repulsion between all pairs of nodes.
  - `collideStrength`: Short-range collision separation force preventing node overlap below minimum distance (8.0).
  - `alphaDecay`: Rate of alpha temperature decay per tick.
  - `velocityDecay`: Velocity damping factor (friction).
- **Physics Integration Step (`tick`)**: Applies center attraction, spring forces, mutual n-body repulsion, and collision separation with velocity damping; cools down simulation alpha.
- **Node Pinning & Simulation Control**:
  - `pin(id, x, y, z)`: Locks a node's coordinates in 3D space and cancels its velocity.
  - `unpin(id)`: Releases a pinned node back into dynamic simulation.
  - `reheat()`: Resets simulation alpha to 1.0 to re-energize the graph upon interaction or parameter change.
  - `positions()`: Exports array of current node 3D coordinates, link counts, and status flags (`pinned`, `ghost`, `tag`).

### `graph-render.js`
- **WebGL2 3D Graph Renderer (`GraphRender`)**: High-performance hardware-accelerated 3D rendering pipeline for nodes and links.
- **Procedural Shader Billboard Nodes**:
  - Camera-facing quad billboards rendered using instanced vertex and fragment shaders.
  - Regular notes rendered as antialiased circular discs with radial glow.
  - Folder-based node palette: 6 distinct colors mapped to vault folders (Atlas: Blue, Chronicles: Amber, Lexicon: Purple, Research: Emerald, Systems: Rose, Theory: Cyan).
  - Ghost nodes rendered as hollow circles / rings (`GHOST_COLOR`).
  - Tag nodes rendered as diamonds / rhombuses (`TAG_COLOR`).
  - Node radius scaling proportional to node link degree (`(3.0 + 1.2 * sqrt(links)) * nodeSize`).
- **WebGL2 Link Geometry**:
  - 3D line segment rendering between connected nodes.
  - Depth fog attenuation blending links smoothly into background color.
  - Dynamic link states: default color, lit/active color for highlighted/focused nodes and neighbors, and dimmed color for inactive connections.
  - Directional 3D arrowheads / cones along link directions when enabled.
- **3D Orbit & Perspective Camera**:
  - Orbiting camera system supporting yaw and pitch rotation around the origin.
  - Pan offset along camera right/up vectors.
  - Perspective projection matrix with configurable field-of-view, aspect ratio, and clipping planes.
- **2D Canvas High-DPI Text Label Overlay**:
  - Crisp text rendering of note names and tags (`#tag`).
  - Distance-based label fading against configurable `textFadeThreshold`.
  - Automatic dimming and opacity fading for non-highlighted nodes.
- **Display Options & Filtering (`getOption`, `setOption`)**:
  - `arrows`: Toggle directional arrowheads on links.
  - `nodeSize`: Global size scaling multiplier for all nodes.
  - `textFadeThreshold`: Distance cutoff for label fading.
  - `animate`: Toggle real-time physics tick execution during animation frames.
  - `labels`: Toggle visibility of text overlay labels.
  - `highlight`: Highlight matching nodes and 1st-degree neighbors while dimming the rest of the graph.
  - `focusDepth`: N-degree BFS neighborhood filtering radiating from the focused node.
  - `attachments`: Toggle visibility of attachment file nodes (`.png`, `.pdf`).
  - `unresolved`: Toggle visibility of unresolved / ghost link nodes.
  - `orphans`: Toggle visibility of disconnected orphan nodes.
  - `tags`: Toggle visibility of tag nodes and note-to-tag links.
- **Interaction Raycasting & Math Utilities**:
  - `pick(x, y)`: Screen-to-world raycast picking detecting the closest node under cursor.
  - `unproject(x, y)`: Unprojects 2D screen coordinates into 3D world space at camera plane for dragging.
  - `focus(nodeId)` / `clearFocus()`: Focus state management.
  - `onHover(callback)`: Registers listener callback for node hover transitions.

### `graph-input.js`
- **Multi-Modal Input Controller (`attachGraphInput`)**: Binds mouse, pointer, touch, and wheel events to the canvas.
- **Camera Orbiting**: Left-click drag on empty canvas background rotates camera yaw and pitch.
- **Camera Panning**: Right-click drag, Middle-click drag, or Shift + Left-click drag pans the camera view in 3D.
- **Camera Zooming**: Mouse wheel scroll and touch pinch-to-zoom adjust camera distance clamped within `[10, 3000]`.
- **Interactive Node Dragging**: Left-click dragging a node raycasts and unprojects cursor coordinates into 3D, pins the node (`engine.pin`), and continually reheats physics (`engine.reheat`), releasing/unpinning on pointer up.
- **Focus & Selection**: Single-click on a node focuses it (`renderer.focus`); double-clicking empty canvas space resets the camera view and clears focus (`renderer.clearFocus`).
- **Hover Detection**: Real-time cursor raycasting tracking hovered nodes, triggering hover callbacks, and toggling cursor style between `pointer` and `default`.
- **Multi-Touch Gestures**: Touch support for mobile/touchscreens (single-finger orbit, two-finger pan, and two-finger pinch zoom).
- **Context Menu Suppression**: Prevents browser context menu on right-click to allow seamless panning.

### `graph-ui.js`
- **Settings Panel UI Controller (`mountGraphUI`)**: Generates and mounts an interactive Obsidian-style settings drawer inside `#settings-panel`.
- **Toggle Controls**:
  - **Animation**: Toggles live physics simulation (`animate` option).
  - **Arrows**: Toggles directional arrows on links (`arrows` option).
  - **Labels**: Toggles text label overlay visibility (`labels` option).
  - **Attachments**: Filters attachment file nodes (`attachments` option).
  - **Unresolved**: Filters ghost / unresolved link nodes (`unresolved` option).
  - **Orphans**: Filters disconnected orphan nodes (`orphans` option).
  - **Tags**: Filters tag nodes and tag links (`tags` option).
- **Slider Controls (with real-time numeric value displays)**:
  - **Node size**: Adjusts node scale (0.1 – 10.0, step 0.1).
  - **Text fade threshold**: Adjusts distance threshold for text label fading (0 – 1000, step 1).
  - **Focus depth**: Sets neighborhood traversal depth for focused node (0 – 10, step 1).
  - **Center force**: Sets simulation center attraction strength (0 – 1.0, step 0.005).
  - **Link force**: Sets spring attraction force along links (0 – 1.0, step 0.01).
  - **Link distance**: Sets spring rest distance (1 – 300, step 1).
  - **Repel force**: Sets mutual node repulsion force (0 – 300, step 1).
  - **Collision**: Sets short-range collision separation strength (0 – 2.0, step 0.05).
- **Search & Filter Field**:
  - Real-time text search input querying note names, note IDs, and tags (supports `#tag` syntax).
  - Automatically highlights matching nodes and their neighbors in the graph while dimming non-matching elements.

---

## 3. Dataset Notice

**The note dataset contained in `vault-data.js` (`VAULT_DATA`) is entirely fictional.** It was created exclusively as test data for the graph view application and contains no real or personal data.
