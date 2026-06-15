import { describe, it, expect } from 'vitest'
import {
  buildDefaultScenario,
  buildSharePieOption,
  buildShareBarOption,
  buildScenarioName,
  validateScenarios,
} from '@/pages/MarketSimulator'
import {
  buildImportanceChartOption,
  buildImportancePieOption,
  buildImportanceTableData,
  buildWTPTableData,
  getRhatStatusColor,
  getPriceCoefficientColor,
} from '@/pages/ImportanceDashboard'
import {
  slugify,
  generateLevelValue,
  createLevel,
  createAttribute,
  createEmptyAttribute,
  validateAttributes,
  formatProhibitedPairDisplay,
} from '@/pages/AttributeDesign'
import type { AttributeDefinition, ProhibitedPair, ScenarioShare } from '@/types/api'

describe('MarketSimulator helpers', () => {
  const attrs: AttributeDefinition[] = [
    { id: 'price', name: '价格', type: 'price', levels: [] },
    { id: 'brand', name: '品牌', type: 'categorical', levels: [{ value: 'b1', label: 'B1' }] },
    { id: 'size', name: '尺寸', type: 'continuous', levels: [] },
    { id: 'color', name: '颜色', type: 'categorical', levels: [] },
  ]

  it('buildDefaultScenario sets defaults', () => {
    const s = buildDefaultScenario(attrs)
    expect(s.name).toBe('产品 A')
    expect(s.attributes.price).toBe(3999)
    expect(s.attributes.brand).toBe('b1')
    expect(s.attributes.size).toBe(0)
    expect(s.attributes.color).toBe('')
  })

  it('buildSharePieOption builds pie data', () => {
    const shares: ScenarioShare[] = [
      { name: 'A', predicted_share: 0.6, share_ci_95_lower: 0.5, share_ci_95_upper: 0.7 },
      { name: 'B', predicted_share: 0.4, share_ci_95_lower: 0.3, share_ci_95_upper: 0.5 },
    ]
    const option = buildSharePieOption(shares) as any
    expect(option.series[0].data).toEqual([
      { name: 'A', value: 60 },
      { name: 'B', value: 40 },
    ])
  })

  it('buildShareBarOption builds bar data', () => {
    const shares: ScenarioShare[] = [
      { name: 'A', predicted_share: 0.6, share_ci_95_lower: 0.5, share_ci_95_upper: 0.7 },
    ]
    const option = buildShareBarOption(shares) as any
    expect(option.xAxis.data).toEqual(['A'])
    expect(option.series[0].data).toEqual([60])
  })

  it('buildScenarioName cycles through letters', () => {
    expect(buildScenarioName(0)).toBe('产品 A')
    expect(buildScenarioName(9)).toBe('产品 J')
  })

  it('validateScenarios enforces minimum of two scenarios', () => {
    expect(validateScenarios([{ name: 'A', attributes: {} }])).toContain('至少')
    expect(validateScenarios([
      { name: 'A', attributes: {} },
      { name: 'B', attributes: {} },
    ])).toBeNull()
  })
})

describe('ImportanceDashboard helpers', () => {
  const importance = {
    overall: {
      price: { mean: 0.5, std: 0.05, ci_95_lower: 0.4, ci_95_upper: 0.6 },
      brand: { mean: 0.3, std: 0.04, ci_95_lower: 0.2, ci_95_upper: 0.4 },
    },
  }

  it('buildImportanceChartOption returns empty for null', () => {
    expect(buildImportanceChartOption(null)).toEqual({})
  })

  it('buildImportanceChartOption builds bar option', () => {
    const option = buildImportanceChartOption(importance as any) as any
    expect(option.xAxis.data).toEqual(['price', 'brand'])
    expect(option.series[0].data).toEqual([50, 30])
  })

  it('buildImportancePieOption builds pie option', () => {
    const option = buildImportancePieOption(importance as any) as any
    expect(option.series[0].data).toEqual([
      { name: 'price', value: 50 },
      { name: 'brand', value: 30 },
    ])
  })

  it('getRhatStatusColor reflects convergence threshold', () => {
    expect(getRhatStatusColor(1.05)).toBe('#3f8600')
    expect(getRhatStatusColor(1.1)).toBe('#3f8600')
    expect(getRhatStatusColor(1.11)).toBe('#cf1322')
  })

  it('getPriceCoefficientColor reflects sign', () => {
    expect(getPriceCoefficientColor(-0.5)).toBe('#3f8600')
    expect(getPriceCoefficientColor(0)).toBe('#cf1322')
    expect(getPriceCoefficientColor(0.1)).toBe('#cf1322')
  })

  it('buildImportanceTableData sorts and shapes rows', () => {
    const rows = buildImportanceTableData(importance as any)
    expect(rows).toHaveLength(2)
    expect(rows[0].attribute).toBe('price')
    expect(rows[0].rank).toBe(1)
    expect(rows[1].attribute).toBe('brand')
  })

  it('buildImportanceTableData returns empty for null', () => {
    expect(buildImportanceTableData(null)).toEqual([])
  })

  it('buildWTPTableData flattens comparisons', () => {
    const wtp = {
      wtp_values: {
        brand: {
          comparisons: [
            { from_level: 'a', to_level: 'b', wtp_mean: 1, wtp_median: 1, wtp_std: 0.1, ci_95_lower: 0, ci_95_upper: 2 },
          ],
        },
      },
      price_coefficient_summary: { mean: -1, median: -1, std: 0, negative_rate: 1, n_positive_outliers: 0 },
    }
    const rows = buildWTPTableData(wtp as any)
    expect(rows).toHaveLength(1)
    expect(rows[0].attribute).toBe('brand')
    expect(rows[0].fromLevel).toBe('a')
  })

  it('buildWTPTableData returns empty for null', () => {
    expect(buildWTPTableData(null)).toEqual([])
  })
})

