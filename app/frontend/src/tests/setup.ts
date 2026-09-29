import '@testing-library/jest-dom/vitest'
import { beforeEach, vi } from 'vitest'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
})
