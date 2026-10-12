/* Frozen finite routing experiments. Selection never mutates a running graph. */
(function () {
  'use strict';
  const API = '/api/automation/symblic/policy/', KEY = 'symblic-policy-draft-v1', LIMIT = 1048576;
  const vm = {raw:'',revision:0,checked:null,busy:'',error:'',listError:'',runError:'',notice:'',runs:[],selected:'',run:null,
    advanced:false,receipts:false,mount:null,view:null,timer:null,checking:0,reading:0,listing:0};
  try {const saved=JSON.parse(sessionStorage.getItem(KEY)||'null');
    if(saved && typeof saved.raw==='string' && saved.raw.length<=LIMIT)vm.raw=saved.raw;
    if(saved && typeof saved.selected==='string')vm.selected=saved.selected.slice(0,128);
  } catch (_) { }
  function el(tag,attrs,...children) {
    const node=document.createElement(tag);
    Object.entries(attrs||{}).forEach(([key,value])=>{
      if(key==='text')node.textContent=value;
      else if(key==='class')node.className=value;
      else if(key==='on')Object.entries(value).forEach(([event,fn])=>node.addEventListener(event,fn));
      else if(['value','disabled','open'].includes(key))node[key]=value;
      else node.setAttribute(key,value);
    });
    children.flat().forEach(child=>node.appendChild(typeof child==='string'?document.createTextNode(child):child));return node;
  }
  const visible=()=>vm.view && vm.view.isConnected && vm.view.parentElement===vm.mount;
  function save(){try{sessionStorage.setItem(KEY,JSON.stringify({raw:vm.raw,selected:vm.selected}));}catch(_) {}}
  function errorText(error){return (error.status===503?'Policy experiments are unavailable on this server. ':'')+(error.message||'The request failed.');}
  function parse(){
    if(new TextEncoder().encode(vm.raw).length>LIMIT)throw new Error('Experiment documents are limited to 1 MiB.');
    let value;try{value=JSON.parse(vm.raw);}catch(_){throw new Error('The experiment document must be valid JSON.');}
    if(!value || Array.isArray(value) || typeof value!=='object')throw new Error('Use an experiment JSON object.');
    return value;
  }
  function change(raw){vm.raw=raw;vm.revision++;vm.checking++;vm.checked=null;vm.error='';vm.notice='';save();paintControls();paintOverview();}
  async function example(){
    if(vm.busy)return;const revision=vm.revision;vm.busy='example';vm.error='';paintControls();
    try{const value=await Studio.api(API+'example');
      if(!Array.isArray(value.candidates))throw new Error('The example response is incomplete.');
      if(revision===vm.revision){change(JSON.stringify(value,null,2));const editor=visible()&&vm.view.querySelector('#sy-policy-json');if(editor)editor.value=vm.raw;}
    }catch(error){vm.error=errorText(error);}finally{vm.busy='';paintControls();paintOverview();}
  }
  async function check(){
    if(vm.busy)return;const revision=vm.revision,ticket=++vm.checking;
    vm.checked=null;vm.busy='check';vm.error='';vm.notice='';paintControls();
    try{const document=parse(),response=await Studio.api(API+'check',document);
      if(!response.ok || typeof response.plan_hash!=='string')throw new Error('The experiment check response is incomplete.');
      if(revision===vm.revision && ticket===vm.checking)vm.checked={revision,document,response};
    }catch(error){if(ticket===vm.checking)vm.error=errorText(error);}finally{vm.busy='';paintControls();}
  }
  async function run(){
    if(vm.busy || !vm.checked || vm.checked.revision!==vm.revision)return;
    const checked=vm.checked;vm.busy='run';vm.error='';vm.notice='';paintControls();
    const payload = {...checked.document,expected_plan_hash:checked.response.plan_hash};
    if(checked.response.prior_heldout_uses?.length) payload.acknowledge_heldout_reuse = true;
    try{const value=await Studio.api(API+'run',payload);
      if(typeof value.id!=='string' || !value.id)throw new Error('No saved experiment ID was returned.');
      vm.selected=value.id;vm.run=null;vm.receipts=false;save();vm.notice='Experiment saved. Selection uses training only; the frozen held-out comparison is reported separately.';
      await Promise.all([readRun(value.id),refreshRuns()]);
    }catch(error){vm.checked=null;vm.error=errorText(error)+(error.status===409?' Check the current document again.':' Inspect saved experiments before submitting again; this request will not be retried automatically.');}
    finally{vm.busy='';paintControls();paintRun();}
  }
  async function refreshRuns(){
    const ticket=++vm.listing;
    try{const value=await Studio.api(API+'runs');if(!Array.isArray(value.runs))throw new Error('The saved experiment list is unavailable.');
      if(ticket!==vm.listing)return;vm.runs=value.runs;vm.listError='';
    }catch(error){if(ticket!==vm.listing)return;vm.listError=errorText(error);}paintRuns();
  }
  function schedule(){clearTimeout(vm.timer);if(!visible() || !vm.run || (!vm.run.active && vm.run.status!=='starting'))return;
    const id=vm.selected;vm.timer=setTimeout(()=>{if(visible() && vm.selected===id)readRun(id,false);},1800);}
  async function readRun(id,audit=true,recorded=false){
    const ticket=++vm.reading;
    try{let value;
      try{value=await Studio.api(API+'run?id='+encodeURIComponent(id)+(audit?'':'&audit=0'));}
      catch(error){
        // A successful read can include a recorded job/audit error alongside its
        // state. Studio.api exposes that body on the exception; retain both.
        if(error.status!==200 || error.data?.id!==id || !error.data.state)throw error;
        value=error.data;
      }
      if(value.id!==id || !value.state)throw new Error('The saved experiment response is incomplete.');
      if(id!==vm.selected || ticket!==vm.reading)return;
      const finished = !value.active && value.status !== 'starting';
      if(!audit && !recorded && finished && ticket===vm.reading){readRun(id,true);return;}
      vm.run=value;vm.runError='';
    }catch(error){if(id===vm.selected && ticket===vm.reading)vm.runError=errorText(error);}
    if(id!==vm.selected || ticket!==vm.reading)return;paintRun();schedule();
  }
  async function control(action){
    if(vm.busy || !vm.run)return;const id=vm.selected;vm.busy=action;vm.runError='';paintRun();paintControls();
    try{await Studio.api(API+action,{id});if(id===vm.selected)await readRun(id);await refreshRuns();}
    catch(error){if(id===vm.selected)vm.runError=errorText(error);}finally{vm.busy='';paintRun();paintControls();}
  }
  async function copyPolicy(){
    if(vm.busy || !vm.run?.state.selected)return;
    const id=vm.selected,owner=vm.view;vm.busy='copy';vm.runError='';paintRun();paintControls();
    try{const result=await Studio.api(API+'selected?id='+encodeURIComponent(id));
      if(!result.policy || typeof result.policy_hash!=='string')throw new Error('The selected policy response is incomplete.');
      const selected=vm.run?.state.selected?.selected?.sha256;
      if(id!==vm.selected || (selected && selected!==result.policy_hash))throw new Error('The selected policy changed. Refresh and inspect this experiment again.');
      if(!visible() || vm.view!==owner)return;
      if(!window.SymblicGraphs?.importPolicy)throw new Error('The Graphs interface is unavailable. Reload this page.');
      await window.SymblicGraphs.importPolicy(result.policy,{policy_hash:result.policy_hash,experiment:id});
      if(visible() && vm.view===owner)Studio.go('graphs');
    }catch(error){vm.runError=errorText(error);}finally{vm.busy='';paintRun();paintControls();}
  }
  function receipt(title,value,open=false){
    const pre=el('pre',{tabindex:'0','aria-label':title});
    const details=el('details',{open,on:{toggle:()=>{if(details.open && !pre.textContent)pre.textContent=JSON.stringify(value,null,2);}}},el('summary',{text:title}),pre);
    if(open)pre.textContent=JSON.stringify(value,null,2);return details;
  }
  function paintOverview(){
    if(!visible())return;const view=vm.view.querySelector('[data-policy-overview]');view.replaceChildren();
    let document;try{document=parse();}catch(_){return;}
    view.append(el('h3',{text:document.title||'Routing experiment draft'}),
      el('p',{text:(document.candidates?.length??'Unrecorded')+' candidates · '+(document.training?.length??'Unrecorded')+' training cases · '+(document.heldout?.length??'Unrecorded')+' held-out cases'}));
  }
  function paintControls(){
    if(!visible())return;const controls=vm.view.querySelector('[data-policy-controls]');
    const valid=vm.checked && vm.checked.revision===vm.revision;
    controls.replaceChildren(el('div',{class:'sy-policy-actions'},
      el('button',{class:'btn',text:vm.busy==='check'?'Checking…':'Check experiment',disabled:!!vm.busy || !vm.raw,on:{click:check}}),
      el('button',{class:'btn primary',text:vm.busy==='run'?'Starting…':(valid && vm.checked.response.prior_heldout_uses?.length?'Run and acknowledge held-out reuse':'Run checked experiment'),disabled:!!vm.busy || !valid,on:{click:run}})),
      el('p',{class:'hint',text:'Check makes no model calls. Run freezes cases, candidates, expected outcomes, budgets and the objective before dispatch.'}));
    if(vm.error)controls.append(el('p',{role:'alert',class:'sy-policy-error',text:vm.error}));
    if(vm.notice)controls.append(el('p',{role:'status',text:vm.notice}));
    if(valid){const c=vm.checked.response;
      const prior = c.prior_heldout_uses;
      const children = [
        el('h3',{text:'Reviewed experiment limits'}),
        el('p',{text:c.candidates+' candidates · '+c.training_cases+' training cases · '+c.heldout_cases+' held-out cases'}),
        el('p',{text:'At most '+c.max_assignments+' assigned evaluations and '+c.max_provider_calls+' reserved provider calls.'})
      ];
      if(prior && prior.length){
        children.push(el('p',{role:'alert',class:'hint',text:prior.length+' prior experiment(s) reserved or used these held-out cases ('+prior.join(', ')+'). Running acknowledges possible prior exposure; it will be recorded.'}));
      }
      children.push(el('p',{class:'hint',text:c.scope||'Finite candidate selection under the declared cases and objective.'}),receipt('Frozen plan hash and check receipt',c));
      controls.append(el('div',{'data-policy-check':'',class:'sy-policy-check'},...children));
    }else if(vm.raw)controls.append(el('p',{class:'hint',text:'Check this draft to review limits and enable Run. Every edit clears the previous check.'}));
    const load=vm.view.querySelector('[data-policy-example]');if(load)load.disabled=!!vm.busy;
  }
  function paintRuns(){
    if(!visible())return;const list=vm.view.querySelector('[data-policy-runs]');list.replaceChildren();
    if(vm.listError)list.append(el('p',{role:'alert',class:'sy-policy-error',text:vm.listError}));
    if(!vm.runs.length)list.append(el('p',{class:'hint',text:'No saved policy experiments were returned.'}));
    vm.runs.forEach(row=>list.append(el('button',{class:'btn sy-policy-saved','aria-pressed':row.id===vm.selected?'true':'false',
      text:(row.title||row.id)+' · '+row.status,on:{click:()=>{clearTimeout(vm.timer);vm.selected=row.id;vm.run=null;vm.runError='';vm.receipts=false;save();paintRuns();paintRun();readRun(row.id);}}})));
  }
  function summaries(title,rows){
    const view=el('section',{},el('h4',{text:title}));
    Object.entries(rows||{}).forEach(([hash,row])=>view.append(el('div',{class:'sy-policy-summary'},
      el('p',{class:'mono',text:'Candidate '+hash}),
      el('p',{text:'Score sum: '+row.score_sum+' / '+row.denominator+' assigned cases · utility sum: '+row.utility_sum}),
      el('p',{text:'Observed calls: '+row.observed_calls+' · charged calls: '+row.charged_calls+' · unknown cost items: '+row.unknown_cost_items}),
      el('p',{class:'hint',text:'Recorded statuses: '+Object.entries(row.statuses||{}).map(([key,count])=>key+' '+count).join(' · ')}))));
    return view;
  }
  function paintRun(){
    if(!visible())return;const view=vm.view.querySelector('[data-policy-run]');view.replaceChildren();
    if(vm.runError)view.append(el('p',{role:'alert',class:'sy-policy-error',text:vm.runError}));
    if(!vm.selected)return;view.append(el('h3',{text:'Selected experiment · '+vm.selected}));
    if(!vm.run){view.append(el('p',{class:'hint',text:vm.runError?'No current audit was returned. Recorded receipts can still be requested.':'Reading saved experiment…'}),
      el('button',{class:'btn',text:'Refresh selected experiment',on:{click:()=>readRun(vm.selected)}}),
      el('button',{class:'btn',text:'Read recorded receipts',on:{click:()=>readRun(vm.selected,false,true)}}));return;}
    const run=vm.run,state=run.state,status=run.status||'unrecorded';
    const prior = run.meta?.prior_heldout_uses;
    const assurance = run.assurance || state.assurance;
    const headerLines = [
      el('p',{'data-policy-status':'',role:'status',text:'Recorded status: '+status+' · stage: '+(state.stage||'unrecorded')+' · worker '+(run.active?'active':'inactive')})
    ];
    if(assurance && assurance!=='verified'){
      headerLines.push(el('p',{class:'hint',text:'Assurance: '+assurance}));
    }
    if(prior && prior.length){
      headerLines.push(el('p',{class:'hint',text:'Previously reserved or used held-out set ('+prior.length+' prior experiment'+(prior.length>1?'s':'')+': '+prior.join(', ')+'). Prior exposure recorded.'}));
    }
    headerLines.push(el('p',{class:'hint',text:run.scope||'Selection affects only future graphs after an explicit copy.'}));
    view.append(...headerLines);
    if(run.error)view.append(el('p',{class:'sy-policy-error',text:run.error}));
    view.append(el('div',{class:'sy-policy-actions'},
      el('button',{class:'btn',text:'Refresh selected experiment',disabled:!!vm.busy,on:{click:()=>readRun(vm.selected)}}),
      el('button',{class:'btn',text:'Read recorded receipts',disabled:!!vm.busy,on:{click:()=>readRun(vm.selected,false,true)}}),
      el('button',{class:'btn danger',text:'Stop experiment',disabled:!!vm.busy || status==='done' || !run.active,on:{click:()=>control('stop')}}),
      el('button',{class:'btn',text:'Resume experiment',disabled:!!vm.busy || !run.can_resume || run.active || status==='done',on:{click:()=>control('resume')}})));
    for(const stage of ['training','heldout']){
      const counts=state.assignments?.[stage];
      view.append(el('p',{'data-policy-stage':stage,text:(stage==='training'?'Training':'Held-out')+' assignments: '+(counts?
        ['pending','inflight','terminal'].map(key=>key+' '+(counts[key]?.count??'unrecorded')).join(' · '):'not opened')}));
    }
    view.append(el('p',{class:'hint',text:'Recorded cost unit: '+(state.cost_unit||'unrecorded')+'. Charged limits and observed usage are shown separately.'}));
    if(state.selected){
      view.append(el('p',{text:'Training selected policy: '+(state.selected.selected?.sha256||'unrecorded')}),
        el('button',{class:'btn',text:vm.busy==='copy'?'Copying…':'Copy selected policy to Graphs draft',disabled:!!vm.busy,on:{click:copyPolicy}}),
        el('p',{class:'hint',text:'This explicit copy changes only the routing policy in your future graph draft. Review and check that graph again. Existing runs keep their frozen policies.'}),
        summaries('Training scores',state.selected.receipt?.summaries));
    }
    const evaluation=state.evaluation;
    const gain=evaluation?.improvement===true && evaluation.complete_accounting===true && evaluation.comparison==='observed_improvement' &&
      Number.isSafeInteger(evaluation.utility_gain?.numerator) && evaluation.utility_gain.numerator>0 &&
      Number.isSafeInteger(evaluation.utility_gain?.denominator) && evaluation.utility_gain.denominator>0;
    view.append(el('p',{'data-policy-evaluation':'',text:gain?
      'Recorded finite held-out utility gain: '+evaluation.utility_gain?.numerator+' / '+evaluation.utility_gain?.denominator+'. This applies only to these frozen cases and objective.':
      'Held-out improvement is not established.'}),
      el('p',{class:'hint',text:'These are recorded measurements under declared scoring and cost units. Statistical confidence, causality and broader generalization are not established. Missing or failed assignments remain visible.'}));
    if(evaluation)view.append(summaries('Held-out scores',evaluation.summaries));
    const full=receipt('Full experiment state and receipts',run,vm.receipts);
    full.addEventListener('toggle',()=>{if(full.isConnected)vm.receipts=full.open;});view.append(full);
  }
  function render(mount){
    clearTimeout(vm.timer);vm.mount=mount;vm.view=el('div',{class:'sy-policies'});mount.replaceChildren(vm.view);
    const advanced=el('details',{open:vm.advanced},el('summary',{text:'Edit experiment JSON'}),
      el('p',{class:'hint',text:'Declare candidate routing policies, a baseline, separate training and held-out task families, exact expected outputs, per-assignment budgets and the objective. Held-out data cannot select or revise the training winner.'}),
      el('label',{for:'sy-policy-json',text:'Routing experiment document'}),
      el('textarea',{id:'sy-policy-json',rows:16,maxlength:LIMIT,value:vm.raw,spellcheck:'false',on:{input:event=>change(event.target.value)}}),
      el('button',{class:'btn','data-policy-example':'',text:'Load deterministic experiment',disabled:!!vm.busy,on:{click:example}}));
    advanced.addEventListener('toggle',()=>{if(advanced.isConnected)vm.advanced=advanced.open;});
    vm.view.append(el('section',{class:'unit','aria-labelledby':'sy-policy-title'},el('span',{class:'lbl',text:'Frozen routing experiments'}),
      el('h2',{id:'sy-policy-title',text:'Compare policies. Preserve the held-out test.'}),
      el('p',{class:'hint',text:'Choose among a finite set of routing policies using training results, then measure that frozen choice against the declared baseline on separate cases. The deterministic example demonstrates the workflow; it does not establish a performance gain.'}),
      el('div',{'data-policy-overview':''}),advanced,el('div',{'data-policy-controls':''})),
      el('section',{class:'unit','aria-labelledby':'sy-policy-saved'},el('h2',{id:'sy-policy-saved',text:'Saved policy experiments'}),
        el('button',{class:'btn',text:'Refresh saved experiments',on:{click:refreshRuns}}),el('div',{'data-policy-runs':''}),el('div',{'data-policy-run':''})));
    paintOverview();paintControls();paintRuns();paintRun();refreshRuns();if(vm.selected)readRun(vm.selected);if(!vm.raw && !vm.busy)example();
  }
  window.SymblicPolicies={render};
})();
