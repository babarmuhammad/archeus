// The short code a project wears on the Overview and the Network: initials of a several-word name, the first two characters of a single word.
// Codes are unique across the list. A later project whose code is taken keeps its first two characters and gains a number (AL, AL2, AL3), so the first holder never changes when the list grows.
export function projectCodes(names) {
  const used = new Set();
  return names.map((name) => {
    const words = String(name).toUpperCase().match(/[\p{L}\p{N}]+/gu) || [];
    const chars = (s, n) => Array.from(s).slice(0, n).join('');
    const base = words.length > 1 ? chars(words.map((w) => chars(w, 1)).join(''), 3) : chars(words[0] || '#', 2);
    let c = base;
    for (let i = 2; used.has(c); i++) c = chars(base, 2) + i;
    used.add(c);
    return c;
  });
}
