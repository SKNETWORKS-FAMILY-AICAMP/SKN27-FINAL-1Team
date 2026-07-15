import assert from 'node:assert/strict'
import test from 'node:test'
import { adjustCropPixelsForOffset, resizeCropBoxFromPointer } from './cropGeometry.js'

test('a west resize keeps the east edge fixed and shifts the crop result', () => {
  const cropBox = resizeCropBoxFromPointer({
    handle: 'w',
    pointerX: 300,
    pointerY: 500,
    initialRect: { left: 100, top: 100, right: 900, bottom: 900 },
    bounds: { left: 0, top: 0, right: 1000, bottom: 1000, width: 1000, height: 1000 },
    minScale: 0.32,
  })

  assert.equal(cropBox.w, 0.6)
  assert.equal(cropBox.x, 0.1)
  assert.equal(500 + cropBox.x * 1000 + cropBox.w * 500, 900)
  assert.deepEqual(
    adjustCropPixelsForOffset({
      pixels: { x: 100, y: 50, width: 400, height: 600 },
      cropBox,
      cropSize: { width: 200, height: 300 },
      displayedMediaSize: { width: 1000, height: 1000 },
      naturalMediaSize: { naturalWidth: 1200, naturalHeight: 1600 },
    }),
    { x: 300, y: 50, width: 400, height: 600 },
  )
})
