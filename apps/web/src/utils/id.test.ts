import { describe, expect, it } from 'vitest'
import { randomKey } from './id'

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

describe('randomKey', () => {
  it('生成符合 UUID v4 格式的标识', () => {
    expect(randomKey()).toMatch(UUID_V4)
  })

  it('连续调用不重复', () => {
    const keys = new Set(Array.from({ length: 500 }, () => randomKey()))
    expect(keys.size).toBe(500)
  })

  it('在没有 crypto.randomUUID 的环境下依然可用且不重复', () => {
    const original = globalThis.crypto
    // 非安全上下文（http://<IP>）有 getRandomValues，但没有 randomUUID。
    Object.defineProperty(globalThis, 'crypto', {
      value: { getRandomValues: original.getRandomValues.bind(original) },
      configurable: true,
    })
    try {
      expect('randomUUID' in globalThis.crypto).toBe(false)
      const keys = new Set(Array.from({ length: 50 }, () => randomKey()))
      expect(keys.size).toBe(50)
      expect([...keys].every(key => UUID_V4.test(key))).toBe(true)
    } finally {
      Object.defineProperty(globalThis, 'crypto', { value: original, configurable: true })
    }
  })

  it('连 crypto 都缺失时仍返回合法格式', () => {
    const original = globalThis.crypto
    Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true })
    try {
      expect(randomKey()).toMatch(UUID_V4)
    } finally {
      Object.defineProperty(globalThis, 'crypto', { value: original, configurable: true })
    }
  })
})
