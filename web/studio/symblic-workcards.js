/* Explicit bounded role contracts. Compile is pure; Write owns execution. */
(() => {
  'use strict';
  const vm = {instruction:'Find a positive integer whose square is nine.', type:'Int', checks:'answer * answer = 9\nanswer > 0', inputs:'{}', rounds:2,
    mode:'team', stepRequest:'', stepBy:'ollama:llama3.2:1b', stepRetries:2, stepFallback:false, stepPrepared:null, stepArtifact:null, stepRun:'', stepError:'', stepBusy:false, builder:'', critic:'', review:'Check all constraints. Veto an invalid answer with a concrete reason.', busy:false, error:'', result:null};
  function el(tag, attrs={}, ...children) {
    const n=document.createElement(tag);
    for(const [k,v] of Object.entries(attrs)) {
      if(k==='text') n.textContent=v;
      else if(k==='class') n.className=v;
      else if(k==='on') for(const [event,fn] of Object.entries(v)) n.addEventListener(event,fn);
      else if(v!==false && v!=null) n.setAttribute(k,v===true?'':String(v));
    }
    for(const child of children) if(child!=null)n.append(child);
    return n;
  }
  function render(mount, actions) {
    if(vm.mode === 'steps') return renderSteps(mount, actions);
    const root=el('div',{class:'sy-workcards'});
    const changed=()=>{vm.result=null;output.replaceChildren();};
    function field(label,key,rows=1) {
      const id='sy-card-'+key, input=el(rows>1?'textarea':'input',{id,class:'field',rows:rows>1?rows:null,
        style:'font-size:16px;box-sizing:border-box;width:100%;max-width:100%',disabled:vm.busy,
        on:{input:()=>{vm[key]=input.value;changed();}}});
      input.value=vm[key];
      return el('div',{style:'margin:12px 0'},el('label',{for:id,text:label,class:'lbl'}),input);
    }
    const output=el('div',{'aria-live':'polite'});
    const builder=el('div'),critic=el('div');
    const count=el('select',{id:'sy-card-rounds',class:'field',style:'font-size:16px',disabled:vm.busy,on:{change:()=>{vm.rounds=Number(count.value);changed();render(mount,actions);}}},
      ...[1,2,3,4].map(n=>el('option',{value:n,text:String(n)})));
    count.value=String(vm.rounds);
    const make=el('button',{class:'btn primary',disabled:vm.busy,text:vm.busy?'Preparing…':'Prepare checked team',on:{click:async()=>{
      vm.busy=true;vm.error='';render(mount,actions);
      try {
        const request={instruction:vm.instruction,answer_type:vm.type,checks:vm.checks.split('\n').map(x=>x.trim()).filter(Boolean),
          inputs:JSON.parse(vm.inputs),builder:vm.builder||actions.currentBy(),reviewers:[{role:'critic',by:vm.critic||vm.builder||actions.currentBy(),instruction:vm.review}],rounds:vm.rounds};
        const response=await fetch('/api/automation/symblic/workcards/compile',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'team',request})});
        const result=await response.json();if(!response.ok)throw Error(result.error||'The team contract could not be prepared.');
        vm.result=result;
      } catch(e){vm.error=e.message;}
      finally{vm.busy=false;render(mount,actions);}
    }}});
    root.append(modeButtons(mount,actions),el('span',{class:'lbl',text:'Workcards'}),el('h2',{text:'A builder proposes. A critic reviews. Your checks decide.'}),
      el('p',{class:'hint',text:'Break a problem into a typed answer and explicit constraints. A critic can veto a proposal; agreement cannot override a failed check. Preparation makes no model calls.'}),
      field('What should the builder achieve?','instruction',4),field('Answer type','type'),field('Acceptance predicates — one per line, using answer','checks',4),
      el('details',{},el('summary',{text:'Inputs and critic instructions'}),field('Named inputs as JSON','inputs',3),field('Critic instructions','review',3)),
      el('span',{class:'lbl',text:'Builder'}),builder,el('span',{class:'lbl',text:'Critic'}),critic,
      el('label',{for:'sy-card-rounds',class:'lbl',text:'Maximum proposal rounds'}),count,
      el('p',{class:'hint',text:'At most '+(vm.rounds*2)+' model calls. Each new round receives the prior candidate and review. Repeated models do not establish independent evidence.'}),make);
    if(vm.error)root.append(el('p',{role:'alert',text:vm.error,class:'hint'}));
    if(vm.result)output.append(el('div',{class:'card'},el('h3',{text:'Contract prepared'}),el('p',{class:'hint',text:vm.result.assurance}),
      el('button',{class:'btn primary',text:'Open in Write',on:{click:()=>actions.open(vm.result)}}),
      el('details',{},el('summary',{text:'Inspect generated program'}),el('pre',{text:vm.result.source,style:'white-space:pre-wrap;overflow-wrap:anywhere'}))));
    root.append(output,el('p',{class:'hint'},el('a',{href:'symblic-guides/workcards.html',text:'Typed hole planner, more reviewers and terminal commands'})));
    mount.replaceChildren(root);
    if(window.SymblicPicker?.mountChoices) {
      window.SymblicPicker.mountChoices(builder,{label:'Workcard builder',getValue:()=>vm.builder||actions.currentBy(),disabled:()=>vm.busy,onSelect:by=>{vm.builder=by;changed();window.SymblicPicker.syncChoices();}});
      window.SymblicPicker.mountChoices(critic,{label:'Workcard critic',getValue:()=>vm.critic||vm.builder||actions.currentBy(),disabled:()=>vm.busy,onSelect:by=>{vm.critic=by;changed();}});
    } else {builder.textContent=critic.textContent='Reload to load model choices.';}
  }

  function modeButtons(mount,actions) {
    return el('div',{role:'group','aria-label':'Workcard mode',style:'display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px'},
      ...[['team','Builder and critic'],['steps','Build one step at a time']].map(([key,label])=>
        el('button',{class:'btn '+(vm.mode===key?'primary':'ghost'),'aria-pressed':vm.mode===key?'true':'false',text:label,
          disabled:vm.busy||vm.stepBusy,on:{click:()=>{vm.mode=key;render(mount,actions);}}})));
  }
  async function stepsApi(route,body) {
    const response=await fetch('/api/automation/symblic/workcards/steps/'+route,{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok) throw Error(data.error||'This step construction could not be prepared. Reload after the server update if this endpoint is unavailable.');
    return data;
  }
  function renderSteps(mount,actions) {
    const root=el('div',{class:'sy-workcards'}),picker=el('div');
    const changed=()=>{vm.stepPrepared=null;vm.stepArtifact=null;root.querySelectorAll('[data-steps-result],[data-steps-outline]').forEach(n=>n.remove());const prepare=root.querySelector('[data-steps-prepare]');if(prepare)prepare.disabled=vm.stepBusy||!vm.stepRequest.trim();};
    const runId=el('input',{class:'field',id:'sy-steps-run',placeholder:'12-character run ID',
      style:'font-size:16px;width:100%;box-sizing:border-box',disabled:vm.stepBusy,on:{input:()=>{vm.stepRun=runId.value.trim();vm.stepArtifact=null;root.querySelectorAll('[data-steps-artifact]').forEach(n=>n.remove());}}});
    runId.value=vm.stepRun;
    const editor=el('textarea',{class:'field',id:'sy-steps-request',rows:18,
      style:'font-size:16px;width:100%;max-width:100%;box-sizing:border-box',disabled:vm.stepBusy,
      on:{input:()=>{vm.stepRequest=editor.value;changed();}}});editor.value=vm.stepRequest;
    const retries=el('select',{class:'field',id:'sy-steps-retries',style:'font-size:16px',disabled:vm.stepBusy,
      on:{change:()=>{vm.stepRetries=Number(retries.value);changed();render(mount,actions);}}},
      ...[0,1,2,3,4,5].map(n=>el('option',{value:n,text:String(n)})));retries.value=String(vm.stepRetries);
    const fallback=el('input',{type:'checkbox',id:'sy-steps-fallback',disabled:vm.stepBusy,on:{change:()=>{vm.stepFallback=fallback.checked;changed();}}});fallback.checked=vm.stepFallback;
    const busy=async work=>{
      vm.stepBusy=true;vm.stepError='';render(mount,actions);
      try{await work();}catch(e){vm.stepError=e.message;}finally{vm.stepBusy=false;render(mount,actions);}
    };
    root.append(modeButtons(mount,actions),el('span',{class:'lbl',text:'Checked construction'}),el('h2',{text:'One small piece. Only the work it needs.'}),
      el('p',{class:'hint',text:'Each English instruction chooses one expression. Its local checks must pass before the next step can use it. The completed program can run on new inputs without asking a model.'}),
      el('button',{class:'btn',disabled:vm.stepBusy,text:'Load parcel program example',on:{click:()=>busy(async()=>{
        const r=await fetch('../../examples/steps-parcel.json',{credentials:'same-origin'});
        if(!r.ok)throw Error('The parcel example is unavailable.');
        vm.stepRequest=JSON.stringify(await r.json(),null,2);changed();
      })}}));
    if(vm.stepRequest) {
      try {
        const request=JSON.parse(vm.stepRequest);
        if(Array.isArray(request.steps)&&request.steps.length<=64) {
          root.append(el('div',{'data-steps-outline':''},el('h3',{text:request.title||'The construction steps'}),
            el('ol',{},...request.steps.map(step=>el('li',{style:'margin-bottom:12px'},
              el('strong',{text:String(step.instruction||'')}),
              el('div',{class:'hint',text:'Reads: '+(Array.isArray(step.uses)&&step.uses.length?step.uses.join(', '):'its own input parameters')+' · '+(step.choices?.length||0)+' visible choices · '+(step.checks?.length||0)+' local checks'}))))));
        }
      }catch(_){/* The server reports exact validation errors on Prepare. */}
    }
    root.append(el('details',{},el('summary',{text:'Edit instructions, choices and checks'}),
      el('label',{for:'sy-steps-request',class:'lbl',text:'Construction request (JSON)'}),editor),
      el('label',{class:'lbl',text:'Worker model'}),picker,
      el('label',{class:'lbl',for:'sy-steps-retries',text:'Maximum corrections for each step'}),retries,
      el('label',{for:'sy-steps-fallback',style:'display:flex;align-items:center;gap:10px;margin:14px 0'},fallback,el('span',{text:'Let the engine try the finite menu after rejected model attempts'})),
      el('p',{class:'hint',text:'Optional: after check failures exhaust corrections, native checks try the authored expressions in order. Engine-selected pieces are identified in the result. Provider or resource failures still stop the run.'}),
      el('p',{class:'hint',text:'The worker gets one instruction and its declared accepted dependencies. It does not receive the whole program or hidden evaluation cases. Preparation makes no model calls.'}),
      el('button',{class:'btn primary','data-steps-prepare':'',disabled:vm.stepBusy||!vm.stepRequest.trim(),text:vm.stepBusy?'Working…':'Prepare checked steps',on:{click:()=>busy(async()=>{
        vm.stepPrepared=await stepsApi('compile',{request:JSON.parse(vm.stepRequest),by:vm.stepBy||actions.currentBy(),retries:vm.stepRetries,finite_fallback:vm.stepFallback});
        vm.stepArtifact=null;
      })}}));
    if(vm.stepPrepared) root.append(el('div',{class:'card','data-steps-result':''},el('h3',{text:'Construction prepared'}),
      el('p',{class:'hint',text:'Up to '+vm.stepPrepared.options.max_calls+' model calls. Open in Write and run to select and check the pieces.'}),
      el('button',{class:'btn primary',text:'Open construction in Write',disabled:vm.stepBusy,on:{click:()=>actions.open(vm.stepPrepared)}}),
      el('details',{},el('summary',{text:'Inspect generated construction'}),el('pre',{text:vm.stepPrepared.source,style:'white-space:pre-wrap;overflow-wrap:anywhere'}))));
    root.append(el('hr'),el('h3',{text:'Get a completed program'}),
      el('p',{class:'hint',text:'After construction finishes, copy its run ID from Runs. The saved contract and checks are verified before offering the assembled file. You can recover it after reloading this page.'}),
      el('label',{class:'lbl',for:'sy-steps-run',text:'Completed construction run ID'}),runId,
      el('button',{class:'btn',disabled:vm.stepBusy,text:'Get checked program',on:{click:()=>busy(async()=>{
        const r=await stepsApi('result',{id:vm.stepRun});
        if(!r.accepted)throw Error('The construction is '+r.status+'. It has no completed program yet.');
        vm.stepArtifact=r;
      })}}));
    if(vm.stepArtifact) {
      const artifact=vm.stepArtifact.artifact;
      if(vm.stepArtifact.selection_origins)root.append(el('div',{'data-steps-result':'','data-steps-artifact':''},
        el('p',{text:String(vm.stepArtifact.model_selected_steps)+' functions selected by the model; '+String(vm.stepArtifact.finite_selected_steps)+' completed by finite checks ('+String(vm.stepArtifact.finite_trials)+' engine trials).'}),
        el('details',{},el('summary',{text:'Who selected each function?'}),el('ul',{},...Object.entries(vm.stepArtifact.selection_origins).map(([name,origin])=>el('li',{text:name+': '+(origin==='finite_fallback'?'engine finite completion':'model proposal')}))))));
      root.append(el('div',{class:'card','data-steps-result':'','data-steps-artifact':''},el('h3',{text:'Program assembled'}),el('p',{class:'hint',text:vm.stepArtifact.assurance}),
        el('button',{class:'btn primary',text:'Open finished program in Write',disabled:vm.stepBusy,on:{click:()=>actions.open(artifact)}}),
        el('button',{class:'btn',text:'Download .sym file',disabled:vm.stepBusy,on:{click:()=>{
          const url=URL.createObjectURL(new Blob([artifact.source],{type:'text/plain;charset=utf-8'}));
          const a=el('a',{href:url,download:'constructed-program.sym'});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        }}}),el('details',{},el('summary',{text:'Inspect finished source'}),el('pre',{text:artifact.source,style:'white-space:pre-wrap;overflow-wrap:anywhere'}))));
    }
    if(vm.stepError)root.append(el('p',{role:'alert',text:vm.stepError}));
    root.append(el('p',{},el('a',{href:'symblic-guides/steps.html',text:'Writing precise steps and testing the whole program'})));
    mount.replaceChildren(root);
    if(window.SymblicPicker?.mountChoices)window.SymblicPicker.mountChoices(picker,{label:'Step worker model',getValue:()=>vm.stepBy||actions.currentBy(),disabled:()=>vm.stepBusy,
      onSelect:by=>{vm.stepBy=by;changed();}});
    else picker.textContent='Reload to load model choices.';
  }

  window.SymblicWorkcards={render};
})();
