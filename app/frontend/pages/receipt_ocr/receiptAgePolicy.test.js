import assert from 'node:assert/strict'
import test from 'node:test'
import { getReceiptAgeInDays, isOldReceipt } from './receiptAgePolicy.js'

const july20 = new Date(2026, 6, 20, 12, 0, 0)

test('구매일이 30일을 초과한 영수증만 오래된 영수증으로 판단한다', () => {
  assert.equal(getReceiptAgeInDays('2026-06-19 14:30:00', july20), 31)
  assert.equal(isOldReceipt('2026-06-19 14:30:00', july20), true)
})

test('정확히 30일 전 영수증은 추가 경고 대상이 아니다', () => {
  assert.equal(getReceiptAgeInDays('2026-06-20 00:00:00', july20), 30)
  assert.equal(isOldReceipt('2026-06-20 00:00:00', july20), false)
})

test('날짜가 없거나 올바르지 않으면 오래된 영수증으로 단정하지 않는다', () => {
  assert.equal(getReceiptAgeInDays(null, july20), null)
  assert.equal(getReceiptAgeInDays('날짜 미확인', july20), null)
  assert.equal(isOldReceipt('날짜 미확인', july20), false)
})