describe('AttributeDesign validateAttributes', () => {
  const baseAttr = (id: string, name: string): AttributeDefinition => ({
    id,
    name,
    type: 'categorical',
    description: null,
    levels: [
      { value: `${id}_1`, label: 'A' },
      { value: `${id}_2`, label: 'B' },
    ],
  })

  it('returns null for valid attributes', () => {
    expect(validateAttributes([baseAttr('brand', '品牌'), baseAttr('price', '价格')], [])).toBeNull()
  })

  it('requires at least two attributes', () => {
    expect(validateAttributes([baseAttr('brand', '品牌')], [])).toContain('两个属性')
  })

  it('requires non-empty id', () => {
    const attr = { ...baseAttr('brand', '品牌'), id: ' ' }
    expect(validateAttributes([attr, baseAttr('price', '价格')], [])).toContain('ID不能为空')
  })

  it('requires valid id characters', () => {
    const attr = { ...baseAttr('brand', '品牌'), id: 'brand id' }
    expect(validateAttributes([attr, baseAttr('price', '价格')], [])).toContain('ID只能包含')
  })

  it('detects duplicate ids', () => {
    expect(validateAttributes([baseAttr('brand', '品牌'), baseAttr('brand', '品牌2')], [])).toContain('重复')
  })

  it('requires non-empty name', () => {
    const attr = { ...baseAttr('brand', ''), name: '   ' }
    expect(validateAttributes([attr, baseAttr('price', '价格')], [])).toContain('名称不能为空')
  })

  it('requires at least two levels', () => {
    const attr: AttributeDefinition = { ...baseAttr('brand', '品牌'), levels: [{ value: 'brand_1', label: 'A' }] }
    expect(validateAttributes([attr, baseAttr('price', '价格')], [])).toContain('两个水平')
  })

  it('requires non-empty level value', () => {
    const attr: AttributeDefinition = { ...baseAttr('brand', '品牌'), levels: [{ value: ' ', label: 'A' }, { value: 'brand_2', label: 'B' }] }
    expect(validateAttributes([attr, baseAttr('price', '价格')], [])).toContain('标识（value）不能为空')
  })

  it('detects duplicate level values', () => {
    const attr: AttributeDefinition = { ...baseAttr('brand', '品牌'), levels: [{ value: 'x', label: 'A' }, { value: 'x', label: 'B' }] }
    expect(validateAttributes([attr, baseAttr('price', '价格')], [])).toContain('水平值')
  })

  it('validates prohibited pairs need two conditions', () => {
    const pair: ProhibitedPair = { conditions: [{ attribute_id: 'brand', level_value: 'brand_1' }] }
    expect(validateAttributes([baseAttr('brand', '品牌'), baseAttr('price', '价格')], [pair])).toContain('两个条件')
  })

  it('validates prohibited pair references existing attribute', () => {
    const pair: ProhibitedPair = {
      conditions: [
        { attribute_id: 'missing', level_value: 'x' },
        { attribute_id: 'price', level_value: 'price_1' },
      ],
    }
    expect(validateAttributes([baseAttr('brand', '品牌'), baseAttr('price', '价格')], [pair])).toContain('不存在的属性')
  })

  it('validates prohibited pair references existing level', () => {
    const pair: ProhibitedPair = {
      conditions: [
        { attribute_id: 'brand', level_value: 'brand_1' },
        { attribute_id: 'price', level_value: 'price_9' },
      ],
    }
    expect(validateAttributes([baseAttr('brand', '品牌'), baseAttr('price', '价格')], [pair])).toContain('不存在的水平')
  })
})

describe('AttributeDesign helpers', () => {
  it('slugify normalizes names', () => {
    expect(slugify('Hello World')).toBe('hello_world')
    expect(slugify('价格')).toBeNull()
  })

  it('generateLevelValue respects types', () => {
    expect(generateLevelValue(0, 'brand', 'categorical')).toBe('brand_1')
    expect(generateLevelValue(2, 'price', 'price')).toBe('level_3')
    expect(generateLevelValue(1, '', 'ordinal')).toBe('level_2')
  })

  it('createLevel builds a level', () => {
    const level = createLevel(0, 'brand', 'categorical', '美的')
    expect(level.value).toBe('brand_1')
    expect(level.label).toBe('美的')
  })

  it('createAttribute builds an attribute with levels', () => {
    const attr = createAttribute('brand', '品牌', 'categorical', ['A', 'B'])
    expect(attr.id).toBe('brand')
    expect(attr.levels).toHaveLength(2)
    expect(attr.levels[0].value).toBe('brand_1')
  })

  it('createEmptyAttribute builds a blank attribute', () => {
    const attr = createEmptyAttribute(0)
    expect(attr.id).toBe('attr_1')
    expect(attr.levels).toHaveLength(2)
  })

  it('formatProhibitedPairDisplay builds readable condition text', () => {
    const attributes: AttributeDefinition[] = [
      { id: 'brand', name: '品牌', type: 'categorical', description: null, levels: [{ value: 'brand_1', label: '美的' }] },
    ]
    const pair: ProhibitedPair = {
      conditions: [
        { attribute_id: 'brand', level_value: 'brand_1' },
        { attribute_id: 'missing', level_value: 'x' },
      ],
    }
    expect(formatProhibitedPairDisplay(pair, attributes)).toBe('品牌 = 美的 且 missing = x')
  })
})
