import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildSourceFilterOptions,
  itemMatchesSourceOption,
} from './shoppingSourceFilters.js'

test('keeps named recipe filters for current source metadata', () => {
  const list = {
    source_recipes: [
      { recipe_id: 1, recipe_title: '햄 치즈 샌드위치' },
      { recipe_id: 2, recipe_title: '핫도그 샌드위치' },
    ],
    items: [],
  }

  assert.deepEqual(
    buildSourceFilterOptions(list, []).map(({ key, label }) => ({ key, label })),
    [
      { key: 'recipe:id:1', label: '햄 치즈 샌드위치' },
      { key: 'recipe:id:2', label: '핫도그 샌드위치' },
    ],
  )
})

test('uses the list recipe title for legacy items without source refs', () => {
  const item = { source_type: 'recipe', source_refs: [] }
  const options = buildSourceFilterOptions({
    source: 'recipe',
    recipe_id: 7,
    recipe_title: '참치마요 주먹밥',
    items: [item],
  }, [item])

  assert.equal(options.length, 1)
  assert.equal(options[0].label, '참치마요 주먹밥')
  assert.equal(itemMatchesSourceOption(item, options[0], 1), true)
})

test('shows directly added items but does not create a chatbot filter', () => {
  const items = [
    { source_type: 'manual', source_refs: [] },
    { source_type: 'chatbot', source_refs: [] },
  ]

  assert.deepEqual(
    buildSourceFilterOptions({ source: 'manual', items }, items).map(({ key, label }) => ({ key, label })),
    [
      { key: 'manual', label: '직접 추가' },
    ],
  )
})

test('does not replace a missing recipe title with a generic recipe label', () => {
  const item = { source_type: 'recipe', source_refs: [] }

  assert.deepEqual(buildSourceFilterOptions({ source: 'recipe', items: [item] }, [item]), [])
})

test('assigns ref-less recipe items only when one named recipe filter exists', () => {
  const legacyItem = { source_type: 'recipe', source_refs: [] }
  const singleOption = buildSourceFilterOptions({ recipe_id: 7, recipe_title: '참치마요 주먹밥' }, [legacyItem])[0]

  assert.equal(itemMatchesSourceOption(legacyItem, singleOption, 1), true)
  assert.equal(itemMatchesSourceOption(legacyItem, singleOption, 2), false)
})
