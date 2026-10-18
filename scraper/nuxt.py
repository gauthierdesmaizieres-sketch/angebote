"""Decode the Nuxt payload (__NUXT_DATA__, devalue format) of a page loaded in Playwright."""

# Runs in the page: rebuilds the object graph from the flat devalue array.
_DECODE_JS = r"""
() => {
  const el = document.getElementById('__NUXT_DATA__');
  if (!el) return null;
  const raw = JSON.parse(el.textContent);
  const wrappers = ['Reactive', 'ShallowReactive', 'Ref', 'ShallowRef', 'EmptyRef', 'EmptyShallowRef', 'NuxtError'];
  const memo = new Map();
  const rev = (i) => {
    if (typeof i !== 'number') return i;
    if (memo.has(i)) return memo.get(i);
    const v = raw[i];
    let out;
    if (Array.isArray(v)) {
      if (typeof v[0] === 'string' && wrappers.includes(v[0])) out = rev(v[1]);
      else if (v[0] === 'Set') out = v.slice(1).map(rev);
      else if (v[0] === 'Date') out = v[1];
      else { out = []; memo.set(i, out); v.forEach((x) => out.push(rev(x))); }
    } else if (v && typeof v === 'object') {
      out = {}; memo.set(i, out);
      for (const k in v) out[k] = rev(v[k]);
    } else out = v;
    memo.set(i, out);
    return out;
  };
  const pinia = rev(0).pinia || {};
  // Only return what the scraper needs (the full graph is ~500 KB).
  return {
    promotions: pinia.promotionTree?.promotionTree?.promotions ?? null,
    products: pinia.search?.searchResult?.data ?? null,
    pagination: pinia.search?.searchResult?.meta?.pagination ?? null,
  };
}
"""


async def read_payload(page):
    return await page.evaluate(_DECODE_JS)
