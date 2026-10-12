/**
 * graph-render.js
 *
 * WebGL2 Graph Renderer for Obsidian-style beta-graphview.
 * Self-contained ECMAScript 2020. No imports or external dependencies.
 */

(function () {
  'use strict';

  // Exactly six fixed colors chosen for the six note folders in VAULT_DATA
  const FOLDER_COLORS = {
    'Atlas': [0.23, 0.51, 0.96, 1.0],      // Blue
    'Chronicles': [0.96, 0.62, 0.04, 1.0], // Amber
    'Lexicon': [0.55, 0.36, 0.96, 1.0],    // Purple
    'Research': [0.06, 0.73, 0.51, 1.0],   // Emerald
    'Systems': [0.94, 0.27, 0.27, 1.0],    // Rose
    'Theory': [0.02, 0.71, 0.83, 1.0]      // Cyan
  };

  const SIX_FIXED_COLORS = [
    [0.23, 0.51, 0.96, 1.0],
    [0.96, 0.62, 0.04, 1.0],
    [0.55, 0.36, 0.96, 1.0],
    [0.06, 0.73, 0.51, 1.0],
    [0.94, 0.27, 0.27, 1.0],
    [0.02, 0.71, 0.83, 1.0]
  ];

  const GHOST_COLOR = [0.65, 0.67, 0.72, 1.0];
  const TAG_COLOR = [0.85, 0.45, 0.90, 1.0];
  const LINK_DEFAULT_COLOR = [0.42, 0.48, 0.58, 0.45];
  const LINK_LIT_COLOR = [0.82, 0.88, 0.98, 0.90];
  const LINK_DIMMED_COLOR = [0.20, 0.22, 0.28, 0.12];
  const BG_COLOR = [0.07, 0.07, 0.09, 1.0];

  const VALID_OPTIONS = new Set([
    'arrows',
    'nodeSize',
    'textFadeThreshold',
    'animate',
    'labels',
    'highlight',
    'focusDepth',
    'attachments',
    'unresolved',
    'orphans',
    'tags'
  ]);

  // --- 4x4 Matrix and Vector Mathematics ---

  function mat4Create() {
    const out = new Float32Array(16);
    out[0] = 1; out[5] = 1; out[10] = 1; out[15] = 1;
    return out;
  }

  function mat4Perspective(out, fovY, aspect, near, far) {
    const f = 1.0 / Math.tan(fovY / 2);
    const nf = 1.0 / (near - far);
    out[0] = f / aspect; out[1] = 0; out[2] = 0; out[3] = 0;
    out[4] = 0; out[5] = f; out[6] = 0; out[7] = 0;
    out[8] = 0; out[9] = 0; out[10] = (far + near) * nf; out[11] = -1;
    out[12] = 0; out[13] = 0; out[14] = (2 * far * near) * nf; out[15] = 0;
    return out;
  }

  function mat4LookAt(out, eye, target, up) {
    let z0 = eye[0] - target[0], z1 = eye[1] - target[1], z2 = eye[2] - target[2];
    let len = Math.hypot(z0, z1, z2) || 1e-6;
    z0 /= len; z1 /= len; z2 /= len;

    let x0 = up[1] * z2 - up[2] * z1;
    let x1 = up[2] * z0 - up[0] * z2;
    let x2 = up[0] * z1 - up[1] * z0;
    len = Math.hypot(x0, x1, x2) || 1e-6;
    x0 /= len; x1 /= len; x2 /= len;

    let y0 = z1 * x2 - z2 * x1;
    let y1 = z2 * x0 - z0 * x2;
    let y2 = z0 * x1 - z1 * x0;

    out[0] = x0; out[1] = y0; out[2] = z0; out[3] = 0;
    out[4] = x1; out[5] = y1; out[6] = z1; out[7] = 0;
    out[8] = x2; out[9] = y2; out[10] = z2; out[11] = 0;
    out[12] = -(x0 * eye[0] + x1 * eye[1] + x2 * eye[2]);
    out[13] = -(y0 * eye[0] + y1 * eye[1] + y2 * eye[2]);
    out[14] = -(z0 * eye[0] + z1 * eye[1] + z2 * eye[2]);
    out[15] = 1;
    return out;
  }

  function mat4Multiply(out, a, b) {
    for (let i = 0; i < 4; i++) {
      const ai0 = a[i], ai1 = a[i + 4], ai2 = a[i + 8], ai3 = a[i + 12];
      out[i] = ai0 * b[0] + ai1 * b[1] + ai2 * b[2] + ai3 * b[3];
      out[i + 4] = ai0 * b[4] + ai1 * b[5] + ai2 * b[6] + ai3 * b[7];
      out[i + 8] = ai0 * b[8] + ai1 * b[9] + ai2 * b[10] + ai3 * b[11];
      out[i + 12] = ai0 * b[12] + ai1 * b[13] + ai2 * b[14] + ai3 * b[15];
    }
    return out;
  }

  function mat4Invert(out, a) {
    const a00 = a[0], a01 = a[1], a02 = a[2], a03 = a[3];
    const a10 = a[4], a11 = a[5], a12 = a[6], a13 = a[7];
    const a20 = a[8], a21 = a[9], a22 = a[10], a23 = a[11];
    const a30 = a[12], a31 = a[13], a32 = a[14], a33 = a[15];

    const b00 = a00 * a11 - a01 * a10, b01 = a00 * a12 - a02 * a10, b02 = a00 * a13 - a03 * a10;
    const b03 = a01 * a12 - a02 * a11, b04 = a01 * a13 - a03 * a11, b05 = a02 * a13 - a03 * a12;
    const b06 = a20 * a31 - a21 * a30, b07 = a20 * a32 - a22 * a30, b08 = a20 * a33 - a23 * a30;
    const b09 = a21 * a32 - a22 * a31, b10 = a21 * a33 - a23 * a31, b11 = a22 * a33 - a23 * a32;

    let det = b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06;
    if (!det) return null;
    det = 1.0 / det;

    out[0] = (a11 * b11 - a12 * b10 + a13 * b09) * det;
    out[1] = (a02 * b10 - a01 * b11 - a03 * b09) * det;
    out[2] = (a31 * b05 - a32 * b04 + a33 * b03) * det;
    out[3] = (a22 * b04 - a21 * b05 - a23 * b03) * det;
    out[4] = (a12 * b08 - a10 * b11 - a13 * b07) * det;
    out[5] = (a00 * b11 - a02 * b08 + a03 * b07) * det;
    out[6] = (a32 * b02 - a30 * b05 - a33 * b01) * det;
    out[7] = (a20 * b05 - a22 * b02 + a23 * b01) * det;
    out[8] = (a10 * b10 - a11 * b08 + a13 * b06) * det;
    out[9] = (a01 * b08 - a00 * b10 - a03 * b06) * det;
    out[10] = (a30 * b04 - a31 * b02 + a33 * b00) * det;
    out[11] = (a21 * b02 - a20 * b04 - a23 * b00) * det;
    out[12] = (a11 * b07 - a10 * b09 - a12 * b06) * det;
    out[13] = (a00 * b09 - a01 * b07 + a02 * b06) * det;
    out[14] = (a31 * b01 - a30 * b03 - a32 * b00) * det;
    out[15] = (a20 * b03 - a21 * b01 + a22 * b00) * det;
    return out;
  }

  function transformVec4(v, m) {
    const x = v[0], y = v[1], z = v[2], w = v[3];
    const rx = m[0] * x + m[4] * y + m[8] * z + m[12] * w;
    const ry = m[1] * x + m[5] * y + m[9] * z + m[13] * w;
    const rz = m[2] * x + m[6] * y + m[10] * z + m[14] * w;
    const rw = m[3] * x + m[7] * y + m[11] * z + m[15] * w;
    const invW = rw !== 0 ? 1 / rw : 1;
    return [rx * invW, ry * invW, rz * invW];
  }

  function transformVec4ToClip(v, m) {
    const x = v[0], y = v[1], z = v[2], w = v[3];
    return {
      x: m[0] * x + m[4] * y + m[8] * z + m[12] * w,
      y: m[1] * x + m[5] * y + m[9] * z + m[13] * w,
      z: m[2] * x + m[6] * y + m[10] * z + m[14] * w,
      w: m[3] * x + m[7] * y + m[11] * z + m[15] * w
    };
  }

  // --- GLSL Shaders ---

  const NODE_VS_SOURCE = `#version 300 es
precision highp float;

in vec2 a_quad;
in vec3 a_center;
in float a_radius;
in vec4 a_color;
in float a_type;
in float a_dimmed;

uniform mat4 u_viewProjection;
uniform vec3 u_cameraRight;
uniform vec3 u_cameraUp;

out vec2 v_uv;
out vec4 v_color;
out float v_type;
out float v_dimmed;
out vec3 v_worldPos;
out vec3 v_center;
out float v_radius;

void main() {
  v_uv = a_quad;
  v_color = a_color;
  v_type = a_type;
  v_dimmed = a_dimmed;
  v_center = a_center;
  v_radius = a_radius;

  vec3 worldPos = a_center + (u_cameraRight * a_quad.x + u_cameraUp * a_quad.y) * a_radius;
  v_worldPos = worldPos;
  gl_Position = u_viewProjection * vec4(worldPos, 1.0);
}
`;

  const NODE_FS_SOURCE = `#version 300 es
precision highp float;

in vec2 v_uv;
in vec4 v_color;
in float v_type;
in float v_dimmed;
in vec3 v_worldPos;
in vec3 v_center;
in float v_radius;

uniform vec3 u_cameraPosition;
uniform vec3 u_cameraRight;
uniform vec3 u_cameraUp;
uniform vec3 u_cameraForward;
uniform vec4 u_fogColor;
uniform float u_fogNear;
uniform float u_fogFar;

out vec4 fragColor;

void main() {
  vec2 p = v_uv;
  vec3 baseColor = v_color.rgb;
  float alpha = v_color.a;

  if (v_dimmed > 0.5) {
    baseColor *= 0.35;
    alpha *= 0.25;
  }

  // Type 0: Shaded Sphere
  if (v_type < 0.5) {
    float r2 = dot(p, p);
    if (r2 > 1.0) {
      discard;
    }
    float z = sqrt(max(0.0, 1.0 - r2));
    vec3 normal = normalize(u_cameraRight * p.x + u_cameraUp * p.y - u_cameraForward * z);

    vec3 lightDir = normalize(vec3(0.5, 0.8, 0.6));
    float diff = max(dot(normal, lightDir), 0.0);
    vec3 viewDir = normalize(u_cameraPosition - v_worldPos);
    vec3 halfDir = normalize(lightDir + viewDir);
    float spec = pow(max(dot(normal, halfDir), 0.0), 32.0);

    float ambient = 0.45;
    vec3 shaded = baseColor * (ambient + 0.55 * diff) + vec3(0.35) * spec;

    float dist = length(v_center - u_cameraPosition);
    float fog = clamp((dist - u_fogNear) / max(u_fogFar - u_fogNear, 1e-4), 0.0, 1.0);
    vec3 fogged = mix(shaded, u_fogColor.rgb, fog);

    fragColor = vec4(fogged, alpha);
  }
  // Type 1: Ghost Node (Smaller hollow circle)
  else if (v_type < 1.5) {
    float r = length(p);
    if (r > 1.0 || r < 0.6) {
      discard;
    }
    float dist = length(v_center - u_cameraPosition);
    float fog = clamp((dist - u_fogNear) / max(u_fogFar - u_fogNear, 1e-4), 0.0, 1.0);
    vec3 fogged = mix(baseColor, u_fogColor.rgb, fog);

    fragColor = vec4(fogged, alpha);
  }
  // Type 2: Tag Node (Small hollow diamond)
  else {
    float d = abs(p.x) + abs(p.y);
    if (d > 1.0 || d < 0.6) {
      discard;
    }
    float dist = length(v_center - u_cameraPosition);
    float fog = clamp((dist - u_fogNear) / max(u_fogFar - u_fogNear, 1e-4), 0.0, 1.0);
    vec3 fogged = mix(baseColor, u_fogColor.rgb, fog);

    fragColor = vec4(fogged, alpha);
  }
}
`;

  const LINK_VS_SOURCE = `#version 300 es
precision highp float;

in vec3 a_position;
in vec4 a_color;

uniform mat4 u_viewProjection;
uniform vec3 u_cameraPosition;
uniform vec4 u_fogColor;
uniform float u_fogNear;
uniform float u_fogFar;

out vec4 v_color;

void main() {
  gl_Position = u_viewProjection * vec4(a_position, 1.0);
  float dist = length(a_position - u_cameraPosition);
  float fog = clamp((dist - u_fogNear) / max(u_fogFar - u_fogNear, 1e-4), 0.0, 1.0);
  vec3 fogged = mix(a_color.rgb, u_fogColor.rgb, fog);
  v_color = vec4(fogged, a_color.a * (1.0 - fog * 0.7));
}
`;

  const LINK_FS_SOURCE = `#version 300 es
precision highp float;

in vec4 v_color;
out vec4 fragColor;

void main() {
  fragColor = v_color;
}
`;

  function createShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const info = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error('Shader compilation error: ' + info);
    }
    return shader;
  }

  function createProgram(gl, vsSource, fsSource) {
    const vs = createShader(gl, gl.VERTEX_SHADER, vsSource);
    const fs = createShader(gl, gl.FRAGMENT_SHADER, fsSource);
    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      const info = gl.getProgramInfoLog(program);
      gl.deleteProgram(program);
      throw new Error('Program link error: ' + info);
    }
    return program;
  }

  // --- GraphRender Class ---

  class GraphRender {
    constructor(canvas, overlayCanvas, engine, vaultData) {
      this._canvas = canvas;
      this._overlayCanvas = overlayCanvas;
      this._engine = engine;
      this._vaultData = Array.isArray(vaultData) ? vaultData : (typeof VAULT_DATA !== 'undefined' ? VAULT_DATA : []);

      // Exactly the 11 options
      this._options = {
        arrows: false,
        nodeSize: 1.0,
        textFadeThreshold: 200,
        animate: true,
        labels: true,
        highlight: null,
        focusDepth: 0,
        attachments: true,
        unresolved: true,
        orphans: true,
        tags: true
      };

      this._highlightSet = new Set();
      this._focusedNodeId = null;
      this._hoveredNodeId = null;
      this._hoverCallback = null;

      // Camera: orbits origin with rotation, zoom distance and pan
      this.camera = {
        rotation: { yaw: 0.0, pitch: 0.2 },
        distance: 220,
        pan: { x: 0, y: 0, z: 0 }
      };

      // Internal matrices
      this._viewMatrix = mat4Create();
      this._projMatrix = mat4Create();
      this._viewProjMatrix = mat4Create();
      this._cameraPos = [0, 0, 220];
      this._cameraRight = [1, 0, 0];
      this._cameraUp = [0, 1, 0];
      this._cameraForward = [0, 0, -1];

      // Build vault metadata maps
      this._itemById = new Map();
      this._attachmentSet = new Set();
      this._orphanSet = new Set();
      this._inDegree = new Map();
      this._outDegree = new Map();
      this._initVaultMetadata();

      // WebGL2 context and buffers
      this._gl = null;
      this._ctx = null;
      this._initContexts();

      // Bind input events for camera orbit, pan, zoom, hover
      this._initInteraction();
    }

    _initVaultMetadata() {
      const noteIds = new Set();
      for (let i = 0; i < this._vaultData.length; i++) {
        const item = this._vaultData[i];
        if (item && item.id) {
          noteIds.add(item.id);
          this._itemById.set(item.id, item);
          this._inDegree.set(item.id, 0);
          this._outDegree.set(item.id, (item.links || []).length);

          // Attachment: files that have an extension in their name
          if (typeof item.name === 'string' && /\.[a-zA-Z0-9]+$/.test(item.name)) {
            this._attachmentSet.add(item.id);
          }
        }
      }

      // Count note-to-note incoming links
      for (let i = 0; i < this._vaultData.length; i++) {
        const item = this._vaultData[i];
        if (item && Array.isArray(item.links)) {
          for (let j = 0; j < item.links.length; j++) {
            const tgt = item.links[j];
            if (tgt && this._inDegree.has(tgt)) {
              this._inDegree.set(tgt, this._inDegree.get(tgt) + 1);
            }
          }
        }
      }

      // Orphan notes: notes in VAULT_DATA without any note-to-note links
      for (let i = 0; i < this._vaultData.length; i++) {
        const item = this._vaultData[i];
        if (item && item.id) {
          const inD = this._inDegree.get(item.id) || 0;
          const outD = this._outDegree.get(item.id) || 0;
          if (inD === 0 && outD === 0) {
            this._orphanSet.add(item.id);
          }
        }
      }
    }

    _initContexts() {
      if (this._canvas && typeof this._canvas.getContext === 'function') {
        try {
          this._gl = this._canvas.getContext('webgl2');
        } catch (_) {
          this._gl = null;
        }
      }

      if (this._overlayCanvas && typeof this._overlayCanvas.getContext === 'function') {
        try {
          this._ctx = this._overlayCanvas.getContext('2d');
        } catch (_) {
          this._ctx = null;
        }
      }

      if (this._gl) {
        this._initGLResources();
      }
    }

    _initGLResources() {
      const gl = this._gl;

      try {
        this._nodeProgram = createProgram(gl, NODE_VS_SOURCE, NODE_FS_SOURCE);
        this._nodeUniforms = {
          viewProj: gl.getUniformLocation(this._nodeProgram, 'u_viewProjection'),
          camRight: gl.getUniformLocation(this._nodeProgram, 'u_cameraRight'),
          camUp: gl.getUniformLocation(this._nodeProgram, 'u_cameraUp'),
          camForward: gl.getUniformLocation(this._nodeProgram, 'u_cameraForward'),
          camPos: gl.getUniformLocation(this._nodeProgram, 'u_cameraPosition'),
          fogColor: gl.getUniformLocation(this._nodeProgram, 'u_fogColor'),
          fogNear: gl.getUniformLocation(this._nodeProgram, 'u_fogNear'),
          fogFar: gl.getUniformLocation(this._nodeProgram, 'u_fogFar')
        };
        this._nodeAttribs = {
          quad: gl.getAttribLocation(this._nodeProgram, 'a_quad'),
          center: gl.getAttribLocation(this._nodeProgram, 'a_center'),
          radius: gl.getAttribLocation(this._nodeProgram, 'a_radius'),
          color: gl.getAttribLocation(this._nodeProgram, 'a_color'),
          type: gl.getAttribLocation(this._nodeProgram, 'a_type'),
          dimmed: gl.getAttribLocation(this._nodeProgram, 'a_dimmed')
        };

        this._linkProgram = createProgram(gl, LINK_VS_SOURCE, LINK_FS_SOURCE);
        this._linkUniforms = {
          viewProj: gl.getUniformLocation(this._linkProgram, 'u_viewProjection'),
          camPos: gl.getUniformLocation(this._linkProgram, 'u_cameraPosition'),
          fogColor: gl.getUniformLocation(this._linkProgram, 'u_fogColor'),
          fogNear: gl.getUniformLocation(this._linkProgram, 'u_fogNear'),
          fogFar: gl.getUniformLocation(this._linkProgram, 'u_fogFar')
        };
        this._linkAttribs = {
          position: gl.getAttribLocation(this._linkProgram, 'a_position'),
          color: gl.getAttribLocation(this._linkProgram, 'a_color')
        };

        // Quad buffer for nodes
        this._quadBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, this._quadBuffer);
        const quadData = new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]);
        gl.bufferData(gl.ARRAY_BUFFER, quadData, gl.STATIC_DRAW);

        this._nodeInstanceBuffer = gl.createBuffer();
        this._linkBuffer = gl.createBuffer();
        this._coneBuffer = gl.createBuffer();

        // Node VAO
        this._nodeVAO = gl.createVertexArray();
        gl.bindVertexArray(this._nodeVAO);

        gl.bindBuffer(gl.ARRAY_BUFFER, this._quadBuffer);
        gl.enableVertexAttribArray(this._nodeAttribs.quad);
        gl.vertexAttribPointer(this._nodeAttribs.quad, 2, gl.FLOAT, false, 0, 0);

        gl.bindBuffer(gl.ARRAY_BUFFER, this._nodeInstanceBuffer);
        const stride = 10 * 4; // 10 floats = 40 bytes

        gl.enableVertexAttribArray(this._nodeAttribs.center);
        gl.vertexAttribPointer(this._nodeAttribs.center, 3, gl.FLOAT, false, stride, 0);
        gl.vertexAttribDivisor(this._nodeAttribs.center, 1);

        gl.enableVertexAttribArray(this._nodeAttribs.radius);
        gl.vertexAttribPointer(this._nodeAttribs.radius, 1, gl.FLOAT, false, stride, 12);
        gl.vertexAttribDivisor(this._nodeAttribs.radius, 1);

        gl.enableVertexAttribArray(this._nodeAttribs.color);
        gl.vertexAttribPointer(this._nodeAttribs.color, 4, gl.FLOAT, false, stride, 16);
        gl.vertexAttribDivisor(this._nodeAttribs.color, 1);

        gl.enableVertexAttribArray(this._nodeAttribs.type);
        gl.vertexAttribPointer(this._nodeAttribs.type, 1, gl.FLOAT, false, stride, 32);
        gl.vertexAttribDivisor(this._nodeAttribs.type, 1);

        gl.enableVertexAttribArray(this._nodeAttribs.dimmed);
        gl.vertexAttribPointer(this._nodeAttribs.dimmed, 1, gl.FLOAT, false, stride, 36);
        gl.vertexAttribDivisor(this._nodeAttribs.dimmed, 1);

        // Link VAO
        this._linkVAO = gl.createVertexArray();
        gl.bindVertexArray(this._linkVAO);
        gl.bindBuffer(gl.ARRAY_BUFFER, this._linkBuffer);
        const linkStride = 7 * 4; // 3 pos + 4 color = 28 bytes
        gl.enableVertexAttribArray(this._linkAttribs.position);
        gl.vertexAttribPointer(this._linkAttribs.position, 3, gl.FLOAT, false, linkStride, 0);
        gl.enableVertexAttribArray(this._linkAttribs.color);
        gl.vertexAttribPointer(this._linkAttribs.color, 4, gl.FLOAT, false, linkStride, 12);

        // Cone VAO
        this._coneVAO = gl.createVertexArray();
        gl.bindVertexArray(this._coneVAO);
        gl.bindBuffer(gl.ARRAY_BUFFER, this._coneBuffer);
        gl.enableVertexAttribArray(this._linkAttribs.position);
        gl.vertexAttribPointer(this._linkAttribs.position, 3, gl.FLOAT, false, linkStride, 0);
        gl.enableVertexAttribArray(this._linkAttribs.color);
        gl.vertexAttribPointer(this._linkAttribs.color, 4, gl.FLOAT, false, linkStride, 12);

        gl.bindVertexArray(null);
      } catch (err) {
        // If WebGL fails to initialize (mock environment), continue gracefully
        this._gl = null;
      }
    }

    _initInteraction() {
      const target = this._overlayCanvas || this._canvas;
      if (!target || typeof target.addEventListener !== 'function') {
        return;
      }

      let isDragging = false;
      let dragButton = 0;
      let isShift = false;
      let lastX = 0;
      let lastY = 0;

      const getCoords = (e) => {
        if (typeof target.getBoundingClientRect === 'function') {
          const rect = target.getBoundingClientRect();
          return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
          };
        }
        return { x: e.offsetX || 0, y: e.offsetY || 0 };
      };

      target.addEventListener('pointerdown', (e) => {
        isDragging = true;
        dragButton = e.button;
        isShift = Boolean(e.shiftKey);
        lastX = e.clientX;
        lastY = e.clientY;
      });

      target.addEventListener('pointermove', (e) => {
        const coords = getCoords(e);
        if (isDragging) {
          const dx = e.clientX - lastX;
          const dy = e.clientY - lastY;
          lastX = e.clientX;
          lastY = e.clientY;

          if (dragButton === 1 || dragButton === 2 || isShift || e.shiftKey) {
            // Pan camera along right and up axes
            const panSpeed = this.camera.distance * 0.0015;
            this.camera.pan.x += (-this._cameraRight[0] * dx + this._cameraUp[0] * dy) * panSpeed;
            this.camera.pan.y += (-this._cameraRight[1] * dx + this._cameraUp[1] * dy) * panSpeed;
            this.camera.pan.z += (-this._cameraRight[2] * dx + this._cameraUp[2] * dy) * panSpeed;
          } else {
            // Orbit camera
            this.camera.rotation.yaw -= dx * 0.006;
            this.camera.rotation.pitch = Math.max(-1.48, Math.min(1.48, this.camera.rotation.pitch + dy * 0.006));
          }
        }

        // Hover test
        const hitId = this.pick(coords.x, coords.y);
        this._setHoveredNode(hitId);
      });

      const onPointerUp = () => {
        isDragging = false;
      };

      target.addEventListener('pointerup', onPointerUp);
      target.addEventListener('pointercancel', onPointerUp);

      target.addEventListener('pointerleave', () => {
        isDragging = false;
        this._setHoveredNode(null);
      });

      target.addEventListener('wheel', (e) => {
        if (typeof e.preventDefault === 'function') {
          e.preventDefault();
        }
        this.camera.distance *= Math.exp(e.deltaY * 0.001);
        this.camera.distance = Math.max(10, Math.min(3000, this.camera.distance));
      }, { passive: false });
    }

    _setHoveredNode(nodeId) {
      const normId = nodeId || null;
      if (this._hoveredNodeId !== normId) {
        this._hoveredNodeId = normId;
        if (typeof this._hoverCallback === 'function') {
          try {
            this._hoverCallback(this._hoveredNodeId);
          } catch (_) {}
        }
      }
    }

    // --- Public API ---

    onHover(callback) {
      this._hoverCallback = typeof callback === 'function' ? callback : null;
    }

    focus(nodeId) {
      this._focusedNodeId = nodeId != null ? String(nodeId) : null;
    }

    clearFocus() {
      this._focusedNodeId = null;
    }

    setOption(name, value) {
      if (!VALID_OPTIONS.has(name)) {
        return;
      }

      if (name === 'arrows') {
        this._options.arrows = Boolean(value);
      } else if (name === 'nodeSize') {
        const num = Number(value);
        if (!Number.isNaN(num)) this._options.nodeSize = num;
      } else if (name === 'textFadeThreshold') {
        const num = Number(value);
        if (!Number.isNaN(num)) this._options.textFadeThreshold = num;
      } else if (name === 'animate') {
        this._options.animate = Boolean(value);
      } else if (name === 'labels') {
        this._options.labels = Boolean(value);
      } else if (name === 'highlight') {
        this._options.highlight = value;
        this._updateHighlightSet(value);
      } else if (name === 'focusDepth') {
        const num = parseInt(value, 10);
        this._options.focusDepth = Number.isNaN(num) ? 0 : Math.max(0, num);
      } else if (name === 'attachments') {
        this._options.attachments = Boolean(value);
      } else if (name === 'unresolved') {
        this._options.unresolved = Boolean(value);
      } else if (name === 'orphans') {
        this._options.orphans = Boolean(value);
      } else if (name === 'tags') {
        this._options.tags = Boolean(value);
      }
    }

    getOption(name) {
      if (VALID_OPTIONS.has(name)) {
        return this._options[name];
      }
      return undefined;
    }

    _updateHighlightSet(val) {
      this._highlightSet.clear();
      if (!val) return;
      if (Array.isArray(val)) {
        for (let i = 0; i < val.length; i++) {
          if (val[i] != null) this._highlightSet.add(String(val[i]));
        }
      } else if (typeof val === 'string' && val.length > 0) {
        this._highlightSet.add(val);
      } else if (val instanceof Set) {
        for (const item of val) {
          if (item != null) this._highlightSet.add(String(item));
        }
      }
    }

    _updateMatrices() {
      const w = this._canvas ? (this._canvas.clientWidth || this._canvas.width || 800) : 800;
      const h = this._canvas ? (this._canvas.clientHeight || this._canvas.height || 600) : 600;
      const aspect = Math.max(0.1, w / h);

      const yaw = this.camera.rotation.yaw || 0;
      const pitch = this.camera.rotation.pitch || 0;
      const dist = this.camera.distance || 220;
      const pan = this.camera.pan || { x: 0, y: 0, z: 0 };

      const cosPitch = Math.cos(pitch);
      const sinPitch = Math.sin(pitch);
      const sinYaw = Math.sin(yaw);
      const cosYaw = Math.cos(yaw);

      const cx = (pan.x || 0) + dist * cosPitch * sinYaw;
      const cy = (pan.y || 0) + dist * sinPitch;
      const cz = (pan.z || 0) + dist * cosPitch * cosYaw;

      this._cameraPos[0] = cx;
      this._cameraPos[1] = cy;
      this._cameraPos[2] = cz;

      const target = [pan.x || 0, pan.y || 0, pan.z || 0];
      const up = [0, 1, 0];

      mat4LookAt(this._viewMatrix, this._cameraPos, target, up);
      mat4Perspective(this._projMatrix, Math.PI / 4, aspect, 1.0, 5000.0);
      mat4Multiply(this._viewProjMatrix, this._projMatrix, this._viewMatrix);

      // Camera vectors in world space
      this._cameraRight[0] = this._viewMatrix[0];
      this._cameraRight[1] = this._viewMatrix[4];
      this._cameraRight[2] = this._viewMatrix[8];

      this._cameraUp[0] = this._viewMatrix[1];
      this._cameraUp[1] = this._viewMatrix[5];
      this._cameraUp[2] = this._viewMatrix[9];

      this._cameraForward[0] = -this._viewMatrix[2];
      this._cameraForward[1] = -this._viewMatrix[6];
      this._cameraForward[2] = -this._viewMatrix[10];
    }

    _getNodeRadius(node) {
      const nodeSize = this._options.nodeSize || 1.0;
      if (node.ghost) {
        return 2.2 * nodeSize;
      }
      if (node.tag) {
        return 2.5 * nodeSize;
      }
      const links = node.links != null ? node.links : (node.linkCount || 0);
      return (3.0 + 1.2 * Math.sqrt(links)) * nodeSize;
    }

    _getNodeColor(node) {
      if (node.ghost) {
        return GHOST_COLOR;
      }
      if (node.tag) {
        return TAG_COLOR;
      }
      const item = this._itemById.get(node.id);
      const folder = item ? item.folder : null;
      if (folder && Object.prototype.hasOwnProperty.call(FOLDER_COLORS, folder)) {
        return FOLDER_COLORS[folder];
      }
      // Fixed deterministic color chosen by folder
      let h = 0;
      const s = String(folder || node.id || '');
      for (let i = 0; i < s.length; i++) {
        h = (h * 31 + s.charCodeAt(i)) & 0xffff;
      }
      return SIX_FIXED_COLORS[Math.abs(h) % 6];
    }

    _getNodeType(node) {
      if (node.ghost) return 1.0;
      if (node.tag) return 2.0;
      return 0.0;
    }

    _computeVisibleGraph() {
      let rawNodes = [];
      if (this._engine && typeof this._engine.positions === 'function') {
        rawNodes = this._engine.positions();
      } else if (this._engine && Array.isArray(this._engine._nodes)) {
        rawNodes = this._engine._nodes;
      }

      const nodeMap = new Map();
      for (let i = 0; i < rawNodes.length; i++) {
        nodeMap.set(rawNodes[i].id, rawNodes[i]);
      }

      // Adjacency from engine links or vault data
      const rawLinks = (this._engine && Array.isArray(this._engine._links)) ? this._engine._links : [];
      const adj = new Map();
      for (let i = 0; i < rawNodes.length; i++) {
        adj.set(rawNodes[i].id, []);
      }

      for (let i = 0; i < rawLinks.length; i++) {
        const l = rawLinks[i];
        const sId = l.source ? l.source.id : null;
        const tId = l.target ? l.target.id : null;
        if (sId && tId) {
          if (adj.has(sId)) adj.get(sId).push(tId);
          if (adj.has(tId)) adj.get(tId).push(sId);
        }
      }

      // 1. Filter switches
      // attachments hides or shows attachment notes
      // unresolved switch hides or shows ghost nodes
      // orphans switch hides or shows orphan notes
      // tags switch hides or shows tag nodes
      const passesFilter = (node) => {
        if (node.ghost) {
          return this._options.unresolved;
        }
        if (node.tag) {
          return this._options.tags;
        }
        if (this._attachmentSet.has(node.id) && !this._options.attachments) {
          return false;
        }
        if (this._orphanSet.has(node.id) && !this._options.orphans) {
          return false;
        }
        return true;
      };

      // 2. Focus depth restriction
      let focusAllowed = null;
      if (this._focusedNodeId && this._options.focusDepth > 0 && nodeMap.has(this._focusedNodeId)) {
        focusAllowed = new Set();
        const queue = [{ id: this._focusedNodeId, dist: 0 }];
        focusAllowed.add(this._focusedNodeId);

        while (queue.length > 0) {
          const { id, dist } = queue.shift();
          if (dist < this._options.focusDepth) {
            const nbrs = adj.get(id) || [];
            for (let j = 0; j < nbrs.length; j++) {
              const nbr = nbrs[j];
              if (!focusAllowed.has(nbr)) {
                focusAllowed.add(nbr);
                queue.push({ id: nbr, dist: dist + 1 });
              }
            }
          }
        }
      }

      const visibleNodes = [];
      const visibleNodeSet = new Set();
      for (let i = 0; i < rawNodes.length; i++) {
        const n = rawNodes[i];
        if (!passesFilter(n)) continue;
        if (focusAllowed && !focusAllowed.has(n.id)) continue;
        visibleNodes.push(n);
        visibleNodeSet.add(n.id);
      }

      // 3. Visible links: both endpoints must be visible
      const visibleLinks = [];
      for (let i = 0; i < rawLinks.length; i++) {
        const l = rawLinks[i];
        const sId = l.source ? l.source.id : null;
        const tId = l.target ? l.target.id : null;
        if (sId && tId && visibleNodeSet.has(sId) && visibleNodeSet.has(tId)) {
          const srcNode = nodeMap.get(sId);
          const tgtNode = nodeMap.get(tId);
          if (srcNode && tgtNode) {
            visibleLinks.push({ source: srcNode, target: tgtNode });
          }
        }
      }

      // 4. Highlight: lights those nodes, their direct neighbors and their links while dimming all other nodes and links
      const hasHighlight = this._highlightSet.size > 0;
      const litNodes = new Set();

      if (hasHighlight) {
        for (const hid of this._highlightSet) {
          litNodes.add(hid);
          const nbrs = adj.get(hid) || [];
          for (let j = 0; j < nbrs.length; j++) {
            litNodes.add(nbrs[j]);
          }
        }
      }

      const nodeDimmedMap = new Map();
      for (let i = 0; i < visibleNodes.length; i++) {
        const n = visibleNodes[i];
        const isDimmed = hasHighlight ? !litNodes.has(n.id) : false;
        nodeDimmedMap.set(n.id, isDimmed);
      }

      const linkDimmedList = new Array(visibleLinks.length);
      for (let i = 0; i < visibleLinks.length; i++) {
        const l = visibleLinks[i];
        let isLit = false;
        if (hasHighlight) {
          isLit = this._highlightSet.has(l.source.id) || this._highlightSet.has(l.target.id);
        } else {
          isLit = true;
        }
        linkDimmedList[i] = !isLit;
      }

      return {
        nodes: visibleNodes,
        links: visibleLinks,
        nodeDimmed: nodeDimmedMap,
        linkDimmed: linkDimmedList
      };
    }

    _renderWebGL(graph) {
      const gl = this._gl;
      if (!gl) return;

      const w = this._canvas.clientWidth || this._canvas.width || 800;
      const h = this._canvas.clientHeight || this._canvas.height || 600;

      if (this._canvas.width !== w || this._canvas.height !== h) {
        this._canvas.width = w;
        this._canvas.height = h;
      }

      gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

      gl.clearColor(BG_COLOR[0], BG_COLOR[1], BG_COLOR[2], BG_COLOR[3]);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

      const fogNear = this.camera.distance * 0.4;
      const fogFar = this.camera.distance * 2.4;

      // 1. Draw Links
      const links = graph.links;
      if (links.length > 0) {
        gl.useProgram(this._linkProgram);
        gl.uniformMatrix4fv(this._linkUniforms.viewProj, false, this._viewProjMatrix);
        gl.uniform3fv(this._linkUniforms.camPos, this._cameraPos);
        gl.uniform4fv(this._linkUniforms.fogColor, BG_COLOR);
        gl.uniform1f(this._linkUniforms.fogNear, fogNear);
        gl.uniform1f(this._linkUniforms.fogFar, fogFar);

        const lineVerts = new Float32Array(links.length * 2 * 7); // 2 vertices * 7 floats (3 pos + 4 color)
        let ptr = 0;
        for (let i = 0; i < links.length; i++) {
          const l = links[i];
          const isDim = graph.linkDimmed[i];
          const col = isDim ? LINK_DIMMED_COLOR : (this._highlightSet.size > 0 ? LINK_LIT_COLOR : LINK_DEFAULT_COLOR);

          lineVerts[ptr++] = l.source.x;
          lineVerts[ptr++] = l.source.y;
          lineVerts[ptr++] = l.source.z;
          lineVerts[ptr++] = col[0];
          lineVerts[ptr++] = col[1];
          lineVerts[ptr++] = col[2];
          lineVerts[ptr++] = col[3];

          lineVerts[ptr++] = l.target.x;
          lineVerts[ptr++] = l.target.y;
          lineVerts[ptr++] = l.target.z;
          lineVerts[ptr++] = col[0];
          lineVerts[ptr++] = col[1];
          lineVerts[ptr++] = col[2];
          lineVerts[ptr++] = col[3];
        }

        gl.bindVertexArray(this._linkVAO);
        gl.bindBuffer(gl.ARRAY_BUFFER, this._linkBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, lineVerts, gl.DYNAMIC_DRAW);
        gl.drawArrays(gl.LINES, 0, links.length * 2);

        // 2. Arrows (Cones at target end of every link line)
        if (this._options.arrows) {
          const segs = 8;
          const vertsPerCone = segs * 3;
          const coneVerts = new Float32Array(links.length * vertsPerCone * 7);
          let cPtr = 0;

          for (let i = 0; i < links.length; i++) {
            const l = links[i];
            const isDim = graph.linkDimmed[i];
            const col = isDim ? LINK_DIMMED_COLOR : (this._highlightSet.size > 0 ? LINK_LIT_COLOR : LINK_DEFAULT_COLOR);
            const baseCol = [col[0] * 0.7, col[1] * 0.7, col[2] * 0.7, col[3]];

            const sx = l.source.x, sy = l.source.y, sz = l.source.z;
            const tx = l.target.x, ty = l.target.y, tz = l.target.z;
            const dx = tx - sx, dy = ty - sy, dz = tz - sz;
            const len = Math.hypot(dx, dy, dz) || 1e-6;
            const dirX = dx / len, dirY = dy / len, dirZ = dz / len;

            const tgtRadius = this._getNodeRadius(l.target);
            const coneLen = Math.min(6.0 * this._options.nodeSize, len * 0.35);
            const coneRadius = Math.min(2.0 * this._options.nodeSize, len * 0.16);

            const tipX = tx - dirX * tgtRadius;
            const tipY = ty - dirY * tgtRadius;
            const tipZ = tz - dirZ * tgtRadius;

            const baseX = tipX - dirX * coneLen;
            const baseY = tipY - dirY * coneLen;
            const baseZ = tipZ - dirZ * coneLen;

            let uX, uY, uZ;
            if (Math.abs(dirY) < 0.9) {
              uX = -dirZ; uY = 0; uZ = dirX;
            } else {
              uX = 0; uY = -dirZ; uZ = dirY;
            }
            const uLen = Math.hypot(uX, uY, uZ) || 1e-6;
            uX /= uLen; uY /= uLen; uZ /= uLen;

            const vX = dirY * uZ - dirZ * uY;
            const vY = dirZ * uX - dirX * uZ;
            const vZ = dirX * uY - dirY * uX;

            for (let s = 0; s < segs; s++) {
              const a1 = (s / segs) * Math.PI * 2;
              const a2 = ((s + 1) / segs) * Math.PI * 2;
              const cos1 = Math.cos(a1), sin1 = Math.sin(a1);
              const cos2 = Math.cos(a2), sin2 = Math.sin(a2);

              const p1x = baseX + coneRadius * (cos1 * uX + sin1 * vX);
              const p1y = baseY + coneRadius * (cos1 * uY + sin1 * vY);
              const p1z = baseZ + coneRadius * (cos1 * uZ + sin1 * vZ);

              const p2x = baseX + coneRadius * (cos2 * uX + sin2 * vX);
              const p2y = baseY + coneRadius * (cos2 * uY + sin2 * vY);
              const p2z = baseZ + coneRadius * (cos2 * uZ + sin2 * vZ);

              // Triangle tip, p1, p2
              coneVerts[cPtr++] = tipX; coneVerts[cPtr++] = tipY; coneVerts[cPtr++] = tipZ;
              coneVerts[cPtr++] = col[0]; coneVerts[cPtr++] = col[1]; coneVerts[cPtr++] = col[2]; coneVerts[cPtr++] = col[3];

              coneVerts[cPtr++] = p1x; coneVerts[cPtr++] = p1y; coneVerts[cPtr++] = p1z;
              coneVerts[cPtr++] = baseCol[0]; coneVerts[cPtr++] = baseCol[1]; coneVerts[cPtr++] = baseCol[2]; coneVerts[cPtr++] = baseCol[3];

              coneVerts[cPtr++] = p2x; coneVerts[cPtr++] = p2y; coneVerts[cPtr++] = p2z;
              coneVerts[cPtr++] = baseCol[0]; coneVerts[cPtr++] = baseCol[1]; coneVerts[cPtr++] = baseCol[2]; coneVerts[cPtr++] = baseCol[3];
            }
          }

          gl.bindVertexArray(this._coneVAO);
          gl.bindBuffer(gl.ARRAY_BUFFER, this._coneBuffer);
          gl.bufferData(gl.ARRAY_BUFFER, coneVerts, gl.DYNAMIC_DRAW);
          gl.drawArrays(gl.TRIANGLES, 0, links.length * vertsPerCone);
        }
      }

      // 3. Draw Nodes (Instanced billboard quads)
      const nodes = graph.nodes;
      if (nodes.length > 0) {
        gl.useProgram(this._nodeProgram);
        gl.uniformMatrix4fv(this._nodeUniforms.viewProj, false, this._viewProjMatrix);
        gl.uniform3fv(this._nodeUniforms.camRight, this._cameraRight);
        gl.uniform3fv(this._nodeUniforms.camUp, this._cameraUp);
        gl.uniform3fv(this._nodeUniforms.camForward, this._cameraForward);
        gl.uniform3fv(this._nodeUniforms.camPos, this._cameraPos);
        gl.uniform4fv(this._nodeUniforms.fogColor, BG_COLOR);
        gl.uniform1f(this._nodeUniforms.fogNear, fogNear);
        gl.uniform1f(this._nodeUniforms.fogFar, fogFar);

        const instanceData = new Float32Array(nodes.length * 10);
        let iPtr = 0;
        for (let i = 0; i < nodes.length; i++) {
          const n = nodes[i];
          const radius = this._getNodeRadius(n);
          const col = this._getNodeColor(n);
          const type = this._getNodeType(n);
          const isDim = graph.nodeDimmed.get(n.id) ? 1.0 : 0.0;

          instanceData[iPtr++] = n.x;
          instanceData[iPtr++] = n.y;
          instanceData[iPtr++] = n.z;
          instanceData[iPtr++] = radius;
          instanceData[iPtr++] = col[0];
          instanceData[iPtr++] = col[1];
          instanceData[iPtr++] = col[2];
          instanceData[iPtr++] = col[3];
          instanceData[iPtr++] = type;
          instanceData[iPtr++] = isDim;
        }

        gl.bindVertexArray(this._nodeVAO);
        gl.bindBuffer(gl.ARRAY_BUFFER, this._nodeInstanceBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, instanceData, gl.DYNAMIC_DRAW);
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, nodes.length);
      }

      gl.bindVertexArray(null);
    }

    _renderOverlayText(graph) {
      const ctx = this._ctx;
      if (!ctx || !this._overlayCanvas) return;

      const w = this._canvas.clientWidth || this._canvas.width || 800;
      const h = this._canvas.clientHeight || this._canvas.height || 600;

      if (this._overlayCanvas.width !== w || this._overlayCanvas.height !== h) {
        this._overlayCanvas.width = w;
        this._overlayCanvas.height = h;
      }

      ctx.clearRect(0, 0, w, h);

      // labels option shows or hides all name text
      if (!this._options.labels) {
        return;
      }

      const threshold = this.camera.distance > 0 ? (this._options.textFadeThreshold || 200) : 200;
      const halfThresh = 0.5 * threshold;
      const twiceThresh = 2.0 * threshold;
      const span = twiceThresh - halfThresh;

      const fovY = Math.PI / 4;
      const projFactor = h / (2 * Math.tan(fovY / 2));

      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';

      const nodes = graph.nodes;
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];

        // Screen-space text whose opacity fades to zero between twice and half
        // the text fade threshold relative to camera distance
        const dx = n.x - this._cameraPos[0];
        const dy = n.y - this._cameraPos[1];
        const dz = n.z - this._cameraPos[2];
        const dist = Math.hypot(dx, dy, dz);

        let opacity = 1.0;
        if (dist >= twiceThresh) {
          opacity = 0.0;
        } else if (dist <= halfThresh) {
          opacity = 1.0;
        } else {
          opacity = (twiceThresh - dist) / span;
        }

        const isDim = graph.nodeDimmed.get(n.id);
        if (isDim) {
          opacity *= 0.2;
        }

        if (opacity <= 0.01) {
          continue;
        }

        const clip = transformVec4ToClip([n.x, n.y, n.z, 1.0], this._viewProjMatrix);
        if (clip.w <= 0.001) continue;

        const ndcX = clip.x / clip.w;
        const ndcY = clip.y / clip.w;
        if (ndcX < -1.1 || ndcX > 1.1 || ndcY < -1.1 || ndcY > 1.1) continue;

        const sx = (ndcX + 1) * 0.5 * w;
        const sy = (1 - ndcY) * 0.5 * h;

        const r = this._getNodeRadius(n);
        const screenR = (r / clip.w) * projFactor;

        // Display name
        let name = n.id;
        if (n.tag) {
          name = n.id; // Tag name
        } else {
          const item = this._itemById.get(n.id);
          if (item && item.name) {
            name = item.name;
          }
        }

        ctx.fillStyle = `rgba(224, 228, 238, ${opacity.toFixed(3)})`;
        ctx.fillText(name, sx, sy + screenR + 3);
      }
    }

    frame() {
      // When the animate option is on it first calls the engine's tick
      if (this._options.animate && this._engine && typeof this._engine.tick === 'function') {
        this._engine.tick();
      }

      this._updateMatrices();
      const graph = this._computeVisibleGraph();
      this._renderWebGL(graph);
      this._renderOverlayText(graph);
    }

    pick(x, y) {
      const w = this._canvas ? (this._canvas.clientWidth || this._canvas.width || 800) : 800;
      const h = this._canvas ? (this._canvas.clientHeight || this._canvas.height || 600) : 600;

      this._updateMatrices();
      const graph = this._computeVisibleGraph();
      const nodes = graph.nodes;

      const fovY = Math.PI / 4;
      const projFactor = h / (2 * Math.tan(fovY / 2));

      let closestId = null;
      let minDepth = Infinity;

      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        const clip = transformVec4ToClip([n.x, n.y, n.z, 1.0], this._viewProjMatrix);
        if (clip.w <= 0) continue;

        const ndcX = clip.x / clip.w;
        const ndcY = clip.y / clip.w;
        const sx = (ndcX + 1) * 0.5 * w;
        const sy = (1 - ndcY) * 0.5 * h;

        const r = this._getNodeRadius(n);
        const screenR = Math.max((r / clip.w) * projFactor, 8);

        const dx = sx - x;
        const dy = sy - y;
        if (dx * dx + dy * dy <= screenR * screenR) {
          if (clip.w < minDepth) {
            minDepth = clip.w;
            closestId = n.id;
          }
        }
      }

      return closestId;
    }

    unproject(x, y) {
      const w = this._canvas ? (this._canvas.clientWidth || this._canvas.width || 800) : 800;
      const h = this._canvas ? (this._canvas.clientHeight || this._canvas.height || 600) : 600;

      this._updateMatrices();

      const ndcX = (x / w) * 2 - 1;
      const ndcY = 1 - (y / h) * 2;

      const invVP = mat4Invert(new Float32Array(16), this._viewProjMatrix);
      if (!invVP) {
        const zeroPt = [0, 0, 0];
        zeroPt.x = 0; zeroPt.y = 0; zeroPt.z = 0;
        return zeroPt;
      }

      const near = transformVec4([ndcX, ndcY, -1, 1], invVP);
      const far = transformVec4([ndcX, ndcY, 1, 1], invVP);

      const rx = far[0] - near[0];
      const ry = far[1] - near[1];
      const rz = far[2] - near[2];
      const rlen = Math.hypot(rx, ry, rz) || 1e-6;
      const dir = [rx / rlen, ry / rlen, rz / rlen];

      // Plane through the origin facing the camera:
      // Normal of the plane is unit vector pointing from origin toward camera position
      let nx = this._cameraPos[0];
      let ny = this._cameraPos[1];
      let nz = this._cameraPos[2];
      const nlen = Math.hypot(nx, ny, nz) || 1e-6;
      nx /= nlen;
      ny /= nlen;
      nz /= nlen;

      // Plane equation: n . p = 0
      // Intersect ray p(t) = near + t * dir:
      // n . (near + t * dir) = 0 => t = -(n . near) / (n . dir)
      const dotNear = nx * near[0] + ny * near[1] + nz * near[2];
      const dotDir = nx * dir[0] + ny * dir[1] + nz * dir[2];
      const t = Math.abs(dotDir) > 1e-7 ? -dotNear / dotDir : 0;

      const hitX = near[0] + t * dir[0];
      const hitY = near[1] + t * dir[1];
      const hitZ = near[2] + t * dir[2];

      const res = [hitX, hitY, hitZ];
      res.x = hitX;
      res.y = hitY;
      res.z = hitZ;
      return res;
    }
  }

  // Global exports
  if (typeof globalThis !== 'undefined') {
    globalThis.GraphRender = GraphRender;
  }
  if (typeof window !== 'undefined') {
    window.GraphRender = GraphRender;
  }
})();
