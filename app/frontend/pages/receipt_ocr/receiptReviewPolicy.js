export function requiresReceiptItemReview(item) {
  return item?.normalization_match_type !== 'exact'
}
