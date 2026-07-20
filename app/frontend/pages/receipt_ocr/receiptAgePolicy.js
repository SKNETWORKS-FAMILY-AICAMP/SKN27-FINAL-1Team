export const oldReceiptWarningDays = 30

const millisecondsPerDay = 24 * 60 * 60 * 1000

export function getReceiptAgeInDays(value, now = new Date()) {
  if (!value) {
    return null
  }

  const normalized = String(value).trim().replace(/\./g, '-').replace(' ', 'T')
  const purchaseDate = new Date(normalized)
  const currentDate = now instanceof Date ? now : new Date(now)

  if (Number.isNaN(purchaseDate.getTime()) || Number.isNaN(currentDate.getTime())) {
    return null
  }

  const purchaseDay = Date.UTC(
    purchaseDate.getFullYear(),
    purchaseDate.getMonth(),
    purchaseDate.getDate(),
  )
  const currentDay = Date.UTC(
    currentDate.getFullYear(),
    currentDate.getMonth(),
    currentDate.getDate(),
  )

  return Math.floor((currentDay - purchaseDay) / millisecondsPerDay)
}

export function isOldReceipt(value, now = new Date()) {
  const ageInDays = getReceiptAgeInDays(value, now)
  return ageInDays !== null && ageInDays > oldReceiptWarningDays
}
