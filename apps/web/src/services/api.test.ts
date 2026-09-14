import { describe, expect, it } from 'vitest';

describe('API contract helpers', () => {
  it('uses the versioned same-origin API by default', async () => {
    const module = await import('./api');
    expect(module.API_BASE_URL).toBe('/api/v1');
  });
});
