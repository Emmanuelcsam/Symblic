/* Finite, reproducible experiments. User values always enter as text. */
(function () {
  'use strict';
  const API='/api/automation/symblic/experiments/';
  const vm={mount:null,view:null,catalog:null,selected:'',drafts:{},receipt:null,error:'',busy:false,verified:null};
  const words=value=>String(value).replace(/[_-]/g,' ');
  function el(tag,attrs,...children){
    const item=document.createElement(tag);
    for(const [key,value] of Object.entries(attrs||{})){
      if(key==='text')item.textContent=value;
      else if(key==='class')item.className=value;
      else if(key==='on')for(const [event,fn] of Object.entries(value))item.addEventListener(event,fn);
      else if(['value','disabled','open'].includes(key))item[key]=value;
      else item.setAttribute(key,value);
    }
    for(const child of children.flat())if(child!==null&&child!==undefined)
      item.appendChild(typeof child==='string'?document.createTextNode(child):child);
    return item;
  }
  const button=(text,fn,id)=>el('button',{class:'btn',id,text,disabled:vm.busy,on:{click:fn}});
  const chosen=()=>vm.catalog?.experiments.find(item=>item.id===vm.selected);
  function inspect(title,data){return el('details',{},el('summary',{text:title}),el('pre',{tabindex:0,text:JSON.stringify(data,null,2)}));}
  async function action(fn){
    if(vm.busy)return;vm.busy=true;vm.error='';paint();
    try{await fn();}catch(error){vm.error=(error.message||'Experiment failed.')+(error.data?.detail?.code?' '+words(error.data.detail.code)+'.':'');}
    finally{vm.busy=false;paint();}
  }
  function load(){return action(async()=>{
    vm.catalog=await Studio.api(API+'catalog');
    if(!chosen())vm.selected=vm.catalog.experiments[0]?.id||'';
    if(chosen()&&vm.drafts[vm.selected]===undefined)vm.drafts[vm.selected]=JSON.stringify(chosen().example,null,2);
  });}
  function run(){return action(async()=>{
    vm.receipt=null;vm.verified=null;
    vm.receipt=await Studio.api(API+'run',{experiment:vm.selected,input_json:vm.drafts[vm.selected]||''});
  });}
  function verify(){return action(async()=>{
    vm.verified=await Studio.api(API+'verify',{receipt_json:JSON.stringify(vm.receipt)});
  });}
  function save(){
    if(!vm.receipt)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(vm.receipt,null,2)+'\n'],{type:'application/json'}));
    const link=el('a',{href:url,download:'symblic-'+vm.receipt.experiment+'-'+vm.receipt.sha256.slice(0,12)+'.json'});
    document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function readable(value,depth=0){
    if(value===null||typeof value!=='object')return el('span',{text:value===null?'Not available':String(value)});
    const entries=Object.entries(value);
    if(depth>=2||entries.length>12)return inspect('Inspect '+(Array.isArray(value)?entries.length+' values':'details'),value);
    return el('dl',{class:'sy-experiment-values'},...entries.map(([key,item])=>el('div',{},
      el('dt',{text:Array.isArray(value)?'Item '+(Number(key)+1):words(key)}),el('dd',{},readable(item,depth+1)))));
  }
  function chartFor(receipt){
    const values=receipt.output.results;
    let series,title,xLabel,yLabel;
    if(receipt.experiment==='field-refinement'){
      series=values.meshes.map(mesh=>({name:mesh.intervals+' intervals',x:mesh.coordinates_m,y:mesh.computed_temperature_K}));
      const last=values.meshes.at(-1);
      series.push({name:'Manufactured solution',x:last.coordinates_m,y:last.manufactured_temperature_K});
      title='Temperature across the domain';xLabel='Position (m)';yLabel='Temperature (K)';
    }else if(receipt.experiment==='hamiltonian_integrators'){
      series=['explicit_euler','symplectic_euler'].map(key=>({name:words(key),x:values[key].trajectory.map(row=>row.step),y:values[key].trajectory.map(row=>row.energy_error)}));
      title='Change in the original Hamiltonian';xLabel='Step';yLabel='Energy error (dimensionless)';
    }else return null;
    const number=value=>{
      if(typeof value==='number')return value;
      if(typeof value!=='string'||!/^[-]?[0-9]+(?:\/[0-9]+)?$/.test(value))return NaN;
      const [a,b='1']=value.split('/');return Number(a)/Number(b);
    };
    if(series.length>6)return null;
    series=series.map(row=>({...row,points:row.x.map((x,i)=>[number(x),number(row.y[i])])}));
    if(series.some(row=>!row.points.length||row.points.length>65||row.points.some(point=>point.some(x=>!Number.isFinite(x)))))
      return el('p',{class:'hint',text:'These values exceed the plot display range. Exact values remain below.'});
    const all=series.flatMap(row=>row.points),xs=all.map(point=>point[0]),ys=all.map(point=>point[1]);
    let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(0,...ys),ymax=Math.max(0,...ys);
    if(xmin===xmax)xmax=xmin+1;if(ymin===ymax)ymax=ymin+1;
    const px=x=>110+(x-xmin)/(xmax-xmin)*492,py=y=>230-(y-ymin)/(ymax-ymin)*180;
    const svg=(name,attrs,text)=>{
      const node=document.createElementNS('http://www.w3.org/2000/svg',name);
      for(const [key,value] of Object.entries(attrs||{}))node.setAttribute(key,String(value));
      if(text!==undefined)node.textContent=text;return node;
    };
    const plot=svg('svg',{viewBox:'0 0 640 290',role:'img','aria-label':title,class:'sy-experiment-plot'});
    plot.append(svg('title',{},title));
    for(let i=0;i<=4;i++){
      const y=ymin+(ymax-ymin)*i/4,x=xmin+(xmax-xmin)*i/4;
      plot.append(svg('line',{x1:110,x2:602,y1:py(y),y2:py(y),stroke:'currentColor',opacity:.15}),
        svg('text',{x:103,y:py(y)+4,'text-anchor':'end'},Number(y.toPrecision(3)).toString()),
        svg('text',{x:px(x),y:249,'text-anchor':'middle'},Number(x.toPrecision(3)).toString()));
    }
    plot.append(svg('text',{x:110,y:24},yLabel),svg('text',{x:337,y:278,'text-anchor':'middle'},xLabel));
    const colors=['#e49a45','#4cafb9','#b593d6','#b4bd63','#dd748a','#97a9c6'];
    const legend=el('ul',{class:'sy-experiment-legend'});
    series.forEach((row,i)=>{
      plot.append(svg('polyline',{points:row.points.map(([x,y])=>px(x)+','+py(y)).join(' '),fill:'none',stroke:colors[i],'stroke-width':2.5,'stroke-dasharray':i===series.length-1&&receipt.experiment==='field-refinement'?'6 4':'none'}));
      const mark=el('span',{'aria-hidden':'true',text:'━'});mark.style.color=colors[i];
      legend.append(el('li',{},mark,' '+row.name));
    });
    return el('figure',{class:'sy-experiment-figure'},el('figcaption',{text:title}),plot,legend,
      el('p',{class:'hint',text:'The plot approximates numbers for display. The receipt retains the exact values.'}));
  }
  function resultView(receipt){
    const output=receipt.output;
    return el('section',{class:'unit','aria-label':'Experiment result',id:'sy-experiment-result'},
      el('h3',{text:'Computed result'}),readable(output.arithmetic),chartFor(receipt),
      readable(output.results),el('h4',{text:'Recorded checks'}),readable(output.checks),
      el('h4',{text:'Scope and limits'}),el('ul',{},...(output.limits||[]).map(text=>el('li',{text}))),
      el('div',{class:'sy-experiment-actions'},button('Recompute and verify receipt',verify,'sy-experiment-verify'),button('Download receipt',save,'sy-experiment-download')),
      ...(vm.verified?[el('p',{role:'status',id:'sy-experiment-verified',text:vm.verified.ok?'Receipt matches a fresh calculation.':'Receipt does not match the current calculation.'})]:[]),
      el('p',{class:'hint',text:'Input and implementation hashes are retained in the receipt. Verification repeats this calculation; independent tests support the adapter itself.'}),
      inspect('Complete input, result and receipt',receipt));
  }
  function paint(){
    if(!vm.view?.isConnected||vm.view.parentElement!==vm.mount)return;
    const item=chosen();
    const select=el('select',{id:'sy-experiment-select',disabled:vm.busy,'aria-label':'Experiment',on:{change:event=>{
      vm.selected=event.target.value;vm.receipt=null;vm.verified=null;vm.error='';
      if(vm.drafts[vm.selected]===undefined)vm.drafts[vm.selected]=JSON.stringify(chosen().example,null,2);
      paint();
    }}},...(vm.catalog?.experiments||[]).map(row=>el('option',{value:row.id,text:row.title})));
    select.value=vm.selected;
    const editor=el('textarea',{id:'sy-experiment-input',rows:15,spellcheck:'false',maxlength:1048576,
      value:vm.drafts[vm.selected]||'',disabled:vm.busy,'aria-label':'Experiment input JSON',on:{input:event=>{
        vm.drafts[vm.selected]=event.target.value;vm.receipt=null;vm.verified=null;
        vm.view.querySelector('#sy-experiment-result')?.remove();
      }}});
    const input=el('details',{id:'sy-experiment-edit'},el('summary',{text:'Inspect or change the inputs'}),
      el('p',{class:'hint',text:'Use integers or exact fraction strings such as "1/2". Input changes clear the previous result.'}),editor);
    const content=[el('section',{class:'unit'},el('span',{class:'lbl',text:'Executable research'}),
      el('h2',{text:'Try a mechanism, inspect the result'}),
      el('p',{class:'hint',text:'Choose a finite experiment and run its synthetic example, or change the supplied inputs. Each calculation reports comparisons, checks and limits.'}),
      ...(vm.catalog?[el('label',{for:'sy-experiment-select',text:'Choose an experiment'}),select]:[]),
      ...(item?[el('p',{text:item.summary}),el('div',{class:'sy-experiment-actions'},button(vm.busy?'Computing…':'Run experiment',run,'sy-experiment-run'),
        button('Reset example',()=>{vm.drafts[vm.selected]=JSON.stringify(item.example,null,2);vm.receipt=null;vm.verified=null;vm.error='';paint();},'sy-experiment-reset')),
        input,el('ul',{class:'hint'},...(item.limits||[]).map(text=>el('li',{text}))),
        el('div',{class:'sy-experiment-sources'},...(item.sources||[]).map(source=>typeof source==='string'?{url:source}:source).filter(source=>source&&typeof source.url==='string'&&/^https:\/\//.test(source.url)).map((source,index)=>el('a',{href:source.url,target:'_blank',rel:'noopener noreferrer',title:source.scope||'',text:source.title||'Primary source '+(index+1)})))]:[]),
      ...(!vm.catalog?[button(vm.busy?'Loading…':'Load experiments',load,'sy-experiment-load')]:[])),
      ...(vm.error?[el('p',{role:'alert',text:vm.error})]:[]),
      ...(vm.receipt?[resultView(vm.receipt)]:[])];
    if(vm.catalog?.unavailable_modules.length)content.push(el('p',{class:'hint',text:'Some experiment adapters are unavailable. Reload after the server update.'}));
    vm.view.replaceChildren(...content);
  }
  window.SymblicExperiments={render(mount){
    vm.mount=mount;vm.view=el('div',{class:'sy-experiments'});mount.replaceChildren(vm.view);paint();
    if(!vm.catalog&&!vm.busy)load();
  }};
})();
