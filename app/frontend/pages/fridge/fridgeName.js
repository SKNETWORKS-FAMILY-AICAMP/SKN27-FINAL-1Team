export function getFridgeNameClass(name) {
  const length = Array.from(String(name || '').trim()).length

  if (length > 11) return 'is-name-very-long'
  if (length > 8) return 'is-name-long'
  if (length > 5) return 'is-name-medium'
  return ''
}
