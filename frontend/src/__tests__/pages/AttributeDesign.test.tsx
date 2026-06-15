import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import AttributeDesign from '@/pages/AttributeDesign'
import { getStudyDesign, updateStudyDesign } from '@/services/api'

vi.mock('@/services/api', () => ({
  getStudyDesign: vi.fn(),
  updateStudyDesign: vi.fn(),
}))

const renderAttributeDesign = () =>
  render(
    <MemoryRouter initialEntries={['/studies/s1/design']}>
      <Routes>
        <Route path="/studies/:studyId/design" element={<AttributeDesign />} />
      </Routes>
    </MemoryRouter>,
  )

describe('AttributeDesign render', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders with study design', async () => {
    ;(getStudyDesign as any).mockResolvedValue({
      study_id: 's1',
      attributes: [
        { id: 'brand', name: '品牌', type: 'categorical', description: null, levels: [{ value: 'brand_1', label: 'A' }, { value: 'brand_2', label: 'B' }] },
        { id: 'price', name: '价格', type: 'price', description: null, levels: [] },
      ],
      prohibited_pairs: [],
    })

    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())
  })

  it('renders fallback when study design fails', async () => {
    ;(getStudyDesign as any).mockRejectedValue(new Error('fail'))

    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())
  })
})

describe('AttributeDesign attribute management', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(getStudyDesign as any).mockRejectedValue(new Error('fail'))
  })

  it('adds a new attribute', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    const addBtn = screen.getByText('添加属性')
    await userEvent.click(addBtn)

    await waitFor(() => {
      expect(screen.getAllByText(/属性/).length).toBeGreaterThan(1)
    })
  })

  it('removes an attribute', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes to load - use getAllByText since '价格' appears in multiple places
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    const deleteButtons = screen.getAllByText('删除属性')
    expect(deleteButtons.length).toBeGreaterThan(0)
    await userEvent.click(deleteButtons[0])

    // After deletion, one fewer attribute should remain
    await waitFor(() => {
      expect(screen.getAllByText('删除属性').length).toBeLessThan(deleteButtons.length)
    })
  })

  it('auto-generates id from name via button', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Add a new attribute (has empty name, so id won't auto-generate from name)
    const addBtn = screen.getByText('添加属性')
    await userEvent.click(addBtn)

    await waitFor(() => {
      const idInputs = screen.getAllByPlaceholderText('属性ID（如 brand）')
      expect(idInputs.length).toBeGreaterThan(7)
    })

    const idInputs = screen.getAllByPlaceholderText('属性ID（如 brand）')
    const lastIdInput = idInputs[idInputs.length - 1]
    const nameInputs = screen.getAllByPlaceholderText('属性名称（如：品牌）')
    const lastNameInput = nameInputs[nameInputs.length - 1]

    // Set name first
    await userEvent.type(lastNameInput, '测试属性')

    // Then click auto-generate button for this attribute
    const autoGenButtons = screen.getAllByTitle('根据名称自动生成ID')
    await userEvent.click(autoGenButtons[autoGenButtons.length - 1])

    // The id should be generated from name (attribute_8 because slugify returns null for CJK and falls back to attribute_8)
    await waitFor(() => {
      expect(lastIdInput).toHaveValue('attribute_8')
    })
  })

  it('updates attribute type', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Find a type select and change it
    const typeSelects = screen.getAllByRole('combobox')
    expect(typeSelects.length).toBeGreaterThan(0)

    // Click on the first select to open dropdown
    await userEvent.click(typeSelects[0])

    // Wait for dropdown to open and select 'ordinal'
    await waitFor(() => {
      const ordinalOption = screen.getByText('有序变量')
      expect(ordinalOption).toBeInTheDocument()
    })
  })
})

describe('AttributeDesign level management', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(getStudyDesign as any).mockRejectedValue(new Error('fail'))
  })

  it('adds a new level to an attribute', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes to load
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    const addLevelButtons = screen.getAllByText('添加水平')
    expect(addLevelButtons.length).toBeGreaterThan(0)
    await userEvent.click(addLevelButtons[0])

    // After adding, there should be more levels
    await waitFor(() => {
      const levelTags = screen.getAllByText(/水平/)
      expect(levelTags.length).toBeGreaterThan(4)
    })
  })

  it('removes a level from an attribute', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes to load
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    // Count initial level tags
    const initialLevelTags = screen.getAllByText(/水平/)
    const initialCount = initialLevelTags.length

    // Find all delete icon buttons within level cards (icon-only buttons)
    const allDeleteButtons = screen.getAllByRole('button').filter(
      btn => btn.className.includes('ant-btn-icon-only') && btn.className.includes('ant-btn-dangerous')
    )
    expect(allDeleteButtons.length).toBeGreaterThan(0)
    await userEvent.click(allDeleteButtons[0])

    // After deletion, one fewer level should remain
    await waitFor(() => {
      const levelTags = screen.getAllByText(/水平/)
      expect(levelTags.length).toBeLessThan(initialCount)
    })
  })

  it('updates level value and label', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes to load
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    // Find level value inputs
    const valueInputs = screen.getAllByPlaceholderText('机器标识（如 brand_a）—— 用于问卷生成和数据分析')
    expect(valueInputs.length).toBeGreaterThan(0)

    await userEvent.clear(valueInputs[0])
    await userEvent.type(valueInputs[0], 'new_value')

    expect(valueInputs[0]).toHaveValue('new_value')
  })
})

