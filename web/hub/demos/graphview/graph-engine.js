class GraphEngine {
  constructor() {
    this._params = {
      centerStrength: 0.05,
      linkStrength: 0.1,
      linkDistance: 30,
      repelStrength: 50,
      collideStrength: 0.5,
      alphaDecay: 0.02,
      velocityDecay: 0.4
    };
    this.alpha = 1;
    this._nodes = [];
    this._nodesById = new Map();
    this._links = [];
  }

  getParameter(name) {
    return this._params[name];
  }

  setParameter(name, value) {
    if (typeof name === 'string' && Object.prototype.hasOwnProperty.call(this._params, name)) {
      const num = Number(value);
      if (!Number.isNaN(num)) {
        this._params[name] = num;
      }
    }
  }

  initialize(vaultData) {
    this.alpha = 1;
    this._nodes = [];
    this._nodesById = new Map();
    this._links = [];

    if (!Array.isArray(vaultData)) {
      return;
    }

    // 1. One node for every note
    const noteIds = new Set();
    for (let i = 0; i < vaultData.length; i++) {
      const item = vaultData[i];
      if (item && item.id) {
        noteIds.add(item.id);
        const node = {
          id: item.id,
          x: 0,
          y: 0,
          z: 0,
          vx: 0,
          vy: 0,
          vz: 0,
          fx: 0,
          fy: 0,
          fz: 0,
          linkCount: 0,
          pinned: false,
          ghost: false,
          tag: false
        };
        this._nodes.push(node);
        this._nodesById.set(item.id, node);
      }
    }

    // 2. One ghost node for every distinct unresolved link target
    const ghostIds = new Set();
    for (let i = 0; i < vaultData.length; i++) {
      const item = vaultData[i];
      if (item && Array.isArray(item.links)) {
        for (let j = 0; j < item.links.length; j++) {
          const targetId = item.links[j];
          if (targetId && !noteIds.has(targetId) && !ghostIds.has(targetId)) {
            ghostIds.add(targetId);
            const ghostNode = {
              id: targetId,
              x: 0,
              y: 0,
              z: 0,
              vx: 0,
              vy: 0,
              vz: 0,
              fx: 0,
              fy: 0,
              fz: 0,
              linkCount: 0,
              pinned: false,
              ghost: true,
              tag: false
            };
            this._nodes.push(ghostNode);
            this._nodesById.set(targetId, ghostNode);
          }
        }
      }
    }

    // 3. One tag node for every distinct tag
    const tagIds = new Set();
    for (let i = 0; i < vaultData.length; i++) {
      const item = vaultData[i];
      if (item && Array.isArray(item.tags)) {
        for (let j = 0; j < item.tags.length; j++) {
          const tag = item.tags[j];
          if (tag && !tagIds.has(tag)) {
            tagIds.add(tag);
            const tagNode = {
              id: tag,
              x: 0,
              y: 0,
              z: 0,
              vx: 0,
              vy: 0,
              vz: 0,
              fx: 0,
              fy: 0,
              fz: 0,
              linkCount: 0,
              pinned: false,
              ghost: false,
              tag: true
            };
            this._nodes.push(tagNode);
            this._nodesById.set(tag, tagNode);
          }
        }
      }
    }

    // Seed distinct starting positions so no two nodes share a position
    const totalNodes = this._nodes.length;
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    const baseRadius = 80;
    for (let i = 0; i < totalNodes; i++) {
      const node = this._nodes[i];
      if (totalNodes === 1) {
        node.x = 0;
        node.y = 0;
        node.z = 0;
      } else {
        const yNorm = 1 - (2 * i + 1) / totalNodes;
        const radiusAtY = Math.sqrt(Math.max(0, 1 - yNorm * yNorm));
        const theta = i * goldenAngle;
        node.x = radiusAtY * Math.cos(theta) * baseRadius;
        node.y = yNorm * baseRadius;
        node.z = radiusAtY * Math.sin(theta) * baseRadius;
      }
    }

    // Create links:
    // - From each note to each link target (notes and ghost nodes)
    // - With one link from each note to each tag node matching its tags
    // Records each node's link count
    for (let i = 0; i < vaultData.length; i++) {
      const item = vaultData[i];
      if (!item || !item.id) continue;
      const srcNode = this._nodesById.get(item.id);
      if (!srcNode) continue;

      if (Array.isArray(item.links)) {
        const seenLinks = new Set();
        for (let j = 0; j < item.links.length; j++) {
          const targetId = item.links[j];
          if (targetId && !seenLinks.has(targetId)) {
            seenLinks.add(targetId);
            const tgtNode = this._nodesById.get(targetId);
            if (tgtNode) {
              this._links.push({ source: srcNode, target: tgtNode });
              srcNode.linkCount++;
              tgtNode.linkCount++;
            }
          }
        }
      }

      if (Array.isArray(item.tags)) {
        const seenTags = new Set();
        for (let j = 0; j < item.tags.length; j++) {
          const tag = item.tags[j];
          if (tag && !seenTags.has(tag)) {
            seenTags.add(tag);
            const tgtNode = this._nodesById.get(tag);
            if (tgtNode) {
              this._links.push({ source: srcNode, target: tgtNode });
              srcNode.linkCount++;
              tgtNode.linkCount++;
            }
          }
        }
      }
    }
  }

  tick() {
    if (this.alpha < 0.01) {
      return false;
    }

    const nNodes = this._nodes.length;
    const nLinks = this._links.length;
    const centerStrength = this._params.centerStrength;
    const linkStrength = this._params.linkStrength;
    const linkDistance = this._params.linkDistance;
    const repelStrength = this._params.repelStrength;
    const collideStrength = this._params.collideStrength;
    const velocityDecay = this._params.velocityDecay;
    const damping = 1.0 - velocityDecay;
    const minDistance = 8.0;

    // 1. Center attraction toward origin scaled by centerStrength
    for (let i = 0; i < nNodes; i++) {
      const node = this._nodes[i];
      if (!node.pinned) {
        node.fx -= node.x * centerStrength;
        node.fy -= node.y * centerStrength;
        node.fz -= node.z * centerStrength;
      }
    }

    // 2. Spring force along every link toward its rest length linkDistance scaled by linkStrength
    for (let i = 0; i < nLinks; i++) {
      const link = this._links[i];
      const src = link.source;
      const tgt = link.target;
      const dx = tgt.x - src.x;
      const dy = tgt.y - src.y;
      const dz = tgt.z - src.z;
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1e-4;
      const displacement = dist - linkDistance;
      const force = displacement * linkStrength * 0.5;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      const fz = (dz / dist) * force;
      if (!src.pinned) {
        src.fx += fx;
        src.fy += fy;
        src.fz += fz;
      }
      if (!tgt.pinned) {
        tgt.fx -= fx;
        tgt.fy -= fy;
        tgt.fz -= fz;
      }
    }

    // 3. Mutual repulsion between every pair of nodes scaled by repelStrength,
    //    and separation preventing overlapping nodes scaled by collideStrength
    for (let i = 0; i < nNodes; i++) {
      const nodeI = this._nodes[i];
      for (let j = i + 1; j < nNodes; j++) {
        const nodeJ = this._nodes[j];
        const dx = nodeJ.x - nodeI.x;
        const dy = nodeJ.y - nodeI.y;
        const dz = nodeJ.z - nodeI.z;
        const distSq = dx * dx + dy * dy + dz * dz;
        const dist = Math.sqrt(distSq) || 1e-4;

        // Mutual repulsion
        const repForce = repelStrength / Math.max(distSq, 1.0);
        let fx = (dx / dist) * repForce;
        let fy = (dy / dist) * repForce;
        let fz = (dz / dist) * repForce;

        // Collision separation
        if (collideStrength > 0 && distSq < minDistance * minDistance) {
          const overlap = minDistance - dist;
          const colForce = overlap * collideStrength * 0.5;
          fx += (dx / dist) * colForce;
          fy += (dy / dist) * colForce;
          fz += (dz / dist) * colForce;
        }

        if (!nodeI.pinned) {
          nodeI.fx -= fx;
          nodeI.fy -= fy;
          nodeI.fz -= fz;
        }
        if (!nodeJ.pinned) {
          nodeJ.fx += fx;
          nodeJ.fy += fy;
          nodeJ.fz += fz;
        }
      }
    }

    // 4. Integrate with damping by velocityDecay
    for (let i = 0; i < nNodes; i++) {
      const node = this._nodes[i];
      if (node.pinned) {
        node.vx = 0;
        node.vy = 0;
        node.vz = 0;
      } else {
        node.vx = (node.vx + node.fx) * damping;
        node.vy = (node.vy + node.fy) * damping;
        node.vz = (node.vz + node.fz) * damping;
        node.x += node.vx;
        node.y += node.vy;
        node.z += node.vz;
      }
      node.fx = 0;
      node.fy = 0;
      node.fz = 0;
    }

    // 5. Decrement alpha by alphaDecay
    this.alpha -= this._params.alphaDecay;
    if (this.alpha < 0) {
      this.alpha = 0;
    }

    return true;
  }

  pin(id, x, y, z) {
    const node = this._nodesById.get(id);
    if (node) {
      node.pinned = true;
      node.x = Number(x);
      node.y = Number(y);
      node.z = Number(z);
      node.vx = 0;
      node.vy = 0;
      node.vz = 0;
    }
  }

  unpin(id) {
    const node = this._nodesById.get(id);
    if (node) {
      node.pinned = false;
    }
  }

  reheat() {
    this.alpha = 1;
  }

  positions() {
    const total = this._nodes.length;
    const result = new Array(total);
    for (let i = 0; i < total; i++) {
      const node = this._nodes[i];
      result[i] = {
        id: node.id,
        x: node.x,
        y: node.y,
        z: node.z,
        links: node.linkCount,
        pinned: Boolean(node.pinned),
        ghost: Boolean(node.ghost),
        tag: Boolean(node.tag)
      };
    }
    return result;
  }
}

if (typeof globalThis !== 'undefined') {
  globalThis.GraphEngine = GraphEngine;
}
