// Trusted finite checks only; the model writes the complete page.
function auditPricing(html) {
  function need(ok, why) { if (!ok) throw new Error('Pricing: '+why); }
  need(typeof html==='string'&&html.length<24000,'bounded HTML string');
  need(/^\s*<!doctype html>/i.test(html),'HTML doctype');
  need(/<html\b[^>]*\blang\s*=\s*["']en["']/i.test(html),'lang=en');
  need(/<meta\b[^>]*\bcharset\s*=\s*["']utf-8["']/i.test(html),'real UTF-8 meta');
  need(/<meta\b[^>]*\bname\s*=\s*["']viewport["'][^>]*width=device-width/i.test(html),'responsive viewport');
  need(!/<(?:script|iframe|object|embed|img|link|form)\b|\bon[a-z]+\s*=|\b(?:src|href|action)\s*=|@import|url\s*\(/i.test(html),'no executable markup or external resources');
  const count = name => (html.match(new RegExp('<'+name+'\\b','gi'))||[]).length;
  need(count('main')===1&&count('h1')===1&&count('h2')===3&&count('button')===3&&count('style')===1,'one main/h1/style and three plan headings/buttons');
  const plain = html.replace(/<style\b[^>]*>[\s\S]*?<\/style\s*>/gi,'').replace(/<title\b[^>]*>[\s\S]*?<\/title\s*>/gi,'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();
  need(plain==='Pricing Plans Basic $0 Select Studio $12 Select Team $30 Select','exact plan names/prices/buttons; no invented benefits');
  const css=(/<style\b[^>]*>([\s\S]*?)<\/style\s*>/i.exec(html)||[])[1]||'';
  need(/display\s*:\s*grid/i.test(css)&&/repeat\s*\(\s*auto-fit\s*,\s*minmax\s*\(\s*min\s*\(\s*240px\s*,\s*100%\s*\)\s*,\s*1fr\s*\)\s*\)/i.test(css),'auto-fit grid with min(240px,100%)');
  need(/box-sizing\s*:\s*border-box/i.test(css),'border-box sizing');
  need(/:focus(?:-visible)?\b[^{}]*[{][^}]*outline\s*:\s*(?:[2-9]|[1-9][0-9]+)px\s+solid/i.test(css),'visible >=2px solid focus outline');
  return true;
}
