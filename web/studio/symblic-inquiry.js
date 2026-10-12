/* Bounded next-check planning. Editing and planning have no execution side effects. */
(function () {
  'use strict';
  const API='/api/automation/symblic/inquiry/';
  const vm={mount:null,view:null,text:'',result:null,error:'',busy:false};
  function el(tag,attrs,...children) {
    const item=document.createElement(tag);
    for(const [key,value] of Object.entries(attrs||{})) {
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
  const words=value=>String(value).replace(/_/g,' ');
  const list=values=>values.length?values.join(', '):'None';
  const button=(text,fn,id)=>el('button',{class:'btn',id,text,disabled:vm.busy,on:{click:fn}});
  function json(title,value) {
    const detail=el('details',{},el('summary',{text:title}));
    detail.addEventListener('toggle',()=>{
      if(detail.open&&detail.childElementCount===1)
        detail.appendChild(el('pre',{tabindex:0,text:JSON.stringify(value,null,2)}));
    });
    return detail;
  }
  async function perform(fn) {
    if(vm.busy)return;
    vm.busy=true;vm.error='';paint();
    try{await fn();}catch(error){
      const detail=error.data?.detail;
      vm.error=(error.message||'Inquiry action failed.')+(detail?' '+words(detail.code)+' at '+detail.path+'.':'');
    }finally{vm.busy=false;paint();}
  }
  function example() {return perform(async()=>{
    const response=await Studio.api(API+'example');
    vm.text=JSON.stringify(response.assessment,null,2);vm.result=null;
  });}
  function plan() {return perform(async()=>{
    vm.result=null;
    // Keep duplicate keys and approximate numbers intact for strict server validation.
    vm.result=await Studio.api(API+'plan',{assessment_json:vm.text});
  });}
  function resultView(result) {
    const recommendation=result.recommendation;
    const summary=el('section',{class:'unit','aria-label':'Inquiry plan'},
      el('h3',{text:recommendation?'Recommended next check: '+recommendation.method_id:'No next check selected'}),
      el('p',{role:'status',text:words(result.status)}),
      el('div',{class:'sy-inquiry-status'},
        el('div',{class:'card'},el('h4',{text:'Claim support: '+words(result.support.status)}),
          el('p',{text:result.support.reason}),el('p',{class:'hint',text:'Support binding: '+words(result.support_binding.status)})),
        el('div',{class:'card'},el('h4',{text:'Inquiry: '+words(result.inquiry.status)}),
          el('p',{text:result.inquiry.reason}))),
      el('p',{text:'Previously covered faults: '+list(result.baseline.covered_fault_ids)}),
      el('p',{text:'Remaining declared faults: '+list(result.baseline.uncovered_fault_ids)}),
      el('p',{class:'hint',text:'Claim support and inquiry status are retained as supplied. Coverage concerns only the declared finite fixtures.'}));
    if(recommendation)summary.appendChild(el('div',{class:'card'},
      el('p',{text:'New fault coverage: '+list(recommendation.new_fault_ids)}),
      el('p',{text:'New distinctions: '+list(recommendation.new_alternative_pairs.map(pair=>pair.join(' / ')))}),
      el('p',{text:'Declared cost: '+recommendation.cost.amount+' '+recommendation.budget_unit}),
      el('p',{text:'Admissible frontier: '+list(result.pareto_frontier)}),
      el('p',{class:'hint',text:'All incomparable choices remain visible. The first method ID selects a stable next step; planning does not authorize execution.'}),
      json('Exact recommendation and pinned references',recommendation)));
    const methods=el('section',{class:'unit'},el('h3',{text:'Method evidence'}),
      ...result.methods.map(method=>el('article',{class:'card'},
        el('h4',{text:method.id+' · '+(method.eligible?'eligible':'excluded')}),
        el('p',{text:'Selection reasons: '+(method.reasons.length?method.reasons.map(words).join(', '):'Measured additional benefit within the declared budget')}),
        el('p',{text:'New faults: '+list(method.new_fault_ids)}),
        el('p',{text:'Unknown faults: '+list(method.unknown_fault_ids)+'; conflicting faults: '+list(method.conflicting_fault_ids)}),
        el('p',{text:'Unknown alternatives: '+list(method.unknown_alternative_ids)+'; conflicting alternatives: '+list(method.conflicting_alternative_ids)}),
        json('Inspect '+method.id+' evidence',method))));
    const shared=el('section',{class:'unit'},el('h3',{text:'Shared dependencies'}),
      el('p',{class:'hint',text:'Different methods can share observations or assumptions. Independence is not established by this plan.'}),
      ...(result.shared_dependencies.length?result.shared_dependencies.map(row=>el('div',{class:'card'},
        el('strong',{text:words(row.role)+': '+row.reference.id+' · revision '+row.reference.revision}),
        el('p',{text:'Shared by '+list(row.method_ids)}))):[el('p',{text:'No exact shared dependency references were declared.'})]));
    return [summary,methods,shared,json('Inspect complete plan JSON',result)];
  }
  function paint() {
    if(!vm.view?.isConnected||vm.view.parentElement!==vm.mount)return;
    const editor=el('textarea',{id:'sy-inquiry-assessment',rows:14,value:vm.text,disabled:vm.busy,
      spellcheck:'false',maxlength:1048576,'aria-describedby':'sy-inquiry-help',on:{input:event=>{
        vm.text=event.target.value;vm.result=null;vm.error='';
        vm.view.querySelector('#sy-inquiry-results')?.replaceChildren();
        vm.view.querySelector('[role=alert]')?.remove();
        vm.view.querySelector('#sy-inquiry-plan').disabled=!vm.text.trim();
      }}});
    const compute=button(vm.busy?'Working…':'Plan next check',plan,'sy-inquiry-plan');
    compute.disabled=vm.busy||!vm.text.trim();
    const top=el('section',{class:'unit'},el('span',{class:'lbl',text:'Advanced inquiry planning'}),
      el('h2',{text:'Choose what to check next'}),
      el('p',{id:'sy-inquiry-help',class:'hint',text:'Supply a claim, finite faults and alternatives, versioned method receipts, dependencies and a budget. Compare new coverage, distinctions and cost. No model or instrument runs here.'}),
      el('div',{class:'sy-inquiry-actions'},button('Fill synthetic example',example,'sy-inquiry-example'),compute),
      el('p',{class:'hint',text:'The example computes three checks over tiny integer fixtures. Its costs count declared primitive operations; they are not elapsed-time measurements. Edits and plans are kept only in this browser page until reload.'}),
      el('label',{for:'sy-inquiry-assessment',text:'Assessment JSON'}),editor);
    const results=el('div',{id:'sy-inquiry-results'},...(vm.result?resultView(vm.result):[]));
    vm.view.replaceChildren(top,...(vm.error?[el('p',{role:'alert',class:'sy-inquiry-error',text:vm.error})]:[]),results);
  }
  window.SymblicInquiry={render(mount){
    vm.mount=mount;vm.view=el('div',{class:'sy-inquiry'});mount.replaceChildren(vm.view);paint();
  }};
})();
