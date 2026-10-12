// Trusted finite validator. It generates no chart and repairs no candidate.
function auditChart(source) {
  function need(ok, why) { if (!ok) throw new Error('Chart: ' + why); }
  need(typeof source === 'string' && source.length < 12000, 'bounded SVG string required');
  need(!/[&]|<!|<\?|\bon[a-z]+\s*=|\bhref\s*=|\bstyle\s*=/i.test(source), 'no entities, declarations, events, references or CSS');
  const tokens = source.match(/<[^>]*>|[^<]+/g) || [];
  need(tokens.join('') === source, 'complete markup required');
  const nodes = [], stack = [];
  for (const token of tokens) {
    if (token[0] !== '<') {
      if (token.trim()) {
        need(stack.length === 2 && ['title','desc','text'].includes(stack[1].tag), 'text only in title, desc or text');
        stack[1].text += token;
      }
      continue;
    }
    if (token.startsWith('</')) {
      const close = /^<\/([a-z]+)\s*>$/.exec(token);
      need(close && stack.length && stack[stack.length - 1].tag === close[1], 'balanced closing tags');
      stack.pop(); continue;
    }
    const start = /^<([a-z]+)([\s\S]*?)(\/?)>$/.exec(token);
    need(start && ['svg','title','desc','line','rect','text'].includes(start[1]), 'only inert SVG drawing tags');
    const tag = start[1], attrs = {};
    let rest = start[2];
    while (rest.trim()) {
      const a = /^\s+([a-zA-Z][a-zA-Z0-9:-]*)\s*=\s*("[^"]*"|'[^']*')/.exec(rest);
      need(a && !Object.hasOwn(attrs, a[1]), 'unique quoted attributes');
      attrs[a[1]] = a[2].slice(1,-1); rest = rest.slice(a[0].length);
    }
    need(tag === 'svg' ? nodes.length === 0 && stack.length === 0 : stack.length === 1 && stack[0].tag === 'svg', 'one SVG root and direct drawing children');
    const allowed = {svg:['xmlns','viewBox','role','aria-labelledby'], title:['id'], desc:['id'],
      rect:['x','y','width','height','fill'], line:['x1','y1','x2','y2','stroke','stroke-width'],
      text:['x','y','fill','text-anchor','font-size']}[tag];
    need(Object.keys(attrs).every(k => allowed.includes(k)), 'unsupported attribute');
    const node = {tag, attrs, text:''}; nodes.push(node);
    if (!start[3]) stack.push(node);
  }
  need(stack.length === 0, 'all tags closed');
  const of = tag => nodes.filter(n => n.tag === tag), root = of('svg')[0];
  need(of('svg').length === 1 && root.attrs.xmlns === 'http://www.w3.org/2000/svg', 'standard inert SVG namespace required');
  need(root.attrs.viewBox === '0 0 360 240' && root.attrs.role === 'img', 'viewBox and image role');
  const titles = of('title'), descriptions = of('desc');
  need(titles.length === 1 && descriptions.length === 1 && titles[0].attrs.id === 'chart-title' && descriptions[0].attrs.id === 'chart-desc', 'accessible title and description IDs');
  need(root.attrs['aria-labelledby'] === 'chart-title chart-desc', 'accessible title/description references');
  need(/synthetic/i.test(titles[0].text) && /\bms\b/.test(titles[0].text), 'title identifies synthetic values and ms');
  need(['A 2 ms','B 5 ms','C 3 ms'].every(s => descriptions[0].text.includes(s)), 'description names all measured values and units');
  const color = value => /^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i.test(value || '') && !/^#(?:fff|ffffff)$/i.test(value);
  const num = (attrs,key,want) => Object.hasOwn(attrs,key) && attrs[key].trim() !== '' && Number(attrs[key]) === want;
  const bars = of('rect'); need(bars.length === 3, 'exactly three bars');
  for (let i=0; i<3; i++) {
    const a = bars[i].attrs, h = [40,100,60][i];
    need(num(a,'x',40+100*i) && num(a,'y',180-h) && num(a,'width',50) && num(a,'height',h) && color(a.fill), 'bar '+i+' must have x/y/width/height '+[40+100*i,180-h,50,h].join('/')+' and visible fill');
  }
  const lines=of('line'); need(lines.length===1, 'one zero baseline');
  const l=lines[0].attrs;
  need(num(l,'x1',20)&&num(l,'x2',340)&&num(l,'y1',180)&&num(l,'y2',180)&&num(l,'stroke-width',2)&&color(l.stroke), 'visible baseline at y=180');
  const labels=of('text'); need(labels.length===6, 'six category/value labels');
  for(let i=0;i<3;i++) for(const kind of ['category','value']) {
    const wanted=kind==='category'?['A','B','C'][i]:['2 ms','5 ms','3 ms'][i];
    const matches=labels.filter(n=>n.text.trim()===wanted); need(matches.length===1, 'unique label '+wanted);
    const a=matches[0].attrs, y=kind==='category'?202:[132,72,112][i];
    need(num(a,'x',65+100*i)&&num(a,'y',y)&&num(a,'font-size',14)&&a['text-anchor']==='middle'&&color(a.fill), 'visible positioned label '+wanted);
  }
  return true;
}
