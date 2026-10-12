function gantryGeometry(p, travel) {
    const { width: w, depth: d, height: h, thickness: t, carriageWidth: cw, carriageDepth: cd, carriageHeight: ch, clearance: g } = p;
    
    const base = boxMesh(w, d, t);
    const left_post = translatedMesh(boxMesh(t, t, h - 2 * t), -(w - t) / 2, 0, t);
    const right_post = translatedMesh(boxMesh(t, t, h - 2 * t), (w - t) / 2, 0, t);
    const crossbar = translatedMesh(boxMesh(w, t, t), 0, 0, h - t);
    const carriage = translatedMesh(boxMesh(cw, cd, ch), travel, 0, h + g);
    
    return {
        units: "mm",
        parts: [
            { name: "base", mesh: base },
            { name: "left_post", mesh: left_post },
            { name: "right_post", mesh: right_post },
            { name: "crossbar", mesh: crossbar },
            { name: "carriage", mesh: carriage }
        ]
    };
}