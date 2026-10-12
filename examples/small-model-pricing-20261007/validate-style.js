// Author-owned finite CSS contract checker, never used as generated CSS.
function auditPricingStyle(css) {
  function need(ok,why) { if(!ok)throw new Error('Pricing CSS: '+why); }
  need(typeof css==='string'&&css.length<6000,'bounded CSS string');
  const required={
    '*':{'box-sizing':'border-box'},
    'body':{'margin':'0','background':'#111','color':'#f5f5f5','font-family':'sans-serif','font-size':'16px'},
    'main':{'padding':'16px'},
    '.grid':{'display':'grid','grid-template-columns':'repeat(auto-fit,minmax(min(240px,100%),1fr))','gap':'16px'},
    '.card':{'background':'#222','padding':'24px'},
    'button':{'min-height':'44px','font-size':'16px','color':'#111','background':'#eee'},
    'button:focus-visible':{'outline':'3px solid #7dd3fc','outline-offset':'3px'}
  };
  const rules=new Map(), regex=/([^{}]+)[{]([^{}]*)[}]/g;
  let match, last=0;
  while((match=regex.exec(css))) {
    need(css.slice(last,match.index).trim()==='','complete flat CSS rules');last=regex.lastIndex;
    const selector=match[1].trim();
    need(Object.hasOwn(required,selector)&&!rules.has(selector),'one allowed selector per rule: '+selector);
    const properties={};
    for(const declaration of match[2].split(';')) {
      if(!declaration.trim())continue;
      const colon=declaration.indexOf(':');need(colon>0,'property:value required: '+declaration);
      const name=declaration.slice(0,colon).trim(), value=declaration.slice(colon+1).trim();
      need(Object.hasOwn(required[selector],name)&&!Object.hasOwn(properties,name),'allowed unique property for '+selector+': '+name);
      need(value.replace(/\s+/g,'')===required[selector][name].replace(/\s+/g,''),selector+' '+name+' must be '+required[selector][name]);
      properties[name]=value;
    }
    need(Object.keys(properties).length===Object.keys(required[selector]).length,'missing required property for '+selector);
    rules.set(selector,properties);
  }
  need(css.slice(last).trim()===''&&rules.size===Object.keys(required).length,'all seven required rules and no extra CSS');
  return true;
}
