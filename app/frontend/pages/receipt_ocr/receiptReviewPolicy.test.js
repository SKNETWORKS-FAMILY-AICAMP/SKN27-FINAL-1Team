import assert from 'node:assert/strict'
import test from 'node:test'
import { requiresReceiptItemReview } from './receiptReviewPolicy.js'

test('exact standard-name matches start confirmed', () => {
  assert.equal(requiresReceiptItemReview({ normalization_match_type: 'exact' }), false)
})

test('partial, missing, and unknown matches require review', () => {
  assert.equal(requiresReceiptItemReview({ normalization_match_type: 'partial' }), true)
  assert.equal(requiresReceiptItemReview({ normalization_match_type: 'none' }), true)
  assert.equal(requiresReceiptItemReview({}), true)
  assert.equal(requiresReceiptItemReview(null), true)
})
