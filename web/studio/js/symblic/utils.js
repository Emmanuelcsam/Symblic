// String helpers for the text-mode parser: quotes, punctuation, argument splitting, values and titles. Pure.
export function normalizeContextMode(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (raw === 'continue' || raw === 'append') return 'append';
  if (raw === 'inherit') return 'inherit';
  return 'clear';
}

export function stripQuotes(value) {
  const trimmed = String(value).trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export function stripTrailingPunctuation(value) {
  return String(value).trim().replace(/[.!?]+$/, '');
}

export function splitArgs(input) {
  const parts = [];
  let current = '';
  let quote = null;
  for (let i = 0; i < input.length; i += 1) {
    const ch = input[i];
    if (quote) {
      if (ch === quote && input[i - 1] !== '\\') {
        quote = null;
      }
      current += ch;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      current += ch;
      continue;
    }
    if (ch === ',') {
      parts.push(current);
      current = '';
      continue;
    }
    current += ch;
  }
  if (current.trim()) {
    parts.push(current);
  }
  return parts;
}

export function parseValue(value) {
  const lower = String(value).toLowerCase();
  if (lower === 'true') return true;
  if (lower === 'false') return false;
  if (/^-?\d+(\.\d+)?$/.test(value)) return Number(value);
  return value;
}

export function parseNumber(value) {
  if (value === undefined || value === null || value === '') return undefined;
  const cleaned = String(value).trim().replace(/[.!?]+$/, '');
  if (!cleaned) return undefined;
  const parsed = Number(cleaned);
  return Number.isNaN(parsed) ? undefined : parsed;
}

export function parseParams(value) {
  if (!value) return undefined;
  if (typeof value === 'object') return value;
  const text = String(value).trim();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch (err) {
    return text;
  }
}

export function normalizeScheduleList(value) {
  if (!value) return undefined;
  const text = String(value).trim();
  if (!text) return undefined;
  if (text.includes('|')) {
    return text.split('|').map(part => part.trim()).filter(Boolean).join('\n');
  }
  return text;
}

export function previewText(value) {
  if (!value) return '';
  const trimmed = String(value).replace(/^"|"$/g, '').trim();
  return trimmed.length > 28 ? `${trimmed.slice(0, 28)}...` : trimmed;
}

export function composeTitle(base, moduleName) {
  if (moduleName) {
    return `${moduleName} - ${base}`;
  }
  return base;
}

export function deriveTitle(prompt, moduleName) {
  const clean = String(prompt).replace(/[.!?]+$/, '');
  const words = clean.split(/\s+/).slice(0, 5).join(' ');
  const base = words || 'Instruction';
  return composeTitle(base, moduleName);
}

export function cleanData(data, keep = []) {
  const cleaned = {};
  Object.entries(data).forEach(([key, value]) => {
    if (keep.includes(key)) {
      cleaned[key] = value;
      return;
    }
    if (value === undefined || value === null || value === '') return;
    cleaned[key] = value;
  });
  return cleaned;
}