describe('AttributeDesign validation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(getStudyDesign as any).mockRejectedValue(new Error('fail'))
  })

  it('shows validation error when saving with less than 2 attributes', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes to load
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    const deleteButtons = screen.getAllByText('删除属性')
    // Delete all but one
    for (let i = 0; i < deleteButtons.length - 1; i++) {
      await userEvent.click(deleteButtons[0]) // always click the first one since list shrinks
      await waitFor(() => {
        const remaining = screen.queryAllByText('删除属性')
        expect(remaining.length).toBeLessThan(deleteButtons.length - i)
      })
    }

    // Try to save
    const saveBtn = screen.getByText('保存配置')
    await userEvent.click(saveBtn)

    // Should show validation error
    await waitFor(() => {
      expect(screen.getByText(/至少需要配置两个属性/)).toBeInTheDocument()
    })
  })

  it('shows validation error when attribute has empty id', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    // Clear the first attribute id
    const idInputs = screen.getAllByPlaceholderText('属性ID（如 brand）')
    expect(idInputs.length).toBeGreaterThan(0)

    await userEvent.clear(idInputs[0])

    // Try to save
    const saveBtn = screen.getByText('保存配置')
    await userEvent.click(saveBtn)

    // Should show validation error about empty id
    await waitFor(() => {
      expect(screen.getByText(/ID不能为空/)).toBeInTheDocument()
    })
  })

  it('shows validation error when attribute has duplicate levels', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    // Make two levels have the same value
    const valueInputs = screen.getAllByPlaceholderText('机器标识（如 brand_a）—— 用于问卷生成和数据分析')
    expect(valueInputs.length).toBeGreaterThan(1)

    await userEvent.clear(valueInputs[0])
    await userEvent.type(valueInputs[0], 'same_value')
    await userEvent.clear(valueInputs[1])
    await userEvent.type(valueInputs[1], 'same_value')

    // Try to save
    const saveBtn = screen.getByText('保存配置')
    await userEvent.click(saveBtn)

    // Should show validation error about duplicate level values
    await waitFor(() => {
      expect(screen.getByText(/水平值.*重复/)).toBeInTheDocument()
    })
  })
})

describe('AttributeDesign save', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(getStudyDesign as any).mockRejectedValue(new Error('fail'))
  })

  it('saves valid configuration successfully', async () => {
    ;(updateStudyDesign as any).mockResolvedValue({ success: true })

    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes to load
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    // Save the default configuration
    const saveBtn = screen.getByText('保存配置')
    await userEvent.click(saveBtn)

    await waitFor(() => {
      expect(updateStudyDesign).toHaveBeenCalled()
    })
  })

  it('handles save error', async () => {
    ;(updateStudyDesign as any).mockRejectedValue(new Error('save failed'))

    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    const saveBtn = screen.getByText('保存配置')
    await userEvent.click(saveBtn)

    await waitFor(() => {
      expect(updateStudyDesign).toHaveBeenCalled()
    })
  })
})

describe('AttributeDesign prohibited pairs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(getStudyDesign as any).mockRejectedValue(new Error('fail'))
  })

  it('renders prohibited pairs section', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    expect(screen.getByText('禁止组合配置')).toBeInTheDocument()
  })
})

describe('AttributeDesign navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(getStudyDesign as any).mockRejectedValue(new Error('fail'))
  })

  it('has a back button', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    expect(screen.getByText('返回问卷配置')).toBeInTheDocument()
  })
})

describe('AttributeDesign overview table', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(getStudyDesign as any).mockRejectedValue(new Error('fail'))
  })

  it('renders overview table with attributes', async () => {
    renderAttributeDesign()
    await waitFor(() => expect(screen.getByText('属性与水平配置')).toBeInTheDocument())

    // Wait for default attributes
    await waitFor(() => expect(screen.getAllByText('价格').length).toBeGreaterThan(0))

    // Overview table should show
    expect(screen.getByText('属性与水平总览')).toBeInTheDocument()
  })
})
