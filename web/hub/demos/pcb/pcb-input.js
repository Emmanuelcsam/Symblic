function attachPCBInput(canvas, renderer, onSelect) {
  let isDragging = false;
  let isPrimaryDrag = false;
  let isSecondaryDrag = false;
  let lastX = 0;
  let lastY = 0;
  let hasMoved = false;
  let currentZoom = 1.0;
  const MIN_ZOOM = 0.1;
  const MAX_ZOOM = 10;

  let touchCount = 0;
  let prevTouchDistance = 0;
  let prevTouchCenterX = 0;
  let prevTouchCenterY = 0;
  let touchHasMoved = false;

  function getCanvasCoordinates(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    return { x: clientX - rect.left, y: clientY - rect.top };
  }

  function getComponentAt(clientX, clientY) {
    const coords = getCanvasCoordinates(clientX, clientY);
    if (renderer.getComponentAt) {
      return renderer.getComponentAt(coords.x, coords.y);
    }
    return null;
  }

  function updateHighlight(clientX, clientY) {
    const component = getComponentAt(clientX, clientY);
    if (renderer.highlight) {
      renderer.highlight(component);
    }
  }

  function handleMouseMove(event) {
    updateHighlight(event.clientX, event.clientY);

    if (!isDragging) return;

    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;

    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
      hasMoved = true;
    }

    if (isPrimaryDrag && renderer.rotate) {
      renderer.rotate(dx, dy);
    } else if (isSecondaryDrag && renderer.pan) {
      renderer.pan(dx, dy);
    }

    lastX = event.clientX;
    lastY = event.clientY;
  }

  function handleMouseDown(event) {
    hasMoved = false;
    lastX = event.clientX;
    lastY = event.clientY;

    if (event.button === 0) {
      isPrimaryDrag = true;
    } else if (event.button === 2) {
      isSecondaryDrag = true;
    }
    isDragging = true;
    canvas.style.cursor = isPrimaryDrag ? 'grab' : 'move';
  }

  function handleMouseUp(event) {
    if (isDragging && !hasMoved) {
      const component = getComponentAt(event.clientX, event.clientY);
      if (component && component.id && onSelect) {
        onSelect(component.id);
      }
    }

    isDragging = false;
    isPrimaryDrag = false;
    isSecondaryDrag = false;
    canvas.style.cursor = '';
  }

  function handleWheel(event) {
    event.preventDefault();
    const delta = event.deltaY || 0;
    const sensitivity = 0.001;
    const zoomFactor = 1 - (delta * sensitivity);

    let newZoom = currentZoom * zoomFactor;
    newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newZoom));

    if (newZoom !== currentZoom && renderer.zoom) {
      const factor = newZoom / currentZoom;
      renderer.zoom(factor);
      currentZoom = newZoom;
    }
  }

  function handleDoubleClick(event) {
    const component = getComponentAt(event.clientX, event.clientY);
    if (!component && renderer.resetView) {
      renderer.resetView();
      currentZoom = 1.0;
    }
  }

  function handleTouchStart(event) {
    event.preventDefault();
    touchCount = event.touches.length;
    touchHasMoved = false;

    if (touchCount === 2) {
      const t0 = event.touches[0];
      const t1 = event.touches[1];
      prevTouchDistance = Math.hypot(
        t1.clientX - t0.clientX,
        t1.clientY - t0.clientY
      );
      prevTouchCenterX = (t0.clientX + t1.clientX) / 2;
      prevTouchCenterY = (t0.clientY + t1.clientY) / 2;
    }
  }

  function handleTouchMove(event) {
    event.preventDefault();
    const touches = event.touches;
    touchCount = touches.length;
    touchHasMoved = true;

    if (touchCount === 1) {
      const touch = touches[0];
      updateHighlight(touch.clientX, touch.clientY);

      if (renderer.rotate && canvas._lastTouchX !== undefined) {
        const dx = touch.clientX - canvas._lastTouchX;
        const dy = touch.clientY - canvas._lastTouchY;
        renderer.rotate(dx, dy);
      }
      canvas._lastTouchX = touch.clientX;
      canvas._lastTouchY = touch.clientY;
    } else if (touchCount === 2) {
      const t0 = touches[0];
      const t1 = touches[1];

      const currDistance = Math.hypot(
        t1.clientX - t0.clientX,
        t1.clientY - t0.clientY
      );
      const currCenterX = (t0.clientX + t1.clientX) / 2;
      const currCenterY = (t0.clientY + t1.clientY) / 2;

      if (prevTouchDistance > 0 && renderer.zoom) {
        const zoomFactor = currDistance / prevTouchDistance;
        let newZoom = currentZoom * zoomFactor;
        newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newZoom));

        if (newZoom !== currentZoom) {
          const factor = newZoom / currentZoom;
          renderer.zoom(factor);
          currentZoom = newZoom;
        }
      }

      if (prevTouchCenterX !== undefined && renderer.pan) {
        const dx = currCenterX - prevTouchCenterX;
        const dy = currCenterY - prevTouchCenterY;
        renderer.pan(dx, dy);
      }

      prevTouchDistance = currDistance;
      prevTouchCenterX = currCenterX;
      prevTouchCenterY = currCenterY;
    }
  }

  function handleTouchEnd(event) {
    event.preventDefault();
    touchCount = event.touches.length;

    if (touchCount === 0 && !touchHasMoved && event.changedTouches.length === 1) {
      const touch = event.changedTouches[0];
      const component = getComponentAt(touch.clientX, touch.clientY);
      if (component && component.id && onSelect) {
        onSelect(component.id);
      }
    }

    if (touchCount === 0) {
      prevTouchDistance = 0;
      prevTouchCenterX = 0;
      prevTouchCenterY = 0;
      delete canvas._lastTouchX;
      delete canvas._lastTouchY;
    }
  }

  function handleContextMenu(event) {
    if (isSecondaryDrag) {
      event.preventDefault();
    }
  }

  function handleMouseLeave() {
    if (renderer.highlight) {
      renderer.highlight(null);
    }
    if (isDragging) {
      isDragging = false;
      isPrimaryDrag = false;
      isSecondaryDrag = false;
      canvas.style.cursor = '';
    }
  }

  canvas.addEventListener('mousedown', handleMouseDown);
  canvas.addEventListener('mousemove', handleMouseMove);
  canvas.addEventListener('mouseup', handleMouseUp);
  canvas.addEventListener('mouseleave', handleMouseLeave);
  canvas.addEventListener('wheel', handleWheel, { passive: false });
  canvas.addEventListener('dblclick', handleDoubleClick);
  canvas.addEventListener('contextmenu', handleContextMenu);

  canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
  canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
  canvas.addEventListener('touchend', handleTouchEnd, { passive: false });
}
