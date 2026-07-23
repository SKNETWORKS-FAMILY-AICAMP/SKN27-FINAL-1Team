import assert from 'node:assert/strict'
import test from 'node:test'
import {
  areAllSourceItemsSelected,
  buildSourceFilterOptions,
  findExactSelectedRecipe,
  getSelectedDeleteCount,
  getShoppingSelectionState,
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

test('builds and matches recipe filters from owned ingredient sources', () => {
  const ownedIngredient = {
    name: '물',
    source_refs: [
      { type: 'recipe', recipe_id: 8, recipe_title: '들깨 무나물' },
    ],
  }
  const options = buildSourceFilterOptions({
    items: [],
    owned_ingredients: [ownedIngredient],
  }, [])

  assert.deepEqual(
    options.map(({ key, label }) => ({ key, label })),
    [{ key: 'recipe:id:8', label: '들깨 무나물' }],
  )
  assert.equal(itemMatchesSourceOption(ownedIngredient, options[0], 1), true)
  assert.equal(
    itemMatchesSourceOption(
      ownedIngredient,
      {
        key: 'recipe:id:9',
        label: '단호박물까스',
        type: 'recipe',
        recipeId: '9',
        recipeTitle: '단호박물까스',
      },
      2,
    ),
    false,
  )
})

test('detects when every item in one recipe source is selected', () => {
  assert.equal(
    areAllSourceItemsSelected(
      [{ id: 1, is_checked: true }, { id: 2, is_checked: true }],
      [{ name: '물' }],
      ['name:물'],
    ),
    true,
  )
  assert.equal(
    areAllSourceItemsSelected(
      [{ id: 1, is_checked: true }],
      [{ name: '물' }],
      [],
    ),
    false,
  )
})

test('keeps the global selection independent from the current filter view', () => {
  const activeItems = [
    { id: 1, name: '양파', is_checked: true },
    { id: 2, name: '두부', is_checked: false },
    { id: 3, name: '대파', is_checked: true },
  ]
  const ownedItems = [
    { name: '물' },
    { name: '소금' },
  ]

  const selection = getShoppingSelectionState(
    activeItems,
    ownedItems,
    ['name:물'],
  )

  assert.deepEqual(selection.selectedActiveItems.map((item) => item.id), [1, 3])
  assert.deepEqual(selection.selectedOwnedItems.map((item) => item.name), ['물'])
  assert.equal(selection.selectedCount, 3)
})

test('excludes owned ingredients from generic deletion but counts them for full recipe deletion', () => {
  const selectedActiveItems = [{ id: 1 }, { id: 2 }]
  const recipeActiveItems = [{ id: 1 }]
  const recipeOwnedItems = [{ name: '물' }, { name: '소금' }]

  assert.equal(
    getSelectedDeleteCount({
      selectedActiveItems,
      recipeActiveItems,
      recipeOwnedItems,
      isEntireRecipeSelected: false,
    }),
    2,
  )
  assert.equal(
    getSelectedDeleteCount({
      selectedActiveItems,
      recipeActiveItems,
      recipeOwnedItems,
      isEntireRecipeSelected: true,
    }),
    3,
  )
})

test('detects one exact recipe selection without source filters', () => {
  const recipeA = {
    option: { recipeId: '1', label: '마파두부덮밥' },
    recipeItems: {
      active: [{ id: 1, is_checked: true }],
      owned: [{ name: '물' }],
    },
  }
  const recipeB = {
    option: { recipeId: '2', label: '계란국' },
    recipeItems: {
      active: [{ id: 2, is_checked: false }],
      owned: [],
    },
  }

  assert.equal(
    findExactSelectedRecipe([recipeA, recipeB], 2, ['name:물']),
    recipeA,
  )
  assert.equal(
    findExactSelectedRecipe([recipeA, recipeB], 3, ['name:물']),
    null,
  )
  assert.equal(
    findExactSelectedRecipe([recipeA, { ...recipeA }], 2, ['name:물']),
    null,
  )
})
