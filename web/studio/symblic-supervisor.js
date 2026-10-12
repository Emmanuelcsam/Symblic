/* Durable native workflows. No timer or model starts merely by opening this panel. */
(function () {
  'use strict';
  const API = '/api/automation/symblic/supervisor/';
  const example = {version:1,name:'Two exact calculations, then join',max_parallel:2,state:{completed:0,ready:true},steps:[
    {id:'left',kind:'run',source:'let result = 2 + 3.\nassert result = 5.\nshow result.\n',deadline_s:120},
    {id:'right',kind:'run',source:'let result = 7 * 6.\nassert result = 42.\nshow result.\n',deadline_s:120},
    {id:'joined',kind:'join',after:['left','right']},
    {id:'ready',kind:'wait',after:['joined'],until:{state:'ready',equals:true},within_s:300},
    {id:'count',kind:'set',after:['ready'],changes:{completed:{increment:1}}}
  ]};
  const vm = {mount:null,row:null,list:[],busy:false,error:'',notice:'',simulation:null,draft:JSON.stringify(example,null,2),
    stateDraft:'{}',trigger:'',cron:'0 9 * * *',enabled:false,requests:{},handles:{},loading:false};
  try { vm.requests=JSON.parse(sessionStorage.getItem('symblic-supervisor-requests')||'{}'); } catch (_) {}
  function el(tag, attrs, ...children) {
    const n=document.createElement(tag);
    for(const [key,value] of Object.entries(attrs||{})) {
      if(key==='text') n.textContent=String(value);
      else if(key==='on') for(const [event,fn] of Object.entries(value)) n.addEventListener(event,fn);
      else if(['value','disabled','checked'].includes(key)) n[key]=value;
      else n.setAttribute(key,String(value));
    }
    children.flat().filter(c=>c!==null&&c!==undefined).forEach(c=>n.append(typeof c==='string'?document.createTextNode(c):c));
    return n;
  }
  const para=(value, cls)=>el('p',{text:value,...(cls?{class:cls}:{})});
  function token(key) {
    if(!vm.requests[key]) vm.requests[key]=crypto.randomUUID();
    sessionStorage.setItem('symblic-supervisor-requests',JSON.stringify(vm.requests));
    return vm.requests[key];
  }
  function spent(key) {
    delete vm.requests[key];
    sessionStorage.setItem('symblic-supervisor-requests',JSON.stringify(vm.requests));
  }
  async function api(path,body) {
    let response;
    try { response=await fetch(API+path,{credentials:'same-origin',cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}); }
    catch (_) { throw new Error('Connection lost. Refresh the saved workflow; retry keeps the same request identity.'); }
    let data;
    try { data=await response.json(); } catch (_) { throw new Error('Unreadable reply. Refresh before retrying; the workflow may already be saved.'); }
    if(!response.ok) throw new Error(data.error||(response.status===404||response.status===503?'Supervisor needs the page and server update. Reload after the host restart.':'Request failed ('+response.status+').'));
    return data;
  }
  function adopt(row) {
    vm.row=row;
    sessionStorage.setItem('symblic-supervisor-current',row.id);
    vm.cron=row.schedule?.cron||vm.cron;
    vm.enabled=row.schedule?.enabled===true;
  }
  async function action(fn, notice='Saved.') {
    if(vm.busy) return;
    vm.busy=true;vm.error='';draw();
    try { await fn();vm.notice=notice; }
    catch(error) { vm.error=error.message||String(error); }
    finally {vm.busy=false;draw();}
  }
  const button=(text,fn,alt=false)=>el('button',{type:'button',class:alt?'btn alt':'btn',text,disabled:vm.busy,on:{click:()=>action(fn)}});
  const area=(label,value,change)=>el('label',{class:'ss-field'},el('span',{text:label}),el('textarea',{value,spellcheck:'false',rows:10,on:{input:e=>change(e.target.value)}}));
  function draw() {
    if(!vm.mount?.isConnected) return;
    const top=el('div',{class:'ss-workbench'},el('h2',{text:'Supervisor'}),
      para('Run exact Symblic programs as a durable workflow. Independent steps run together; joins, bounded waits and state survive reconnects.'),
      para('The host scheduler keeps the clock. Native runs keep their effect journals. An unknown outcome or deadline never starts a failure handler by itself.'),
      el('a',{href:'symblic-guides/supervisor.html',text:'Workflow format and examples'}));
    if(vm.error) top.append(el('p',{role:'alert',class:'ss-error',text:vm.error}));
    if(vm.notice) top.append(el('p',{role:'status',text:vm.notice}));
    const saved=el('details',{},el('summary',{text:'Saved workflows'}),button('Refresh saved workflows',async()=>{vm.list=(await api('list')).workflows;},true));
    for(const row of vm.list) saved.append(button(row.name||row.id,async()=>{adopt(await api('view?id='+encodeURIComponent(row.id)));},true));
    top.append(saved);
    const editor=el('details',{...(vm.row?{}:{open:''})},el('summary',{text:'New workflow'}),
      area('Workflow definition (JSON)',vm.draft,value=>{vm.draft=value;}),
      para('Saving checks and freezes exact source, input values, current execution versions and permission ceilings. It does not start a model or action.'),
      el('div',{class:'ss-actions'},button('Save workflow',async()=>{
        const definition=JSON.parse(vm.draft),key='create:'+vm.draft;
        adopt(await api('create',{definition,request_id:token(key)}));spent(key);
      }),button('Simulate control flow',async()=>{
        vm.simulation=await api('simulate',{definition:JSON.parse(vm.draft),outcomes:{}});
      },true),button('Load example',async()=>{vm.draft=JSON.stringify(example,null,2);vm.simulation=null;},true)));
    if(vm.simulation) editor.append(el('div',{class:'ss-card'},el('strong',{text:'SIMULATION — no native execution'}),
      para(vm.simulation.notice),el('pre',{text:JSON.stringify(vm.simulation,null,2)})));
    top.append(editor);
    const row=vm.row;
    if(row) {
      top.append(el('h3',{text:row.definition.name}),para('Saved revision '+row.revision+' · '+(row.paused?'Paused':'Active')+' · '+row.id),
        el('div',{class:'ss-actions'},button('Run once',async()=>{
          const key='start:'+row.id;adopt(await api('start',{id:row.id,request_id:token(key)}));spent(key);
        }),button('Refresh',async()=>adopt(await api('view?id='+encodeURIComponent(row.id))),true),
        button('Advance once',async()=>adopt(await api('tick',{id:row.id})),true),
        button(row.paused?'Resume workflow':'Pause workflow',async()=>{
          const key='pause:'+row.id+':'+row.revision;
          adopt(await api('pause',{id:row.id,revision:row.revision,paused:!row.paused,request_id:token(key)}));spent(key);
        },true)));
      if(row.clock_error) top.append(el('p',{role:'alert',class:'ss-error',text:row.clock_error}));
      top.append(para(row.pulse?.enabled?'The scheduler reconciliation pulse is enabled while bounded work remains.':'No active reconciliation pulse.'));
      const schedule=el('details',{},el('summary',{text:'Schedule with the host scheduler'}),
        el('label',{class:'ss-field'},el('span',{text:'Cron expression'}),el('input',{value:vm.cron,on:{input:e=>{vm.cron=e.target.value;}}})),
        el('label',{class:'ss-check'},el('input',{type:'checkbox',checked:vm.enabled,on:{change:e=>{vm.enabled=e.target.checked;}}}),'Enable scheduled firings'),
        para('Five fields: minute, hour, day, month, weekday. The scheduler’s configured timezone applies. Overlapping firings are recorded as skipped.'),
        button('Save schedule',async()=>adopt(await api('schedule',{id:row.id,revision:row.revision,cron:vm.cron,enabled:vm.enabled})),true));
      if(row.schedule) schedule.append(para('Schedule: '+row.schedule.status+' · '+(row.schedule.enabled?'enabled':'disabled')+(row.schedule.error?' · '+row.schedule.error:'')));
      schedule.append(el('details',{},el('summary',{text:'Attach an existing scheduler event trigger'}),
        para('Configure its actual watcher in the host scheduler first. Its action must start a single runner.supervise tool step with only this workflow ID. Event payload is never passed into native inputs.'),
        el('label',{class:'ss-field'},el('span',{text:'Scheduler event trigger ID'}),el('input',{value:vm.trigger,on:{input:e=>{vm.trigger=e.target.value;}}})),
        button('Attach event trigger',async()=>adopt(await api('bind',{id:row.id,revision:row.revision,trigger:vm.trigger})),true)));
      top.append(schedule,el('details',{},el('summary',{text:'Persistent owner state'}),el('pre',{text:JSON.stringify(row.state,null,2)}),
        area('State changes (JSON object)',vm.stateDraft,value=>{vm.stateDraft=value;}),
        button('Save state changes',async()=>{
          const key='state:'+row.id+':'+row.revision+':'+vm.stateDraft;
          adopt(await api('state',{id:row.id,revision:row.revision,changes:JSON.parse(vm.stateDraft),request_id:token(key)}));spent(key);
        },true)));
      for(const job of [...row.jobs].reverse()) {
        const card=el('section',{class:'ss-card'},el('h4',{text:'Firing '+job.id+' · '+job.status}));
        if(job.reason) card.append(para(job.reason));
        for(const [step,record] of Object.entries(job.steps)) {
          const line=el('div',{class:'ss-step'},el('strong',{text:step+' · '+record.status}));
          if(record.native_id) line.append(el('a',{href:'/runner/#run/'+encodeURIComponent(record.native_id),text:'Open native run'}));
          if(record.error) line.append(para(record.error,'ss-error'));
          if(['unknown','submitting','overdue'].includes(record.status)&&record.submission) {
            const key=job.id+':'+step;
            line.append(el('label',{class:'ss-field'},el('span',{text:'Native run ID for '+step}),
              el('input',{value:vm.handles[key]||record.native_id||'',on:{input:e=>{vm.handles[key]=e.target.value;}}})),
              button('Reconcile '+step,async()=>adopt(await api('reconcile',{id:row.id,firing:job.id,step,native_id:vm.handles[key]||record.native_id||''})),true));
          }
          card.append(line);
        }
        top.append(card);
      }
      top.append(el('details',{},el('summary',{text:'Frozen definition and journal'}),
        el('pre',{text:JSON.stringify({definition:row.definition,frozen:row.frozen,events:row.events},null,2)})));
    }
    vm.mount.replaceChildren(top);
  }
  function render(mount) {
    vm.mount=mount;draw();
    if(!vm.row&&!vm.loading) {
      const id=sessionStorage.getItem('symblic-supervisor-current');
      if(id) {vm.loading=true;action(async()=>adopt(await api('view?id='+encodeURIComponent(id))),'Saved workflow loaded.').finally(()=>{vm.loading=false;});}
    }
  }
  window.SymblicSupervisor={render};
}());
