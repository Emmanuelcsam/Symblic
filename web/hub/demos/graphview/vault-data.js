const VAULT_DATA = [
  {
    id: "stellar-cartography-map",
    name: "stellar-cartography-map.png",
    folder: "Atlas",
    tags: ["atlas", "cartography", "map"],
    links: ["aether-drift-survey", "zenith-passage", "fall-of-the-citadel"]
  },
  {
    id: "aether-drift-survey",
    name: "aether-drift-survey.pdf",
    folder: "Atlas",
    tags: ["atlas", "survey", "aether"],
    links: ["celestial-meridian", "perihelion-ridge"]
  },
  {
    id: "celestial-meridian",
    name: "Celestial Meridian",
    folder: "Atlas",
    tags: ["atlas", "astronomy"],
    links: ["great-rift-corridor", "caldera-expanse", "treaty-of-veridian"]
  },
  {
    id: "great-rift-corridor",
    name: "Great Rift Corridor",
    folder: "Atlas",
    tags: ["atlas", "navigation"],
    links: ["outer-verge-sector", "nadir-strait", "unresolved-echo-basin"]
  },
  {
    id: "outer-verge-sector",
    name: "Outer Verge Sector",
    folder: "Atlas",
    tags: ["atlas", "sector"],
    links: ["solstice-basin", "umbra-chasm"]
  },
  {
    id: "solstice-basin",
    name: "Solstice Basin",
    folder: "Atlas",
    tags: ["atlas", "geography"],
    links: ["aurora-plateau", "corona-marsh", "founding-of-halcyon"]
  },
  {
    id: "aurora-plateau",
    name: "Aurora Plateau",
    folder: "Atlas",
    tags: ["atlas", "topography"],
    links: ["zenith-passage", "equinox-reach"]
  },
  {
    id: "zenith-passage",
    name: "Zenith Passage",
    folder: "Atlas",
    tags: ["atlas", "transit"],
    links: ["perihelion-ridge", "ancient-cipher-transcription"]
  },
  {
    id: "perihelion-ridge",
    name: "Perihelion Ridge",
    folder: "Atlas",
    tags: ["atlas", "terrain"],
    links: ["caldera-expanse", "dynasty-timeline-manifest", "unresolved-chrono-gate"]
  },
  {
    id: "caldera-expanse",
    name: "Caldera Expanse",
    folder: "Atlas",
    tags: ["atlas", "regions"],
    links: ["nadir-strait", "age-of-glass"]
  },
  {
    id: "nadir-strait",
    name: "Nadir Strait",
    folder: "Atlas",
    tags: ["atlas", "navigation"],
    links: ["umbra-chasm", "first-expedition-log", "astral-dialect-glossary"]
  },
  {
    id: "umbra-chasm",
    name: "Umbra Chasm",
    folder: "Atlas",
    tags: ["atlas", "topography"],
    links: ["corona-marsh", "council-of-stars"]
  },
  {
    id: "corona-marsh",
    name: "Corona Marsh",
    folder: "Atlas",
    tags: ["atlas", "wetlands"],
    links: ["equinox-reach", "fall-of-the-citadel", "runic-syntax-rules"]
  },
  {
    id: "equinox-reach",
    name: "Equinox Reach",
    folder: "Atlas",
    tags: ["atlas", "frontiers"],
    links: ["ancient-cipher-transcription", "great-silence-era", "unresolved-astral-spire"]
  },
  {
    id: "ancient-cipher-transcription",
    name: "ancient-cipher-transcription.png",
    folder: "Chronicles",
    tags: ["history", "cipher", "relic"],
    links: ["dynasty-timeline-manifest", "treaty-of-veridian"]
  },
  {
    id: "dynasty-timeline-manifest",
    name: "dynasty-timeline-manifest.pdf",
    folder: "Chronicles",
    tags: ["history", "chronicles", "records"],
    links: ["age-of-glass", "voyage-of-the-aurora", "archaic-prefixes"]
  },
  {
    id: "age-of-glass",
    name: "Age of Glass",
    folder: "Chronicles",
    tags: ["history", "era"],
    links: ["first-expedition-log", "siege-of-the-spire"]
  },
  {
    id: "first-expedition-log",
    name: "First Expedition Log",
    folder: "Chronicles",
    tags: ["expedition", "records"],
    links: ["council-of-stars", "founding-of-halcyon"]
  },
  {
    id: "council-of-stars",
    name: "Council of Stars",
    folder: "Chronicles",
    tags: ["politics", "history"],
    links: ["fall-of-the-citadel", "relic-discovery-report", "unresolved-void-stratum"]
  },
  {
    id: "fall-of-the-citadel",
    name: "Fall of the Citadel",
    folder: "Chronicles",
    tags: ["history", "conflict"],
    links: ["great-silence-era", "pilgrimage-records"]
  },
  {
    id: "great-silence-era",
    name: "Great Silence Era",
    folder: "Chronicles",
    tags: ["history", "era"],
    links: ["treaty-of-veridian", "the-shattered-compact", "void-script-compendium"]
  },
  {
    id: "treaty-of-veridian",
    name: "Treaty of Veridian",
    folder: "Chronicles",
    tags: ["treaty", "diplomacy"],
    links: ["voyage-of-the-aurora", "glyph-taxonomy-sheet"]
  },
  {
    id: "voyage-of-the-aurora",
    name: "Voyage of the Aurora",
    folder: "Chronicles",
    tags: ["voyage", "lore"],
    links: ["siege-of-the-spire", "astral-dialect-glossary", "crystal-matrix-diagram"]
  },
  {
    id: "siege-of-the-spire",
    name: "Siege of the Spire",
    folder: "Chronicles",
    tags: ["conflict", "history"],
    links: ["founding-of-halcyon", "chronomantic-terms", "unresolved-crystal-hollow"]
  },
  {
    id: "founding-of-halcyon",
    name: "Founding of Halcyon",
    folder: "Chronicles",
    tags: ["settlement", "history"],
    links: ["relic-discovery-report", "runic-syntax-rules"]
  },
  {
    id: "relic-discovery-report",
    name: "Relic Discovery Report",
    folder: "Chronicles",
    tags: ["archaeology", "report"],
    links: ["pilgrimage-records", "aetheric-nomenclature", "lumina-wavelength-study"]
  },
  {
    id: "pilgrimage-records",
    name: "Pilgrimage Records",
    folder: "Chronicles",
    tags: ["tradition", "records"],
    links: ["the-shattered-compact", "geomantic-lexicon"]
  },
  {
    id: "the-shattered-compact",
    name: "The Shattered Compact",
    folder: "Chronicles",
    tags: ["history", "lore"],
    links: ["glyph-taxonomy-sheet", "archaic-prefixes"]
  },
  {
    id: "glyph-taxonomy-sheet",
    name: "glyph-taxonomy-sheet.pdf",
    folder: "Lexicon",
    tags: ["linguistics", "taxonomy"],
    links: ["astral-dialect-glossary", "planar-vocabulary", "unresolved-deep-cadence"]
  },
  {
    id: "astral-dialect-glossary",
    name: "Astral Dialect Glossary",
    folder: "Lexicon",
    tags: ["linguistics", "dialects"],
    links: ["chronomantic-terms", "celestial-idioms"]
  },
  {
    id: "chronomantic-terms",
    name: "Chronomantic Terms",
    folder: "Lexicon",
    tags: ["terminology", "chronomancy"],
    links: ["runic-syntax-rules", "cipher-phonetics", "lattice-distortion-notes"]
  },
  {
    id: "runic-syntax-rules",
    name: "Runic Syntax Rules",
    folder: "Lexicon",
    tags: ["runes", "grammar"],
    links: ["aetheric-nomenclature", "harmonic-glossary"]
  },
  {
    id: "aetheric-nomenclature",
    name: "Aetheric Nomenclature",
    folder: "Lexicon",
    tags: ["lexicon", "aether"],
    links: ["geomantic-lexicon", "void-script-compendium"]
  },
  {
    id: "geomantic-lexicon",
    name: "Geomantic Lexicon",
    folder: "Lexicon",
    tags: ["lexicon", "geomancy"],
    links: ["archaic-prefixes", "archival-shorthand", "unresolved-solar-prism"]
  },
  {
    id: "archaic-prefixes",
    name: "Archaic Prefixes",
    folder: "Lexicon",
    tags: ["etymology", "grammar"],
    links: ["planar-vocabulary", "crystal-matrix-diagram"]
  },
  {
    id: "planar-vocabulary",
    name: "Planar Vocabulary",
    folder: "Lexicon",
    tags: ["planes", "lexicon"],
    links: ["celestial-idioms", "void-frequency-analysis", "lumina-core-schematic"]
  },
  {
    id: "celestial-idioms",
    name: "Celestial Idioms",
    folder: "Lexicon",
    tags: ["language", "idioms"],
    links: ["cipher-phonetics", "resonance-decay-rates"]
  },
  {
    id: "cipher-phonetics",
    name: "Cipher Phonetics",
    folder: "Lexicon",
    tags: ["phonetics", "ciphers"],
    links: ["harmonic-glossary", "lumina-wavelength-study"]
  },
  {
    id: "harmonic-glossary",
    name: "Harmonic Glossary",
    folder: "Lexicon",
    tags: ["acoustics", "lexicon"],
    links: ["void-script-compendium", "flux-density-experiments", "unresolved-tide-nexus"]
  },
  {
    id: "void-script-compendium",
    name: "Void Script Compendium",
    folder: "Lexicon",
    tags: ["scripts", "linguistics"],
    links: ["archival-shorthand", "aether-conduction-trials"]
  },
  {
    id: "archival-shorthand",
    name: "Archival Shorthand",
    folder: "Lexicon",
    tags: ["notation", "archives"],
    links: ["crystal-matrix-diagram", "thermal-gradient-log", "harmonic-resonator-rig"]
  },
  {
    id: "crystal-matrix-diagram",
    name: "crystal-matrix-diagram.png",
    folder: "Research",
    tags: ["research", "crystallography"],
    links: ["void-frequency-analysis", "phase-shift-observations"]
  },
  {
    id: "void-frequency-analysis",
    name: "void-frequency-analysis.pdf",
    folder: "Research",
    tags: ["research", "acoustics"],
    links: ["resonance-decay-rates", "lattice-distortion-notes"]
  },
  {
    id: "resonance-decay-rates",
    name: "Resonance Decay Rates",
    folder: "Research",
    tags: ["research", "physics"],
    links: ["lumina-wavelength-study", "entropy-containment-test", "unresolved-shadow-matrix"]
  },
  {
    id: "lumina-wavelength-study",
    name: "Lumina Wavelength Study",
    folder: "Research",
    tags: ["optics", "research"],
    links: ["flux-density-experiments", "harmonic-coherence-lab"]
  },
  {
    id: "flux-density-experiments",
    name: "Flux Density Experiments",
    folder: "Research",
    tags: ["experiment", "flux"],
    links: ["aether-conduction-trials", "spectral-anomaly-series", "calibration-bus-protocol"]
  },
  {
    id: "aether-conduction-trials",
    name: "Aether Conduction Trials",
    folder: "Research",
    tags: ["conduction", "aether"],
    links: ["thermal-gradient-log", "catalyst-stability-study"]
  },
  {
    id: "thermal-gradient-log",
    name: "Thermal Gradient Log",
    folder: "Research",
    tags: ["thermodynamics", "data"],
    links: ["phase-shift-observations", "lumina-core-schematic"]
  },
  {
    id: "phase-shift-observations",
    name: "Phase Shift Observations",
    folder: "Research",
    tags: ["quantum", "research"],
    links: ["lattice-distortion-notes", "chrono-stabilizer-array", "unresolved-lunar-lattice"]
  },
  {
    id: "lattice-distortion-notes",
    name: "Lattice Distortion Notes",
    folder: "Research",
    tags: ["crystals", "materials"],
    links: ["entropy-containment-test", "void-siphon-regulator"]
  },
  {
    id: "entropy-containment-test",
    name: "Entropy Containment Test",
    folder: "Research",
    tags: ["entropy", "safety"],
    links: ["harmonic-coherence-lab", "astral-beacon-network", "aetheric-field-postulates"]
  },
  {
    id: "harmonic-coherence-lab",
    name: "Harmonic Coherence Lab",
    folder: "Research",
    tags: ["harmonics", "lab"],
    links: ["spectral-anomaly-series", "flux-accumulator-grid"]
  },
  {
    id: "spectral-anomaly-series",
    name: "Spectral Anomaly Series",
    folder: "Research",
    tags: ["spectrometry", "anomalies"],
    links: ["catalyst-stability-study", "harmonic-resonator-rig"]
  },
  {
    id: "catalyst-stability-study",
    name: "Catalyst Stability Study",
    folder: "Research",
    tags: ["chemistry", "catalysts"],
    links: ["lumina-core-schematic", "aether-manifold-pipeline", "unresolved-aether-well"]
  },
  {
    id: "lumina-core-schematic",
    name: "lumina-core-schematic.pdf",
    folder: "Systems",
    tags: ["systems", "schematics"],
    links: ["chrono-stabilizer-array", "pulse-generator-subsystem"]
  },
  {
    id: "chrono-stabilizer-array",
    name: "Chrono Stabilizer Array",
    folder: "Systems",
    tags: ["systems", "stabilizers"],
    links: ["void-siphon-regulator", "thermal-dissipation-heatsink", "quantum-superposition-principle"]
  },
  {
    id: "void-siphon-regulator",
    name: "Void Siphon Regulator",
    folder: "Systems",
    tags: ["systems", "regulators"],
    links: ["astral-beacon-network", "containment-field-emitter"]
  },
  {
    id: "astral-beacon-network",
    name: "Astral Beacon Network",
    folder: "Systems",
    tags: ["network", "telecom"],
    links: ["flux-accumulator-grid", "calibration-bus-protocol"]
  },
  {
    id: "flux-accumulator-grid",
    name: "Flux Accumulator Grid",
    folder: "Systems",
    tags: ["energy", "grid"],
    links: ["harmonic-resonator-rig", "telemetry-relay-cluster", "unresolved-frost-core"]
  },
  {
    id: "harmonic-resonator-rig",
    name: "Harmonic Resonator Rig",
    folder: "Systems",
    tags: ["systems", "harmonics"],
    links: ["aether-manifold-pipeline", "feedback-governor-loop"]
  },
  {
    id: "aether-manifold-pipeline",
    name: "Aether Manifold Pipeline",
    folder: "Systems",
    tags: ["pipelines", "hydraulics"],
    links: ["pulse-generator-subsystem", "unified-resonance-theory", "outer-verge-sector"]
  },
  {
    id: "pulse-generator-subsystem",
    name: "Pulse Generator Subsystem",
    folder: "Systems",
    tags: ["hardware", "pulse"],
    links: ["thermal-dissipation-heatsink", "temporal-causality-loops"]
  },
  {
    id: "thermal-dissipation-heatsink",
    name: "Thermal Dissipation Heatsink",
    folder: "Systems",
    tags: ["cooling", "hardware"],
    links: ["containment-field-emitter", "aetheric-field-postulates"]
  },
  {
    id: "containment-field-emitter",
    name: "Containment Field Emitter",
    folder: "Systems",
    tags: ["defense", "containment"],
    links: ["calibration-bus-protocol", "void-space-geometry"]
  },
  {
    id: "calibration-bus-protocol",
    name: "Calibration Bus Protocol",
    folder: "Systems",
    tags: ["protocols", "systems"],
    links: ["telemetry-relay-cluster", "harmonic-equilibrium"]
  },
  {
    id: "telemetry-relay-cluster",
    name: "Telemetry Relay Cluster",
    folder: "Systems",
    tags: ["telemetry", "relays"],
    links: ["feedback-governor-loop", "lumina-duality-thesis", "caldera-expanse"]
  },
  {
    id: "feedback-governor-loop",
    name: "Feedback Governor Loop",
    folder: "Systems",
    tags: ["controls", "systems"],
    links: ["unified-resonance-theory", "dimensional-drift-model"]
  },
  {
    id: "unified-resonance-theory",
    name: "Unified Resonance Theory",
    folder: "Theory",
    tags: ["theory", "physics"],
    links: ["temporal-causality-loops", "quantum-superposition-principle"]
  },
  {
    id: "temporal-causality-loops",
    name: "Temporal Causality Loops",
    folder: "Theory",
    tags: ["theory", "causality"],
    links: ["aetheric-field-postulates", "stellar-cartography-map"]
  },
  {
    id: "aetheric-field-postulates",
    name: "Aetheric Field Postulates",
    folder: "Theory",
    tags: ["theory", "postulates"],
    links: ["void-space-geometry", "aether-drift-survey"]
  },
  {
    id: "void-space-geometry",
    name: "Void Space Geometry",
    folder: "Theory",
    tags: ["geometry", "void"],
    links: ["harmonic-equilibrium", "celestial-meridian", "ancient-cipher-transcription"]
  },
  {
    id: "harmonic-equilibrium",
    name: "Harmonic Equilibrium",
    folder: "Theory",
    tags: ["equilibrium", "harmonics"],
    links: ["lumina-duality-thesis", "great-rift-corridor"]
  },
  {
    id: "lumina-duality-thesis",
    name: "Lumina Duality Thesis",
    folder: "Theory",
    tags: ["optics", "thesis"],
    links: ["dimensional-drift-model", "outer-verge-sector"]
  },
  {
    id: "dimensional-drift-model",
    name: "Dimensional Drift Model",
    folder: "Theory",
    tags: ["dimensions", "modeling"],
    links: ["quantum-superposition-principle", "solstice-basin"]
  },
  {
    id: "quantum-superposition-principle",
    name: "Quantum Superposition Principle",
    folder: "Theory",
    tags: ["theory", "quantum"],
    links: ["stellar-cartography-map", "aurora-plateau"]
  },
  {
    id: "unobserved-horizon",
    name: "Unobserved Horizon",
    folder: "Theory",
    tags: ["philosophy", "horizon"],
    links: []
  },
  {
    id: "isolated-axiom",
    name: "Isolated Axiom",
    folder: "Theory",
    tags: ["logic", "axioms"],
    links: []
  },
  {
    id: "solitary-reflection",
    name: "Solitary Reflection",
    folder: "Theory",
    tags: ["reflection", "solitude"],
    links: []
  },
  {
    id: "silent-hypothesis",
    name: "Silent Hypothesis",
    folder: "Theory",
    tags: ["hypothesis", "epistemology"],
    links: []
  },
  {
    id: "untethered-principle",
    name: "Untethered Principle",
    folder: "Theory",
    tags: ["philosophy", "principles"],
    links: []
  }
];
