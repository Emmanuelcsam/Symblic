/**
 * graph-input.js
 *
 * Input controller for Obsidian-style beta-graphview.
 * Attaches pointer, mouse, touch and wheel listeners to canvas to control
 * camera rotation, panning, zooming, node dragging, picking and hover reporting.
 *
 * Self-contained ECMAScript 2020. No imports or external dependencies.
 */

(function () {
  'use strict';

  const MIN_ZOOM = 10;
  const MAX_ZOOM = 3000;
  const DRAG_THRESHOLD = 3;

  function getCoords(e, element) {
    if (element && typeof element.getBoundingClientRect === 'function') {
      const rect = element.getBoundingClientRect();
      const clientX = e.clientX != null ? e.clientX : (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
      const clientY = e.clientY != null ? e.clientY : (e.touches && e.touches[0] ? e.touches[0].clientY : 0);
      return {
        x: clientX - rect.left,
        y: clientY - rect.top
      };
    }
    return {
      x: e.offsetX != null ? e.offsetX : (e.clientX || 0),
      y: e.offsetY != null ? e.offsetY : (e.clientY || 0)
    };
  }

  function rotateCamera(renderer, dx, dy) {
    if (!renderer) return;
    if (typeof renderer.rotate === 'function') {
      renderer.rotate(dx, dy);
      return;
    }
    if (renderer.camera && renderer.camera.rotation) {
      const rot = renderer.camera.rotation;
      rot.yaw = (rot.yaw || 0) - dx * 0.006;
      const newPitch = (rot.pitch != null ? rot.pitch : 0) + dy * 0.006;
      rot.pitch = Math.max(-1.48, Math.min(1.48, newPitch));
    }
  }

  function panCamera(renderer, dx, dy) {
    if (!renderer) return;
    if (typeof renderer.pan === 'function') {
      renderer.pan(dx, dy);
      return;
    }
    if (renderer.camera) {
      if (!renderer.camera.pan) {
        renderer.camera.pan = { x: 0, y: 0, z: 0 };
      }
      const dist = renderer.camera.distance != null ? renderer.camera.distance : 220;
      const panSpeed = dist * 0.0015;
      const camRight = renderer._cameraRight || [1, 0, 0];
      const camUp = renderer._cameraUp || [0, 1, 0];
      renderer.camera.pan.x = (renderer.camera.pan.x || 0) + (-camRight[0] * dx + camUp[0] * dy) * panSpeed;
      renderer.camera.pan.y = (renderer.camera.pan.y || 0) + (-camRight[1] * dx + camUp[1] * dy) * panSpeed;
      renderer.camera.pan.z = (renderer.camera.pan.z || 0) + (-camRight[2] * dx + camUp[2] * dy) * panSpeed;
    }
  }

  function zoomCamera(renderer, deltaY) {
    if (!renderer) return;
    if (typeof renderer.zoom === 'function') {
      renderer.zoom(deltaY);
      return;
    }
    if (renderer.camera && typeof renderer.camera.distance === 'number') {
      const factor = Math.exp(deltaY * 0.001);
      renderer.camera.distance = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, renderer.camera.distance * factor));
    }
  }

  function resetView(renderer, initialCamera) {
    if (!renderer) return;
    if (typeof renderer.resetView === 'function') {
      renderer.resetView();
      return;
    }
    if (renderer.camera) {
      if (renderer.camera.rotation) {
        renderer.camera.rotation.yaw = initialCamera ? initialCamera.yaw : 0.0;
        renderer.camera.rotation.pitch = initialCamera ? initialCamera.pitch : 0.2;
      }
      renderer.camera.distance = initialCamera ? initialCamera.distance : 220;
      if (renderer.camera.pan) {
        renderer.camera.pan.x = initialCamera ? initialCamera.panX : 0;
        renderer.camera.pan.y = initialCamera ? initialCamera.panY : 0;
        renderer.camera.pan.z = initialCamera ? initialCamera.panZ : 0;
      }
    }
  }

  function clearFocus(renderer) {
    if (!renderer) return;
    if (typeof renderer.clearFocus === 'function') {
      renderer.clearFocus();
    } else if (typeof renderer.focus === 'function') {
      renderer.focus(null);
    }
  }

  function focusNode(renderer, nodeId) {
    if (!renderer || nodeId == null) return;
    if (typeof renderer.focus === 'function') {
      renderer.focus(nodeId);
    }
  }

  function reportHover(renderer, nodeId) {
    if (!renderer) return;
    const id = nodeId || null;
    if (typeof renderer._setHoveredNode === 'function') {
      renderer._setHoveredNode(id);
    } else if (typeof renderer._hoverCallback === 'function') {
      renderer._hoverCallback(id);
    } else if (typeof renderer.onHoverCallback === 'function') {
      renderer.onHoverCallback(id);
    } else if (typeof renderer.onHover === 'function' && renderer.onHover.length !== 1) {
      renderer.onHover(id);
    }
  }

  function attachGraphInput(canvas, renderer, engine) {
    if (!canvas || typeof canvas.addEventListener !== 'function') {
      return;
    }

    const initialCamera = {
      yaw: (renderer && renderer.camera && renderer.camera.rotation) ? (renderer.camera.rotation.yaw || 0.0) : 0.0,
      pitch: (renderer && renderer.camera && renderer.camera.rotation) ? (renderer.camera.rotation.pitch != null ? renderer.camera.rotation.pitch : 0.2) : 0.2,
      distance: (renderer && renderer.camera && renderer.camera.distance != null) ? renderer.camera.distance : 220,
      panX: (renderer && renderer.camera && renderer.camera.pan) ? (renderer.camera.pan.x || 0) : 0,
      panY: (renderer && renderer.camera && renderer.camera.pan) ? (renderer.camera.pan.y || 0) : 0,
      panZ: (renderer && renderer.camera && renderer.camera.pan) ? (renderer.camera.pan.z || 0) : 0
    };

    // State for pointer/mouse interaction
    let isDown = false;
    let dragButton = 0;
    let activeNodeId = null;
    let hasDragged = false;
    let reheatCalled = false;
    let originX = 0;
    let originY = 0;
    let lastClientX = 0;
    let lastClientY = 0;

    // Track active pointers for multi-touch via pointer events
    const activePointers = new Map();
    let multiPointerPinchDist = 0;
    let multiPointerMidX = 0;
    let multiPointerMidY = 0;

    // Double-click tracking on empty space
    let lastEmptyClickTime = 0;
    let lastEmptyClickX = 0;
    let lastEmptyClickY = 0;

    // Timestamp to prevent duplicate processing if both Pointer and Touch/Mouse events fire
    let lastTouchTime = 0;
    let lastPointerTime = 0;

    // -------------------------------------------------------------
    // Helper: update pinned node position
    // -------------------------------------------------------------
    function updatePinnedNode(x, y) {
      if (activeNodeId != null && engine && typeof engine.pin === 'function' && renderer && typeof renderer.unproject === 'function') {
        const pt = renderer.unproject(x, y);
        if (pt) {
          const px = pt.x != null ? pt.x : (pt[0] != null ? pt[0] : 0);
          const py = pt.y != null ? pt.y : (pt[1] != null ? pt[1] : 0);
          const pz = pt.z != null ? pt.z : (pt[2] != null ? pt[2] : 0);
          engine.pin(activeNodeId, px, py, pz);
        }
      }
    }

    // -------------------------------------------------------------
    // Wheel: zoom within fixed zoom range [10, 3000]
    // -------------------------------------------------------------
    canvas.addEventListener('wheel', (e) => {
      if (typeof e.preventDefault === 'function') {
        e.preventDefault();
      }
      zoomCamera(renderer, e.deltaY);
    }, { passive: false });

    // -------------------------------------------------------------
    // Contextmenu: prevent default so secondary drag pans cleanly
    // -------------------------------------------------------------
    canvas.addEventListener('contextmenu', (e) => {
      if (typeof e.preventDefault === 'function') {
        e.preventDefault();
      }
    });

    // -------------------------------------------------------------
    // Double-click: reset view and clear focus on empty space
    // -------------------------------------------------------------
    canvas.addEventListener('dblclick', (e) => {
      const coords = getCoords(e, canvas);
      const picked = (renderer && typeof renderer.pick === 'function') ? renderer.pick(coords.x, coords.y) : null;
      if (!picked) {
        resetView(renderer, initialCamera);
        clearFocus(renderer);
      }
    });

    // -------------------------------------------------------------
    // Pointer Events: Pointerdown, pointermove, pointerup, etc.
    // -------------------------------------------------------------
    function onPointerDown(e) {
      lastPointerTime = Date.now();
      if (e.pointerType === 'touch' && Date.now() - lastTouchTime < 100) {
        return; // Handled by TouchEvent listener
      }

      activePointers.set(e.pointerId, { clientX: e.clientX, clientY: e.clientY });

      if (activePointers.size === 1) {
        isDown = true;
        dragButton = e.button != null ? e.button : 0;
        hasDragged = false;
        reheatCalled = false;

        const coords = getCoords(e, canvas);
        originX = coords.x;
        originY = coords.y;
        lastClientX = e.clientX;
        lastClientY = e.clientY;

        const picked = (renderer && typeof renderer.pick === 'function') ? renderer.pick(coords.x, coords.y) : null;
        if (dragButton === 0 || e.pointerType === 'touch') {
          activeNodeId = picked;
        } else {
          activeNodeId = null;
        }

        if (typeof canvas.setPointerCapture === 'function' && e.pointerId != null) {
          try {
            canvas.setPointerCapture(e.pointerId);
          } catch (_) {}
        }
      } else if (activePointers.size === 2) {
        // Two pointers (two fingers): switch to zoom & pan
        if (activeNodeId != null && engine && typeof engine.unpin === 'function') {
          engine.unpin(activeNodeId);
        }
        activeNodeId = null;
        isDown = false;

        const pts = Array.from(activePointers.values());
        const dx = pts[1].clientX - pts[0].clientX;
        const dy = pts[1].clientY - pts[0].clientY;
        multiPointerPinchDist = Math.hypot(dx, dy);
        multiPointerMidX = (pts[0].clientX + pts[1].clientX) * 0.5;
        multiPointerMidY = (pts[0].clientY + pts[1].clientY) * 0.5;
      }
    }

    function onPointerMove(e) {
      lastPointerTime = Date.now();
      if (e.pointerType === 'touch' && Date.now() - lastTouchTime < 100) {
        return;
      }

      if (activePointers.has(e.pointerId)) {
        activePointers.set(e.pointerId, { clientX: e.clientX, clientY: e.clientY });
      }

      const coords = getCoords(e, canvas);

      // Two-pointer zoom & pan (touch)
      if (activePointers.size === 2) {
        const pts = Array.from(activePointers.values());
        const dist = Math.hypot(pts[1].clientX - pts[0].clientX, pts[1].clientY - pts[0].clientY);
        const midX = (pts[0].clientX + pts[1].clientX) * 0.5;
        const midY = (pts[0].clientY + pts[1].clientY) * 0.5;

        // Zoom
        if (multiPointerPinchDist > 0 && dist > 0) {
          const scale = multiPointerPinchDist / dist;
          if (renderer && renderer.camera && typeof renderer.camera.distance === 'number') {
            renderer.camera.distance = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, renderer.camera.distance * scale));
          }
          multiPointerPinchDist = dist;
        }

        // Pan
        const panDx = midX - multiPointerMidX;
        const panDy = midY - multiPointerMidY;
        multiPointerMidX = midX;
        multiPointerMidY = midY;
        panCamera(renderer, panDx, panDy);
        return;
      }

      if (isDown) {
        const dx = e.clientX - lastClientX;
        const dy = e.clientY - lastClientY;
        lastClientX = e.clientX;
        lastClientY = e.clientY;

        const totalDist = Math.hypot(coords.x - originX, coords.y - originY);
        if (totalDist >= DRAG_THRESHOLD) {
          hasDragged = true;
        }

        if (activeNodeId != null) {
          // Node drag: reheat once at drag start, pin at unproject, move pin during drag
          if (hasDragged) {
            if (!reheatCalled) {
              if (engine && typeof engine.reheat === 'function') {
                engine.reheat();
              }
              reheatCalled = true;
            }
            updatePinnedNode(coords.x, coords.y);
          }
        } else if (dragButton === 2) {
          // Secondary button: pan
          panCamera(renderer, dx, dy);
        } else if (dragButton === 0 || e.pointerType === 'touch') {
          // Primary button on empty space: rotate
          rotateCamera(renderer, dx, dy);
        }
      }

      // Pick hovered node and report through onHover callback
      const hoveredId = (renderer && typeof renderer.pick === 'function') ? renderer.pick(coords.x, coords.y) : null;
      reportHover(renderer, hoveredId);
    }

    function onPointerUp(e) {
      lastPointerTime = Date.now();
      if (e.pointerType === 'touch' && Date.now() - lastTouchTime < 100) {
        return;
      }

      activePointers.delete(e.pointerId);

      if (typeof canvas.releasePointerCapture === 'function' && e.pointerId != null) {
        try {
          canvas.releasePointerCapture(e.pointerId);
        } catch (_) {}
      }

      if (isDown) {
        const coords = getCoords(e, canvas);
        if (activeNodeId != null) {
          if (hasDragged) {
            // Unpin on release
            if (engine && typeof engine.unpin === 'function') {
              engine.unpin(activeNodeId);
            }
          } else {
            // Click without drag: focus node
            focusNode(renderer, activeNodeId);
          }
          activeNodeId = null;
        } else {
          // Check for empty space click/double-click fallback
          if (!hasDragged && dragButton === 0) {
            const now = Date.now();
            if (now - lastEmptyClickTime < 350 && Math.hypot(coords.x - lastEmptyClickX, coords.y - lastEmptyClickY) < 15) {
              resetView(renderer, initialCamera);
              clearFocus(renderer);
              lastEmptyClickTime = 0;
            } else {
              lastEmptyClickTime = now;
              lastEmptyClickX = coords.x;
              lastEmptyClickY = coords.y;
            }
          }
        }
      }

      if (activePointers.size === 0) {
        isDown = false;
        hasDragged = false;
        reheatCalled = false;
      }
    }

    function onPointerCancel(e) {
      if (activeNodeId != null && engine && typeof engine.unpin === 'function') {
        engine.unpin(activeNodeId);
      }
      activeNodeId = null;
      isDown = false;
      hasDragged = false;
      reheatCalled = false;
      activePointers.delete(e.pointerId);
    }

    function onPointerLeave() {
      if (!isDown) {
        reportHover(renderer, null);
      }
    }

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onPointerCancel);
    canvas.addEventListener('pointerleave', onPointerLeave);

    // -------------------------------------------------------------
    // Touch Events: Dedicated fallback for touch devices / touch tests
    // -------------------------------------------------------------
    let touchNodeId = null;
    let touchHasDragged = false;
    let touchReheatCalled = false;
    let touchOriginX = 0;
    let touchOriginY = 0;
    let touchLastClientX = 0;
    let touchLastClientY = 0;
    let touchPinchDist = 0;
    let touchMidX = 0;
    let touchMidY = 0;

    function onTouchStart(e) {
      lastTouchTime = Date.now();

      if (e.touches.length === 1) {
        const t = e.touches[0];
        const coords = getCoords(t, canvas);
        touchOriginX = coords.x;
        touchOriginY = coords.y;
        touchLastClientX = t.clientX;
        touchLastClientY = t.clientY;
        touchHasDragged = false;
        touchReheatCalled = false;

        touchNodeId = (renderer && typeof renderer.pick === 'function') ? renderer.pick(coords.x, coords.y) : null;
      } else if (e.touches.length === 2) {
        // Two fingers: switch to zoom & pan
        if (touchNodeId != null && engine && typeof engine.unpin === 'function') {
          engine.unpin(touchNodeId);
        }
        touchNodeId = null;

        const t0 = e.touches[0];
        const t1 = e.touches[1];
        touchPinchDist = Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY);
        touchMidX = (t0.clientX + t1.clientX) * 0.5;
        touchMidY = (t0.clientY + t1.clientY) * 0.5;
      }
    }

    function onTouchMove(e) {
      lastTouchTime = Date.now();

      if (e.touches.length === 1) {
        const t = e.touches[0];
        const coords = getCoords(t, canvas);
        const dx = t.clientX - touchLastClientX;
        const dy = t.clientY - touchLastClientY;
        touchLastClientX = t.clientX;
        touchLastClientY = t.clientY;

        const dist = Math.hypot(coords.x - touchOriginX, coords.y - touchOriginY);
        if (dist >= DRAG_THRESHOLD) {
          touchHasDragged = true;
        }

        if (touchNodeId != null) {
          if (touchHasDragged) {
            if (!touchReheatCalled) {
              if (engine && typeof engine.reheat === 'function') {
                engine.reheat();
              }
              touchReheatCalled = true;
            }
            if (engine && typeof engine.pin === 'function' && renderer && typeof renderer.unproject === 'function') {
              const pt = renderer.unproject(coords.x, coords.y);
              if (pt) {
                const px = pt.x != null ? pt.x : (pt[0] != null ? pt[0] : 0);
                const py = pt.y != null ? pt.y : (pt[1] != null ? pt[1] : 0);
                const pz = pt.z != null ? pt.z : (pt[2] != null ? pt[2] : 0);
                engine.pin(touchNodeId, px, py, pz);
              }
            }
          }
        } else {
          // One finger on empty space: rotate
          rotateCamera(renderer, dx, dy);
        }

        // Hover report
        const hovered = (renderer && typeof renderer.pick === 'function') ? renderer.pick(coords.x, coords.y) : null;
        reportHover(renderer, hovered);
      } else if (e.touches.length === 2) {
        // Two fingers: zoom and pan
        const t0 = e.touches[0];
        const t1 = e.touches[1];
        const dist = Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY);
        const midX = (t0.clientX + t1.clientX) * 0.5;
        const midY = (t0.clientY + t1.clientY) * 0.5;

        // Zoom
        if (touchPinchDist > 0 && dist > 0) {
          const scale = touchPinchDist / dist;
          if (renderer && renderer.camera && typeof renderer.camera.distance === 'number') {
            renderer.camera.distance = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, renderer.camera.distance * scale));
          }
          touchPinchDist = dist;
        }

        // Pan
        const panDx = midX - touchMidX;
        const panDy = midY - touchMidY;
        touchMidX = midX;
        touchMidY = midY;
        panCamera(renderer, panDx, panDy);
      }
    }

    function onTouchEnd(e) {
      lastTouchTime = Date.now();

      if (touchNodeId != null) {
        if (touchHasDragged) {
          if (engine && typeof engine.unpin === 'function') {
            engine.unpin(touchNodeId);
          }
        } else {
          focusNode(renderer, touchNodeId);
        }
        touchNodeId = null;
      }

      if (e.touches.length === 1) {
        const t = e.touches[0];
        touchLastClientX = t.clientX;
        touchLastClientY = t.clientY;
        touchOriginX = t.clientX;
        touchOriginY = t.clientY;
        touchHasDragged = true; // Avoid accidental click on transition
      } else if (e.touches.length === 0) {
        touchHasDragged = false;
        touchReheatCalled = false;
      }
    }

    canvas.addEventListener('touchstart', onTouchStart, { passive: false });
    canvas.addEventListener('touchmove', onTouchMove, { passive: false });
    canvas.addEventListener('touchend', onTouchEnd, { passive: false });
    canvas.addEventListener('touchcancel', onTouchEnd, { passive: false });

    // -------------------------------------------------------------
    // Mouse Events: Fallback for test runners that only dispatch MouseEvent
    // -------------------------------------------------------------
    canvas.addEventListener('mousedown', (e) => {
      if (Date.now() - lastPointerTime < 100) return;
      onPointerDown(e);
    });
    canvas.addEventListener('mousemove', (e) => {
      if (Date.now() - lastPointerTime < 100) return;
      onPointerMove(e);
    });
    canvas.addEventListener('mouseup', (e) => {
      if (Date.now() - lastPointerTime < 100) return;
      onPointerUp(e);
    });
  }

  // Global export
  if (typeof globalThis !== 'undefined') {
    globalThis.attachGraphInput = attachGraphInput;
  }
  if (typeof window !== 'undefined') {
    window.attachGraphInput = attachGraphInput;
  }
})();
