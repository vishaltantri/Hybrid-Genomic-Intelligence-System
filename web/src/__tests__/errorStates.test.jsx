import { describe, it, expect, vi, afterEach } from 'vitest'
import { friendlyDetail, getUser, verifySession } from '../api.js'

describe('user-facing error wording', () => {
  it('hides server fault text and offers a reference id', () => {
    const m = friendlyDetail(500, 'Traceback (most recent call last): C:\app\db.py', 'abc123')
    expect(m).not.toMatch(/Traceback|\.py/)
    expect(m).toContain('abc123')
  })
  it('maps 403, 429 and 413 to actionable text', () => {
    expect(friendlyDetail(403, 'x')).toMatch(/permission/)
    expect(friendlyDetail(429, 'x')).toMatch(/wait/)
    expect(friendlyDetail(413, 'x')).toMatch(/too large/)
  })
  it('keeps 4xx validation messages written for users', () => {
    expect(friendlyDetail(422, 'Enter at least 2 characters.')).toBe('Enter at least 2 characters.')
  })
})
