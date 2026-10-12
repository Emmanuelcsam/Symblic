'use strict';

const PCBRender = (function() {
  const vsSource = `#version 300 es
precision highp float;
uniform mat4 uMVP;
uniform mat3 uNormalMatrix;
uniform vec3 uCameraPosition;
uniform float uPickMode;
uniform float uHighlightId;
uniform vec3 uHighlightColor;
in vec3 aPosition;
in vec3 aNormal;
in vec3 aColor;
in float aPickId;
out vec3 vNormal;
out vec3 vPosition;
out vec3 vColor;
out float vFogFactor;
out vec4 vPickColor;
void main() {
  vec4 worldPos = vec4(aPosition, 1.0);
  vPosition = worldPos.xyz;
  vNormal = uNormalMatrix * aNormal;
  vColor = aColor;
  float dist = length(uCameraPosition - worldPos.xyz);
  vFogFactor = exp(-dist * 0.0005);
  if (uPickMode > 0.0) {
    vPickColor = vec4(aPickId / 255.0, fract(aPickId), 0.0, 1.0);
  } else {
    vPickColor = vec4(0.0);
  }
  gl_Position = uMVP * vec4(aPosition, 1.0);
}`;

  const fsSource = `#version 300 es
precision highp float;
uniform vec3 uLightDirection;
uniform vec3 uLightColor;
uniform vec3 uAmbientColor;
uniform float uPickMode;
uniform float uHighlightId;
uniform vec3 uHighlightColor;
in vec3 vNormal;
in vec3 vPosition;
in vec3 vColor;
in float vFogFactor;
in vec4 vPickColor;
out vec4 fragColor;
void main() {
  if (uPickMode > 0.0) {
    fragColor = vPickColor;
    return;
  }
  vec3 normal = normalize(vNormal);
  vec3 lightDir = normalize(uLightDirection);
  float diffuse = max(dot(normal, lightDir), 0.15);
  vec3 finalColor = vColor * (uAmbientColor + uLightColor * diffuse);
  if (uHighlightId > 0.5) {
    float pickId = vPickColor.r * 255.0 + vPickColor.g * 255.0;
    if (abs(pickId - uHighlightId) < 0.5) {
      finalColor = mix(finalColor, uHighlightColor, 0.7);
    } else {
      finalColor *= 0.4;
    }
  }
  vec3 fogColor = vec3(0.05, 0.05, 0.08);
  finalColor = mix(fogColor, finalColor, vFogFactor);
  fragColor = vec4(finalColor, 1.0);
}`;

  function createShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error('Shader error:', gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  function createProgram(gl, vs, fs) {
    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error('Link error:', gl.getProgramInfoLog(program));
      gl.deleteProgram(program);
      return null;
    }
    return program;
  }

  function mat4Identity() {
    return [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
  }

  function mat4Perspective(fov, aspect, near, far) {
    const f = 1.0 / Math.tan(fov / 2);
    return [
      f / aspect, 0, 0, 0,
      0, f, 0, 0,
      0, 0, (far + near) / (near - far), -1,
      0, 0, (2 * far * near) / (near - far), 0
    ];
  }

  function mat4LookAt(eye, center, up) {
    const z0 = [eye[0] - center[0], eye[1] - center[1], eye[2] - center[2]];
    const len = Math.sqrt(z0[0] * z0[0] + z0[1] * z0[1] + z0[2] * z0[2]);
    const z = [z0[0] / len, z0[1] / len, z0[2] / len];
    const x0 = [up[1] * z[2] - up[2] * z[1], up[2] * z[0] - up[0] * z[2], up[0] * z[1] - up[1] * z[0]];
    const xLen = Math.sqrt(x0[0] * x0[0] + x0[1] * x0[1] + x0[2] * x0[2]);
    const x = [x0[0] / xLen, x0[1] / xLen, x0[2] / xLen];
    const y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]];
    return [
      x[0], y[0], z[0], 0,
      x[1], y[1], z[1], 0,
      x[2], y[2], z[2], 0,
      -(x[0] * eye[0] + x[1] * eye[1] + x[2] * eye[2]),
      -(y[0] * eye[0] + y[1] * eye[1] + y[2] * eye[2]),
      -(z[0] * eye[0] + z[1] * eye[1] + z[2] * eye[2]),
      1
    ];
  }

  function mat4Multiply(a, b) {
    const r = new Array(16);
    for (let col = 0; col < 4; col++) {
      for (let row = 0; row < 4; row++) {
        r[col * 4 + row] = 0;
        for (let k = 0; k < 4; k++) {
          r[col * 4 + row] += a[k * 4 + row] * b[col * 4 + k];
        }
      }
    }
    return r;
  }

  function mat3FromMat4(m) {
    return [m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]];
  }

  function hexToRGB(hex) {
    if (!hex || !hex.startsWith('#')) return [0.8, 0.8, 0.8];
    const h = hex.substring(1);
    let r = 1, g = 1, b = 1;
    if (h.length === 3) {
      r = parseInt(h[0] + h[0], 16) / 255.0;
      g = parseInt(h[1] + h[1], 16) / 255.0;
      b = parseInt(h[2] + h[2], 16) / 255.0;
    } else if (h.length === 6) {
      r = parseInt(h.substring(0, 2), 16) / 255.0;
      g = parseInt(h.substring(2, 4), 16) / 255.0;
      b = parseInt(h.substring(4, 6), 16) / 255.0;
    }
    return [r, g, b];
  }

  function parseColor(c) {
    if (typeof c === 'string') return hexToRGB(c);
    if (Array.isArray(c) && c.length >= 3) return [c[0], c[1], c[2]];
    return [0.8, 0.8, 0.8];
  }

  function makeBoxGeometry(w, d, h) {
    const hw = w / 2, hd = d / 2, hh = h / 2;
    const vertices = new Float32Array([
      -hw, -hd,  hh,  0, 0, 1,
       hw, -hd,  hh,  0, 0, 1,
       hw,  hd,  hh,  0, 0, 1,
      -hw,  hd,  hh,  0, 0, 1,
      -hw, -hd, -hh,  0, 0, -1,
       hw, -hd, -hh,  0, 0, -1,
       hw,  hd, -hh,  0, 0, -1,
      -hw,  hd, -hh,  0, 0, -1,
       hw, -hd,  hh,  1, 0, 0,
       hw, -hd, -hh,  1, 0, 0,
       hw,  hd, -hh,  1, 0, 0,
       hw,  hd,  hh,  1, 0, 0,
      -hw, -hd,  hh, -1, 0, 0,
      -hw, -hd, -hh, -1, 0, 0,
      -hw,  hd, -hh, -1, 0, 0,
      -hw,  hd,  hh, -1, 0, 0,
      -hw,  hd,  hh,  0, 1, 0,
       hw,  hd,  hh,  0, 1, 0,
       hw,  hd, -hh,  0, 1, 0,
      -hw,  hd, -hh,  0, 1, 0,
      -hw, -hd,  hh,  0, -1, 0,
       hw, -hd,  hh,  0, -1, 0,
       hw, -hd, -hh,  0, -1, 0,
      -hw, -hd, -hh,  0, -1, 0
    ]);
    const indices = new Uint16Array([
      0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7,
      8, 9, 10, 8, 10, 11, 12, 13, 14, 12, 14, 15,
      16, 17, 18, 16, 18, 19, 20, 21, 22, 20, 22, 23
    ]);
    return { vertices, indices, vertexCount: indices.length };
  }

  function makeCylinderGeometry(radius, height, segments) {
    segments = segments || 16;
    const verts = [];
    const inds = [];
    const topCenter = segments * 2;
    const bottomCenter = topCenter + 1;
    
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      const x = Math.cos(angle) * radius;
      const z = Math.sin(angle) * radius;
      verts.push(x, -height/2, z, x, 0, z);
      verts.push(x, height/2, z, x, 0, z);
    }
    verts.push(0, -height/2, 0, 0, -1, 0);
    verts.push(0, height/2, 0, 0, 1, 0);
    
    for (let i = 0; i < segments; i++) {
      const next = (i + 1) % (segments + 1);
      const i0 = i * 2, i1 = i0 + 1, i2 = next * 2, i3 = i2 + 1;
      inds.push(i0, i1, i3);
      inds.push(i0, i3, i2);
    }
    
    for (let i = 0; i < segments; i++) {
      const next = (i + 1) % (segments + 1);
      const i0 = i * 2, i2 = next * 2;
      inds.push(i0, bottomCenter, i2);
    }
    
    for (let i = 0; i < segments; i++) {
      const next = (i + 1) % (segments + 1);
      const i1 = i * 2 + 1, i3 = next * 2 + 1;
      inds.push(i1, i3, topCenter);
    }
    
    return { vertices: new Float32Array(verts), indices: new Uint16Array(inds), vertexCount: inds.length };
  }

  function makeSlabGeometry(w, d, h) {
    const bevel = Math.min(w, d) * 0.02;
    const hw = w / 2, hd = d / 2;
    const bl0 = [-hw + bevel, -hd + bevel, 0];
    const br0 = [ hw - bevel, -hd + bevel, 0];
    const tl0 = [-hw + bevel,  hd - bevel, 0];
    const tr0 = [ hw - bevel,  hd - bevel, 0];
    const bl1 = [-hw, -hd, 0];
    const br1 = [ hw, -hd, 0];
    const tl1 = [-hw,  hd, 0];
    const tr1 = [ hw,  hd, 0];
    const bl2 = [-hw + bevel, -hd + bevel, h];
    const br2 = [ hw - bevel, -hd + bevel, h];
    const tl2 = [-hw + bevel,  hd - bevel, h];
    const tr2 = [ hw - bevel,  hd - bevel, h];
    const bl3 = [-hw, -hd, h];
    const br3 = [ hw, -hd, h];
    const tl3 = [-hw,  hd, h];
    const tr3 = [ hw,  hd, h];
    
    const color = [0.1, 0.4, 0.1];
    const verts = [];
    function v(x, y, z, nx, ny, nz) {
      verts.push(x, y, z, nx, ny, nz, color[0], color[1], color[2]);
      return verts.length / 9 - 1;
    }
    
    const v0 = v(bl0[0], bl0[1], bl0[2], 0, 0, -1);
    const v1 = v(br0[0], br0[1], br0[2], 0, 0, -1);
    const v2 = v(tr0[0], tr0[1], tr0[2], 0, 0, -1);
    const v3 = v(tl0[0], tl0[1], tl0[2], 0, 0, -1);
    const v4 = v(bl1[0], bl1[1], bl1[2], -0.7, -0.7, -0.2);
    const v5 = v(br1[0], br1[1], br1[2], 0.7, -0.7, -0.2);
    const v6 = v(tr1[0], tr1[1], tr1[2], 0.7, 0.7, -0.2);
    const v7 = v(tl1[0], tl1[1], tl1[2], -0.7, 0.7, -0.2);
    const v8 = v(bl2[0], bl2[1], bl2[2], 0, 0, 1);
    const v9 = v(br2[0], br2[1], br2[2], 0, 0, 1);
    const v10 = v(tr2[0], tr2[1], tr2[2], 0, 0, 1);
    const v11 = v(tl2[0], tl2[1], tl2[2], 0, 0, 1);
    const v12 = v(bl3[0], bl3[1], bl3[2], -0.7, -0.7, 0.2);
    const v13 = v(br3[0], br3[1], br3[2], 0.7, -0.7, 0.2);
    const v14 = v(tr3[0], tr3[1], tr3[2], 0.7, 0.7, 0.2);
    const v15 = v(tl3[0], tl3[1], tl3[2], -0.7, 0.7, 0.2);
    
    const indices = new Uint16Array([
      v0, v1, v2, v0, v2, v3,
      v0, v4, v5, v0, v5, v1,
      v1, v5, v6, v1, v6, v2,
      v2, v6, v7, v2, v7, v3,
      v3, v7, v4, v3, v4, v0,
      v8, v9, v10, v8, v10, v11,
      v8, v12, v13, v8, v13, v9,
      v9, v13, v14, v9, v14, v10,
      v10, v14, v15, v10, v15, v11,
      v11, v15, v12, v11, v12, v8,
      v0, v1, v9, v0, v9, v8,
      v1, v2, v10, v1, v10, v9,
      v2, v3, v11, v2, v11, v10,
      v3, v0, v8, v3, v8, v11
    ]);
    
    return { vertices: new Float32Array(verts), indices, vertexCount: indices.length };
  }

  function PCBRender(glCanvas, overlayCanvas, boardCore, boardParts) {
    if (!(this instanceof PCBRender)) {
      return new PCBRender(glCanvas, overlayCanvas, boardCore, boardParts);
    }
    
    this.glCanvas = glCanvas;
    this.overlayCanvas = overlayCanvas;
    this.boardCore = boardCore;
    this.boardParts = boardParts;
    this.gl = glCanvas.getContext('webgl2');
    if (!this.gl) throw new Error('WebGL2 not supported');
    
    const outline = boardCore.outline || { width: 260, depth: 180, height: 1.6 };
    this.boardSize = [outline.width, outline.depth, outline.height];
    
    // Camera - initialize before resetView
    this.camera = { target: [0, 0, 0], distance: 0, theta: Math.PI / 4, phi: Math.PI / 4, pan: [0, 0] };
    
    // Options
    this.options = { showTraces: true, showLabels: true, spin: false, highlight: null };
    
    this.resetView();
    
    // Components
    this.components = [];
    this.mountingHoles = [];
    this.nets = boardParts.nets || [];
    this._initComponents();
    
    // WebGL
    this.program = null;
    this.uLocations = {};
    this.aLocations = {};
    this.pickFramebuffer = null;
    this.pickTexture = null;
    this.pickDepthBuffer = null;
    this._initWebGL();
    
    // Time
    this.lastTime = 0;
    this.spinAngle = 0;
    
    // Lighting
    this.lightDirection = [0.4, -0.5, 1];
    this.lightColor = [0.8, 0.8, 0.7];
    this.ambientColor = [0.15, 0.15, 0.2];
    this.highlightColor = [1.0, 1.0, 0.5];
    
    // Cached geometry
    this.cachedGeom = {};
  }

  PCBRender.prototype._initComponents = function() {
    const comps = [];
    const holes = [];
    
    const process = (c) => {
      const position = c.position || { x: 0, y: 0, z: 0 };
      const size = c.size || { w: 10, d: 10, h: 1 };
      const color = parseColor(c.color);
      const id = c.id || c.name || 'unknown';
      const category = (c.category || '').toLowerCase();
      const pkg = (c.package || '').toLowerCase();
      
      let renderType = 'box';
      if (id.startsWith('cap') || category === 'passive' && (pkg.includes('0402') || pkg.includes('0603') || pkg.includes('0805') || pkg.includes('mlcc'))) {
        renderType = 'cylinder';
      } else if (id.startsWith('ind') || category === 'passive' && pkg.includes('mm') && !pkg.includes('0402') && !pkg.includes('0603')) {
        renderType = 'cylinder';
      } else if (id.startsWith('xtal') || category === 'clock') {
        renderType = 'crystal';
      }
      
      return {
        id: id,
        name: c.name || id,
        type: renderType,
        position: { x: position.x, y: position.y, z: position.z + size.h / 2 },
        size: [size.w, size.d, size.h],
        color: color,
        category: category,
        package: pkg
      };
    };
    
    for (const c of (this.boardCore.components || [])) comps.push(process(c));
    for (const c of (this.boardParts.components || [])) {
      const norm = process(c);
      if (c.package === 'mounting_hole' || (c.name && c.name.startsWith('hole'))) {
        holes.push(norm);
      } else {
        comps.push(norm);
      }
    }
    
    this.components = comps;
    this.mountingHoles = holes;
  };

  PCBRender.prototype._initWebGL = function() {
    const gl = this.gl;
    const vs = createShader(gl, gl.VERTEX_SHADER, vsSource);
    const fs = createShader(gl, gl.FRAGMENT_SHADER, fsSource);
    this.program = createProgram(gl, vs, fs);
    
    this.uLocations = {
      mvp: gl.getUniformLocation(this.program, 'uMVP'),
      normalMatrix: gl.getUniformLocation(this.program, 'uNormalMatrix'),
      cameraPosition: gl.getUniformLocation(this.program, 'uCameraPosition'),
      lightDirection: gl.getUniformLocation(this.program, 'uLightDirection'),
      lightColor: gl.getUniformLocation(this.program, 'uLightColor'),
      ambientColor: gl.getUniformLocation(this.program, 'uAmbientColor'),
      pickMode: gl.getUniformLocation(this.program, 'uPickMode'),
      highlightId: gl.getUniformLocation(this.program, 'uHighlightId'),
      highlightColor: gl.getUniformLocation(this.program, 'uHighlightColor')
    };
    
    this.aLocations = {
      position: gl.getAttribLocation(this.program, 'aPosition'),
      normal: gl.getAttribLocation(this.program, 'aNormal'),
      color: gl.getAttribLocation(this.program, 'aColor'),
      pickId: gl.getAttribLocation(this.program, 'aPickId')
    };
    
    // Create pick framebuffer
    const width = gl.canvas.width || gl.canvas.clientWidth;
    const height = gl.canvas.height || gl.canvas.clientHeight;
    
    this.pickTexture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.pickTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    
    this.pickDepthBuffer = gl.createRenderbuffer();
    gl.bindRenderbuffer(gl.RENDERBUFFER, this.pickDepthBuffer);
    gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, width, height);
    
    this.pickFramebuffer = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.pickFramebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.pickTexture, 0);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, this.pickDepthBuffer);
    
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.bindTexture(gl.TEXTURE_2D, null);
    gl.bindRenderbuffer(gl.RENDERBUFFER, null);
    
    gl.enable(gl.DEPTH_TEST);
    gl.cullFace(gl.BACK);
  };

  PCBRender.prototype._getComponentIndex = function(id) {
    for (let i = 0; i < this.components.length; i++) {
      if (this.components[i].id === id) return i + 1;
    }
    for (let i = 0; i < this.mountingHoles.length; i++) {
      if (this.mountingHoles[i].id === id) return i + 1 + this.components.length;
    }
    return 0;
  };

  PCBRender.prototype._getComponentByIndex = function(idx) {
    if (idx > 0 && idx <= this.components.length) return this.components[idx - 1];
    const holeIdx = idx - this.components.length - 1;
    if (holeIdx >= 0 && holeIdx < this.mountingHoles.length) return this.mountingHoles[holeIdx];
    return null;
  };

  PCBRender.prototype._findComponent = function(id) {
    for (const c of this.components) if (c.id === id || c.name === id) return c;
    for (const c of this.mountingHoles) if (c.id === id || c.name === id) return c;
    for (const c of (this.boardCore.components || [])) if (c.id === id || c.name === id) return c;
    return null;
  };

  PCBRender.prototype._updateCamera = function() {
    const camera = this.camera;
    const width = this.glCanvas.width || this.glCanvas.clientWidth;
    const height = this.glCanvas.height || this.glCanvas.clientHeight;
    const aspect = width / height;
    
    const theta = camera.theta || 0;
    const phi = camera.phi || 0;
    const radius = camera.distance || 500;
    const panX = camera.pan[0] || 0;
    const panY = camera.pan[1] || 0;
    
    const eyeX = camera.target[0] + panX + radius * Math.cos(phi) * Math.cos(theta);
    const eyeY = camera.target[1] + panY + radius * Math.sin(phi);
    const eyeZ = camera.target[2] + radius * Math.cos(phi) * Math.sin(theta);
    
    const eye = [eyeX, eyeY, eyeZ];
    const center = [camera.target[0] + panX, camera.target[1] + panY, camera.target[2]];
    const up = [0, 1, 0];
    
    this.cameraPosition = eye;
    this.viewMatrix = mat4LookAt(eye, center, up);
    this.projectionMatrix = mat4Perspective(Math.PI / 4, aspect, 10, 2000);
    this.mvpMatrix = mat4Multiply(this.projectionMatrix, this.viewMatrix);
  };

  PCBRender.prototype._makeVertexData = function(geometry, color, pickId) {
    const stride = 9;
    const vertexCount = geometry.vertices.length / 9;
    const vertices = new Float32Array(vertexCount * stride);
    
    for (let i = 0, j = 0; i < geometry.vertices.length; i += 9, j += stride) {
      vertices[j] = geometry.vertices[i];
      vertices[j+1] = geometry.vertices[i+1];
      vertices[j+2] = geometry.vertices[i+2];
      vertices[j+3] = geometry.vertices[i+3];
      vertices[j+4] = geometry.vertices[i+4];
      vertices[j+5] = geometry.vertices[i+5];
      vertices[j+6] = color[0];
      vertices[j+7] = color[1];
      vertices[j+8] = color[2];
    }
    return vertices;
  };

  PCBRender.prototype._makePickData = function(vertexCount, pickId) {
    const data = new Float32Array(vertexCount);
    for (let i = 0; i < vertexCount; i++) data[i] = pickId;
    return data;
  };

  PCBRender.prototype._drawMesh = function(geometry, color, modelMatrix, pickId) {
    const gl = this.gl;
    const mvp = mat4Multiply(this.mvpMatrix, modelMatrix);
    const normalMatrix = mat3FromMat4(modelMatrix);
    
    gl.uniformMatrix4fv(this.uLocations.mvp, false, mvp);
    gl.uniformMatrix3fv(this.uLocations.normalMatrix, false, normalMatrix);
    
    const vertices = this._makeVertexData(geometry, color, pickId);
    const vertexBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
    
    const indexBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, geometry.indices, gl.STATIC_DRAW);
    
    gl.vertexAttribPointer(this.aLocations.position, 3, gl.FLOAT, false, 36, 0);
    gl.enableVertexAttribArray(this.aLocations.position);
    gl.vertexAttribPointer(this.aLocations.normal, 3, gl.FLOAT, false, 36, 12);
    gl.enableVertexAttribArray(this.aLocations.normal);
    gl.vertexAttribPointer(this.aLocations.color, 3, gl.FLOAT, false, 36, 24);
    gl.enableVertexAttribArray(this.aLocations.color);
    
    const pickData = this._makePickData(geometry.vertices.length / 9, pickId);
    const pickBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, pickBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, pickData, gl.STATIC_DRAW);
    gl.vertexAttribPointer(this.aLocations.pickId, 1, gl.FLOAT, false, 0, 0);
    gl.enableVertexAttribArray(this.aLocations.pickId);
    
    gl.drawElements(gl.TRIANGLES, geometry.vertexCount, gl.UNSIGNED_SHORT, 0);
    
    gl.deleteBuffer(vertexBuffer);
    gl.deleteBuffer(indexBuffer);
    gl.deleteBuffer(pickBuffer);
  };

  PCBRender.prototype.frame = function() {
    const gl = this.gl;
    const now = Date.now();
    
    if (this.options.spin) {
      const delta = now - (this.lastTime || now);
      this.spinAngle += delta * 0.0003;
      this.camera.theta = this.spinAngle;
    }
    this.lastTime = now;
    
    this._updateCamera();
    
    gl.clearColor(0.05, 0.05, 0.08, 1.0);
    gl.clearDepth(1.0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    
    gl.useProgram(this.program);
    gl.uniform3fv(this.uLocations.lightDirection, this.lightDirection);
    gl.uniform3fv(this.uLocations.lightColor, this.lightColor);
    gl.uniform3fv(this.uLocations.ambientColor, this.ambientColor);
    gl.uniform3fv(this.uLocations.cameraPosition, this.cameraPosition);
    gl.uniform1f(this.uLocations.pickMode, 0.0);
    
    if (this.options.highlight) {
      gl.uniform1f(this.uLocations.highlightId, this._getComponentIndex(this.options.highlight));
      gl.uniform3fv(this.uLocations.highlightColor, this.highlightColor);
    } else {
      gl.uniform1f(this.uLocations.highlightId, -1.0);
    }
    
    // Draw substrate
    const outline = this.boardCore.outline || { width: 260, depth: 180, height: 1.6 };
    if (!this.slabGeom) this.slabGeom = makeSlabGeometry(outline.width, outline.depth, outline.height);
    const modelMatrix = mat4Identity();
    this._drawMesh(this.slabGeom, [0.1, 0.4, 0.1], modelMatrix, 0);
    
    // Draw mounting holes
    for (const hole of this.mountingHoles) {
      const pos = hole.position || { x: 0, y: 0, z: 0 };
      const size = hole.size || [3.5, 3.5, 1.6];
      const pickId = this._getComponentIndex(hole.id);
      const model = [
        1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
        pos.x, pos.y, this.boardSize[2] / 2 - size[2] / 2, 1
      ];
      if (!this.holeGeom) this.holeGeom = makeCylinderGeometry(size[0] / 2, this.boardSize[2] * 1.1, 12);
      this._drawMesh(this.holeGeom, [0.3, 0.3, 0.35], model, pickId);
    }
    
    // Draw components
    for (const comp of this.components) {
      const pos = comp.position || { x: 0, y: 0, z: 0 };
      const size = comp.size || [10, 10, 1];
      const color = comp.color || [0.8, 0.8, 0.8];
      const pickId = this._getComponentIndex(comp.id);
      const model = [
        size[0], 0, 0, 0, 0, size[1], 0, 0, 0, 0, size[2], 0,
        pos.x, pos.y, pos.z - size[2] / 2, 1
      ];
      
      let geom;
      if (comp.type === 'cylinder' || comp.type === 'crystal') {
        if (!this.cylGeom) this.cylGeom = makeCylinderGeometry(size[0] / 2, size[2], 16);
        geom = this.cylGeom;
      } else {
        if (!this.boxGeom) this.boxGeom = makeBoxGeometry(size[0], size[1], size[2]);
        geom = this.boxGeom;
      }
      
      this._drawMesh(geom, color, model, pickId);
    }
    
    // Draw traces
    if (this.options.showTraces) {
      this._drawTraces();
    }
    
    // Draw labels
    if (this.options.showLabels) {
      this._drawLabels();
    }
    
    if (this.options.spin) {
      requestAnimationFrame(() => this.frame());
    }
  };

  PCBRender.prototype._drawTraces = function() {
    const gl = this.gl;
    const copperColor = [0.72, 0.45, 0.2];
    const width = this.boardCore.outline ? (this.boardCore.outline.width || 260) : 260;
    
    for (const net of this.nets) {
      const fromComp = this._findComponent(net.from);
      const toComp = this._findComponent(net.to);
      if (!fromComp || !toComp) continue;
      
      const fromPos = fromComp.position || { x: 0, y: 0, z: 0 };
      const toPos = toComp.position || { x: 0, y: 0, z: 0 };
      const traceWidth = net.width || 1;
      
      // Create up to 3 segments
      const segments = 3;
      const points = [];
      for (let i = 0; i <= segments; i++) {
        const t = i / segments;
        points.push([
          fromPos.x + (toPos.x - fromPos.x) * t,
          fromPos.y + (toPos.y - fromPos.y) * t,
          fromPos.z + (toPos.z - fromPos.z) * t + traceWidth / 2
        ]);
      }
      
      // Draw line segments
      gl.lineWidth(traceWidth * 2);
      for (let i = 0; i < segments; i++) {
        const p0 = points[i];
        const p1 = points[i + 1];
        
        const lineVertices = new Float32Array([
          p0[0], p0[1], p0[2], 0, 0, 1, copperColor[0], copperColor[1], copperColor[2],
          p1[0], p1[1], p1[2], 0, 0, 1, copperColor[0], copperColor[1], copperColor[2]
        ]);
        
        const vertexBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, lineVertices, gl.STATIC_DRAW);
        
        gl.vertexAttribPointer(this.aLocations.position, 3, gl.FLOAT, false, 36, 0);
        gl.enableVertexAttribArray(this.aLocations.position);
        gl.vertexAttribPointer(this.aLocations.normal, 3, gl.FLOAT, false, 36, 12);
        gl.enableVertexAttribArray(this.aLocations.normal);
        gl.vertexAttribPointer(this.aLocations.color, 3, gl.FLOAT, false, 36, 24);
        gl.enableVertexAttribArray(this.aLocations.color);
        
        const pickBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, pickBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0]), gl.STATIC_DRAW);
        gl.vertexAttribPointer(this.aLocations.pickId, 1, gl.FLOAT, false, 0, 0);
        gl.enableVertexAttribArray(this.aLocations.pickId);
        
        // Use identity model for lines
        const mvp = mat4Multiply(this.mvpMatrix, mat4Identity());
        const normalMatrix = mat3FromMat4(mat4Identity());
        gl.uniformMatrix4fv(this.uLocations.mvp, false, mvp);
        gl.uniformMatrix3fv(this.uLocations.normalMatrix, false, normalMatrix);
        
        gl.drawArrays(gl.LINES, 0, 2);
        
        gl.deleteBuffer(vertexBuffer);
        gl.deleteBuffer(pickBuffer);
      }
      
      // Draw vias at bends (intermediate points)
      if (segments > 1) {
        for (let i = 1; i < segments; i++) {
          const viaPos = points[i];
          const viaRadius = traceWidth * 1.5;
          const viaHeight = traceWidth * 0.5;
          
          if (!this.viaGeom) this.viaGeom = makeCylinderGeometry(viaRadius, viaHeight, 8);
          
          const model = [
            1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
            viaPos[0], viaPos[1], viaPos[2], 1
          ];
          this._drawMesh(this.viaGeom, copperColor, model, 0);
        }
      }
    }
    gl.lineWidth(1);
  };

  PCBRender.prototype._drawLabels = function() {
    const ctx = this.overlayCanvas.getContext('2d');
    if (!ctx) return;
    
    const width = this.overlayCanvas.width;
    const height = this.overlayCanvas.height;
    ctx.clearRect(0, 0, width, height);
    
    const cameraDist = Math.sqrt(
      this.cameraPosition[0] * this.cameraPosition[0] +
      this.cameraPosition[1] * this.cameraPosition[1] +
      this.cameraPosition[2] * this.cameraPosition[2]
    );
    const maxDist = 800;
    const minDist = 200;
    let opacity = 1.0;
    if (cameraDist > minDist) {
      opacity = Math.max(0.1, 1.0 - (cameraDist - minDist) / (maxDist - minDist));
    }
    
    ctx.fillStyle = 'rgba(255, 255, 255, ' + opacity + ')';
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    
    const all = this.components.concat(this.mountingHoles);
    for (const comp of all) {
      const pos = comp.position || { x: 0, y: 0, z: 0 };
      const screenPos = this._projectToScreen(pos.x, pos.y, pos.z);
      if (screenPos && screenPos[0] >= 0 && screenPos[0] <= width && screenPos[1] >= 0 && screenPos[1] <= height) {
        ctx.fillText(comp.id, screenPos[0], screenPos[1]);
      }
    }
  };

  PCBRender.prototype._projectToScreen = function(x, y, z) {
    const gl = this.gl;
    const width = gl.canvas.width || gl.canvas.clientWidth;
    const height = gl.canvas.height || gl.canvas.clientHeight;
    
    const worldPos = [x, y, z, 1];
    const viewPos = [0, 0, 0, 0];
    const projPos = [0, 0, 0, 0];
    
    for (let i = 0; i < 4; i++) {
      for (let j = 0; j < 4; j++) {
        viewPos[i] += this.viewMatrix[i * 4 + j] * worldPos[j];
        projPos[i] += this.projectionMatrix[i * 4 + j] * viewPos[j];
      }
    }
    
    if (projPos[3] <= 0) return null;
    
    const ndc = [
      projPos[0] / projPos[3],
      projPos[1] / projPos[3],
      projPos[2] / projPos[3]
    ];
    
    if (ndc[0] < -1 || ndc[0] > 1 || ndc[1] < -1 || ndc[1] > 1 || ndc[2] < -1 || ndc[2] > 1) {
      return null;
    }
    
    return [
      (ndc[0] + 1) * 0.5 * width,
      (1 - (ndc[1] + 1) * 0.5) * height
    ];
  };

  PCBRender.prototype.pick = function(canvasX, canvasY) {
    const gl = this.gl;
    const width = gl.canvas.width || gl.canvas.clientWidth;
    const height = gl.canvas.height || gl.canvas.clientHeight;
    
    this._updateCamera();
    
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.pickFramebuffer);
    gl.viewport(0, 0, width, height);
    gl.clearColor(0, 0, 0, 1);
    gl.clearDepth(1.0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    
    gl.useProgram(this.program);
    gl.uniform1f(this.uLocations.pickMode, 1.0);
    gl.uniform1f(this.uLocations.highlightId, -1.0);
    
    // Draw for picking
    const outline = this.boardCore.outline || { width: 260, depth: 180, height: 1.6 };
    if (!this.slabGeom) this.slabGeom = makeSlabGeometry(outline.width, outline.depth, outline.height);
    this._drawMesh(this.slabGeom, [0.5, 0.5, 0.5], mat4Identity(), 0);
    
    for (const hole of this.mountingHoles) {
      const pos = hole.position || { x: 0, y: 0, z: 0 };
      const size = hole.size || [3.5, 3.5, 1.6];
      const pickId = this._getComponentIndex(hole.id);
      const model = [
        1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
        pos.x, pos.y, this.boardSize[2] / 2 - size[2] / 2, 1
      ];
      if (!this.holeGeom) this.holeGeom = makeCylinderGeometry(size[0] / 2, this.boardSize[2] * 1.1, 12);
      this._drawMesh(this.holeGeom, [0.5, 0.5, 0.5], model, pickId);
    }
    
    for (const comp of this.components) {
      const pos = comp.position || { x: 0, y: 0, z: 0 };
      const size = comp.size || [10, 10, 1];
      const pickId = this._getComponentIndex(comp.id);
      const model = [
        size[0], 0, 0, 0, 0, size[1], 0, 0, 0, 0, size[2], 0,
        pos.x, pos.y, pos.z - size[2] / 2, 1
      ];
      let geom = comp.type === 'cylinder' ? (this.cylGeom || (this.cylGeom = makeCylinderGeometry(size[0] / 2, size[2], 16)))
        : (this.boxGeom || (this.boxGeom = makeBoxGeometry(size[0], size[1], size[2])));
      this._drawMesh(geom, [0.5, 0.5, 0.5], model, pickId);
    }
    
    const pixels = new Uint8Array(4);
    gl.readPixels(canvasX, height - canvasY - 1, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.uniform1f(this.uLocations.pickMode, 0.0);
    
    const pickId = pixels[0] + pixels[1] * 256;
    if (pickId > 0) {
      const comp = this._getComponentByIndex(pickId);
      if (comp) return comp.id;
    }
    return null;
  };

  PCBRender.prototype.focusComponent = function(componentId) {
    const comp = this._findComponent(componentId);
    if (!comp) return;
    const pos = comp.position || { x: 0, y: 0, z: 0 };
    this.camera.target = [pos.x, pos.y, pos.z];
    this.camera.distance = 150;
    this.camera.pan = [0, 0];
    this.setOption('highlight', componentId);
  };

  PCBRender.prototype.resetView = function() {
    const outline = this.boardCore.outline || { width: 260, depth: 180, height: 1.6 };
    this.camera.target = [0, 0, outline.height / 2];
    this.camera.distance = 500;
    this.camera.theta = Math.PI / 4;
    this.camera.phi = Math.PI / 4;
    this.camera.pan = [0, 0];
    this.spinAngle = 0;
    this.setOption('highlight', null);
  };

  PCBRender.prototype.setOption = function(name, value) {
    switch (name) {
      case 'showTraces': this.options.showTraces = !!value; break;
      case 'showLabels': this.options.showLabels = !!value; break;
      case 'spin': 
        this.options.spin = !!value;
        if (value) this.lastTime = Date.now();
        break;
      case 'highlight': this.options.highlight = value === null ? null : String(value); break;
    }
  };

  PCBRender.prototype.getOption = function(name) {
    return this.options[name];
  };

  return PCBRender;
})();
