const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

export function resizeCropBoxFromPointer({ handle, pointerX, pointerY, initialRect, bounds, minScale }) {
  const minWidth = bounds.width * minScale
  const minHeight = bounds.height * minScale
  let { left, top, right, bottom } = initialRect

  if (handle.includes('w')) left = clamp(pointerX, bounds.left, right - minWidth)
  if (handle.includes('e')) right = clamp(pointerX, left + minWidth, bounds.right)
  if (handle.includes('n')) top = clamp(pointerY, bounds.top, bottom - minHeight)
  if (handle.includes('s')) bottom = clamp(pointerY, top + minHeight, bounds.bottom)

  return {
    w: (right - left) / bounds.width,
    h: (bottom - top) / bounds.height,
    x: ((left + right) / 2 - (bounds.left + bounds.right) / 2) / bounds.width,
    y: ((top + bottom) / 2 - (bounds.top + bounds.bottom) / 2) / bounds.height,
  }
}

export function adjustCropPixelsForOffset({ pixels, cropBox, cropSize, displayedMediaSize, naturalMediaSize }) {
  if (!pixels || !cropSize?.width || !cropSize?.height) return pixels

  const shiftedX = pixels.x + (cropBox.x || 0) * displayedMediaSize.width * (pixels.width / cropSize.width)
  const shiftedY = pixels.y + (cropBox.y || 0) * displayedMediaSize.height * (pixels.height / cropSize.height)
  const naturalWidth = Number(naturalMediaSize?.naturalWidth)
  const naturalHeight = Number(naturalMediaSize?.naturalHeight)

  return {
    ...pixels,
    x: Math.round(naturalWidth ? clamp(shiftedX, 0, Math.max(0, naturalWidth - pixels.width)) : Math.max(0, shiftedX)),
    y: Math.round(naturalHeight ? clamp(shiftedY, 0, Math.max(0, naturalHeight - pixels.height)) : Math.max(0, shiftedY)),
  }
}
