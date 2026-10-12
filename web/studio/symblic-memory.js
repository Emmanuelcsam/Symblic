/* Claim notebook: owner revisions, retained evidence and explicit context export. */
(function () {
  'use strict';
  const API = '/api/automation/symblic/memory/';
  const vm = {mount:null,view:null,book:null,books:[],busy:false,error:'',selected:new Set(),
    title:'',run:'',imports:'',claimId:'',content:'',dependencies:'',pending:null,packet:null,page:0};
  function el(tag, attrs, ...children) {
    const item=document.createElement(tag);
    if(tag==='pre')item.tabIndex=0;
    for(const [key,value] of Object.entries(attrs||{})) {
      if(key==='text')item.textContent=value;
      else if(key==='class')item.className=value;
      else if(key==='on')for(const [event,fn] of Object.entries(value))item.addEventListener(event,fn);
      else if(['value','disabled','checked','open'].includes(key))item[key]=value;
      else item.setAttribute(key,value);
    }
    for(const child of children.flat())if(child!==null&&child!==undefined)item.appendChild(typeof child==='string'?document.createTextNode(child):child);
    return item;
  }
  const names=text=>text.split(/[\s,]+/).filter(Boolean);
  const button=(text,fn,extra={})=>el('button',{class:'btn',disabled:vm.busy,text,on:{click:fn},...extra});
  function input(id,key,placeholder='') {
    return el('input',{id,value:vm[key],placeholder,disabled:vm.busy,on:{input:e=>{vm[key]=e.target.value;}}});
  }
  function area(id,key,placeholder='') {
    return el('textarea',{id,rows:4,value:vm[key],placeholder,disabled:vm.busy,on:{input:e=>{vm[key]=e.target.value;}}});
  }
  function jsonOrText(text) {try{return JSON.parse(text);}catch(_){return text;}}
  async function perform(fn) {
    if(vm.busy)return;
    vm.busy=true;vm.error='';paint();
    try{await fn();}catch(error){vm.error=error.message||'Notebook action failed.';}
    finally{vm.busy=false;paint();}
  }
  function accept(book) {
    if(vm.book?.id!==book.id)vm.page=0;
    if(vm.pending&&(vm.book?.id!==book.id||vm.pending.body.expected_head!==book.head||
      (book.events||[]).some(event=>event.operation_id===vm.pending.body.operation_id)))vm.pending=null;
    vm.book=book;vm.packet=null;
    const existing=new Set((book.claims||[]).map(c=>c.id));
    vm.selected=new Set([...vm.selected].filter(id=>existing.has(id)));
  }
  async function load(id) {await perform(async()=>{
    const book=await Studio.api(API+'view?id='+encodeURIComponent(id));
    accept(book);
  });}
  function lazyJson(title,value) {
    const detail=el('details',{class:'unit'},el('summary',{text:title}));
    detail.addEventListener('toggle',()=>{
      if(detail.open&&detail.childElementCount===1)detail.appendChild(el('pre',{text:JSON.stringify(value,null,2)}));
    });
    return detail;
  }
  async function listing() {vm.books=(await Studio.api(API+'notebooks')).notebooks||[];}
  function operation(key,body) {
    if(!vm.pending||vm.pending.key!==key)vm.pending={key,body:{...body,operation_id:crypto.randomUUID()}};
    return vm.pending.body;
  }
  async function create() {
    await perform(async()=>{
      const body={title:vm.title, ...(vm.run.trim()?{run_id:vm.run.trim()}:{}),
        ...(vm.imports.trim()?{selected_ids:names(vm.imports)}:{})};
      const pending=operation('create:'+JSON.stringify(body),body);
      accept(await Studio.api(API+'create',pending));vm.pending=null;
      await listing();
    });
  }
  async function change(fields) {
    if(!vm.book)return;
    await perform(async()=>{
      const key=vm.book.id+':'+JSON.stringify(fields);
      const command=operation(key,{...fields,expected_head:vm.book.head});
      accept(await Studio.api(API+'change',{id:vm.book.id,command}));vm.pending=null;
    });
  }
  function edit(claim) {
    vm.claimId=claim.id;vm.content=typeof claim.content==='string'?claim.content:JSON.stringify(claim.content,null,2);
    vm.dependencies=(claim.dependencies||[]).map(ref=>ref.id).join('\n');paint();
    vm.view?.querySelector('#sy-memory-content')?.focus();
  }
  async function saveClaim(action) {
    await change({action,claim_id:vm.claimId.trim(),content:jsonOrText(vm.content),depends_on:names(vm.dependencies)});
  }
  async function exportContext() {
    await perform(async()=>{
      vm.packet=await Studio.api(API+'context',{id:vm.book.id,selected_ids:[...vm.selected],
        expected_head:vm.book.head,budget:24000,unit:'characters',fixed_parts:[]});
    });
  }
  function download() {
    const url=URL.createObjectURL(new Blob([JSON.stringify(vm.packet,null,2)],{type:'application/json'}));
    const link=el('a',{href:url,download:'symblic-context-'+vm.book.id+'.json'});
    document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function paint() {
    const mount=vm.view;
    if(!mount?.isConnected||mount.parentElement!==vm.mount)return;
    const choose=el('select',{id:'sy-memory-book',disabled:vm.busy,on:{change:e=>{if(e.target.value)load(e.target.value);}}},
      el('option',{value:'',text:'Select a saved notebook'}),
      ...vm.books.map(row=>el('option',{value:row.id,text:vm.book?.id===row.id?vm.book.title+' · '+row.id:row.id})));
    choose.value=vm.book?.id||'';
    const top=el('section',{class:'unit'},el('span',{class:'lbl',text:'Epistemic memory'}),
      el('h2',{text:'Keep evidence. Revise premises. Check what still follows.'}),
      el('p',{class:'hint',text:'A notebook retains every revision and disagreement. Changing support can make dependent claims unavailable. Premises and checked derivations retain their scope; this record does not establish empirical truth.'}),
      el('label',{for:'sy-memory-book',text:'Saved notebook'}),choose,
      button('Refresh notebooks',()=>perform(listing)));
    const make=el('details',{},el('summary',{text:'Create a notebook'}),
      el('label',{for:'sy-memory-title',text:'Notebook title'}),input('sy-memory-title','title','Project evidence'),
      el('label',{for:'sy-memory-run',text:'Import a finished run ID (optional)'}),input('sy-memory-run','run','12-character run ID'),
      el('label',{for:'sy-memory-imports',text:'Selected claim IDs (blank imports all available claims)'}),area('sy-memory-imports','imports'),
      el('p',{class:'hint',text:'Imports read the local run record. Most bindings retain value hashes; an exact output value is attached only when its hash matches. No conversation history is imported.'}),
      button('Create notebook',create,{class:'btn primary',id:'sy-memory-create'}));
    top.appendChild(make);
    const children=[top];
    if(vm.error)children.push(el('p',{role:'alert',class:'sy-memory-error',text:vm.error}));
    if(vm.book) {
      const book=vm.book;
      const assessments=Array.isArray(book.assessments)?new Map(book.assessments.map(a=>[a.id,a])):new Map(Object.entries(book.assessments||{}));
      const claims=book.claims||[];
      vm.page=Math.max(0,Math.min(vm.page,Math.ceil(claims.length/20)-1));
      const rows=claims.slice(vm.page*20,vm.page*20+20).map(claim=>{
        const assessment=assessments.get(claim.id)||{};
        const check=el('input',{type:'checkbox',checked:vm.selected.has(claim.id),disabled:vm.busy,
          'aria-label':'Select '+claim.id,on:{change:e=>{if(e.target.checked)vm.selected.add(claim.id);else vm.selected.delete(claim.id);vm.packet=null;paint();}}});
        const title=el('label',{class:'sy-memory-select'},check,el('span',{text:claim.id+' · revision '+claim.revision}));
        const brief=typeof claim.content==='string'?claim.content:JSON.stringify(claim.content);
        const row=el('article',{class:'card'},title,el('p',{class:'hint',text:claim.origin+' · '+
          (assessment.admissible?'conditional support available':'support unavailable')+' · '+(assessment.status||claim.status)+
          ' · '+(book.value_availability?.[claim.id]||'value availability unknown')}),
          el('pre',{text:brief}),el('div',{class:'sy-acts'},button('Revise',()=>edit(claim)),
            button('Withdraw',()=>change({action:'withdraw',claim_id:claim.id}),{disabled:vm.busy||claim.withdrawn})),
          el('details',{},el('summary',{text:'Dependencies and checks'}),el('pre',{text:JSON.stringify({claim,assessment},null,2)})));
        return row;
      });
      const summary=el('section',{class:'unit'},el('h2',{text:book.title}),
        el('p',{class:'hint',text:book.event_count+' retained events · '+(book.claims||[]).length+' current claims · head '+book.head.slice(0,12)}),
        button('Reload current notebook',()=>load(book.id)),
        el('p',{class:'hint',text:'Select claims to record a disagreement or export their complete dependency context. An unavailable claim cannot be exported as usable support.'}),
        el('p',{class:'hint',text:vm.selected.size+' selected · showing '+(claims.length?vm.page*20+1:0)+'–'+Math.min(vm.page*20+20,claims.length)+' of '+claims.length}),
        el('div',{class:'sy-acts'},button('Record disagreement',()=>change({action:'disagree',
          disagreement_id:'conflict-'+book.head.slice(0,32),claim_ids:[...vm.selected]})),
          button('Prepare selected context',exportContext,{id:'sy-memory-context'})),...rows,
        el('div',{class:'sy-acts'},button('Previous claims',()=>{vm.page--;paint();},{disabled:vm.busy||vm.page===0}),
          button('Next claims',()=>{vm.page++;paint();},{disabled:vm.busy||(vm.page+1)*20>=claims.length})));
      children.push(summary);
      const editor=el('section',{class:'unit'},el('h3',{text:'Add or revise an owner premise'}),
        el('p',{class:'hint',text:'Editing creates an owner premise and clears earlier checks. It does not turn a model proposal into a checked derivation. Dependent claims keep their original references until explicitly rebuilt.'}),
        el('label',{for:'sy-memory-id',text:'Claim ID'}),input('sy-memory-id','claimId','project.requirement'),
        el('label',{for:'sy-memory-content',text:'Statement or exact JSON content'}),area('sy-memory-content','content'),
        el('label',{for:'sy-memory-dependencies',text:'Depends on current claim IDs'}),area('sy-memory-dependencies','dependencies'),
        el('div',{class:'sy-acts'},button('Add premise',()=>saveClaim('add'),{id:'sy-memory-add'}),
          button('Save new revision',()=>saveClaim('revise'),{id:'sy-memory-revise'})));
      children.push(editor);
      const conflicts=book.disagreements||{};
      if((conflicts.active||[]).length)children.push(el('section',{class:'unit'},el('h3',{text:'Active disagreements'}),
        ...(conflicts.active||[]).map(row=>el('div',{class:'card'},el('pre',{text:JSON.stringify(row,null,2)}),
          button('Close this disagreement',()=>change({action:'resolve',disagreement_id:row.id,reason:'Closed by notebook owner'}))))));
      children.push(lazyJson('Retained history and prior disagreements',
        {history:book.history,disagreements:conflicts.historical,source:book.source}));
      if(vm.packet)children.push(el('section',{class:'unit'},el('h3',{text:'Prepared context'}),
        el('p',{class:'hint',text:'This export is bound to the current notebook head. Account for the receiving model’s system prompt, schema and other fixed text when requesting a final context budget.'}),
        vm.packet.all_referenced_values_available===false?el('p',{role:'status',class:'sy-memory-error',text:'Some selected claims contain only value hashes. Their original values are unavailable in this export.'}):null,
        button('Download context JSON',download,{id:'sy-memory-download'}),el('pre',{text:JSON.stringify(vm.packet,null,2)})));
    }
    mount.replaceChildren(...children);
  }
  window.SymblicMemory={render(mount){vm.mount=mount;vm.view=el('div',{class:'sy-memory'});mount.replaceChildren(vm.view);paint();perform(listing);}};
})();
