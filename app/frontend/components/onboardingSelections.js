export function splitIngredientSelections(items, options) {
  const values = [...new Set(
    (Array.isArray(items) ? items : [])
      .filter((item) => typeof item === 'string' && item.trim())
      .map((item) => item.trim()),
  )]

  return {
    selected: values.filter((item) => options.includes(item)),
    custom: values.filter((item) => !options.includes(item)),
  }
}
