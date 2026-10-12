function totals(rows) {
  const map = new Map();
  for (const row of rows) {
    const category = row.category;
    const cents = row.cents;
    if (category === undefined || category === null) {
      category = '';
    }
    map.set(category, (map.get(category) || 0) + cents);
  }
  return Array.from(map.entries()).sort((a, b) => {
    const aCat = a[0], bCat = b[0];
    for (let i = 0; i < Math.min(aCat.length, bCat.length); i++) {
      const aCode = aCat.codePointAt(i), bCode = bCat.codePointAt(i);
      if (aCode !== bCode) return aCode - bCode;
    }
    return aCat.length - bCat.length;
  }).map(([category, totalCents]) => [category, totalCents]);
}