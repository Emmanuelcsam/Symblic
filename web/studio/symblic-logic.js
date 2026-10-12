/* Controlled human logic -> inspected formal reading -> existing Symblic run. */
(function () {
  'use strict';
  const KEY = 'symblic-logic-draft-v1';
  const vm = { premises: 'human: "Socrates is human"\nrule: "Socrates is human" implies "Socrates is mortal"',
    goal: '"Socrates is mortal"', domains: '', domainsOpen: false, certificateFormat: 'steps', proofOpen: false,
    calls: 4, stepLimit: 16, inferenceFormat: 'json', by: '', compiled: null, stale: false, busy: false, error: '', mount: null, view: null, actions: null };
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    if (saved && typeof saved.premises === 'string' && typeof saved.goal === 'string') {
      vm.premises = saved.premises.slice(0, 32768); vm.goal = saved.goal.slice(0, 8192);
      vm.domains = typeof saved.domains === 'string' ? saved.domains.slice(0, 32768) : '';
      // Drafts created before the format choice used nested terms. Preserve
      // that reading unless their author explicitly chooses another format.
      vm.certificateFormat = ['steps', 'incremental'].includes(saved.certificate_format) ? saved.certificate_format : 'terms';
      if (Number.isInteger(saved.calls) && saved.calls >= 1 && saved.calls <= (vm.certificateFormat === 'incremental' ? 64 : 6)) vm.calls = saved.calls;
      if (Number.isInteger(saved.step_limit) && saved.step_limit >= 1 && saved.step_limit <= 32) vm.stepLimit = saved.step_limit;
      vm.inferenceFormat = saved.inference_format === 'command' ? 'command' : 'json';
      if (typeof saved.by === 'string' && /^[A-Za-z0-9_.:@+*/-]{1,300}$/.test(saved.by)) vm.by = saved.by;
    }
  } catch (_) { }
  vm.domainsOpen = !!vm.domains.trim();
  function el(tag, attrs, ...children) {
    const item = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === 'text') item.textContent = value;
      else if (key === 'class') item.className = value;
      else if (key === 'on') Object.entries(value).forEach(([event, fn]) => item.addEventListener(event, fn));
      else if (['value', 'disabled', 'open'].includes(key)) item[key] = value;
      else item.setAttribute(key, value);
    });
    children.flat().forEach(child => item.appendChild(typeof child === 'string' ? document.createTextNode(child) : child));
    return item;
  }
  function save() {
    vm.compiled = null; vm.stale = true; vm.error = '';
    try { sessionStorage.setItem(KEY, JSON.stringify({ premises: vm.premises, goal: vm.goal, calls: vm.calls,
      domains: vm.domains, certificate_format: vm.certificateFormat, step_limit: vm.stepLimit,
      inference_format: vm.inferenceFormat, by: vm.by })); } catch (_) { }
    const staleError = vm.view && vm.view.querySelector('.sy-logic-error');
    if (staleError) staleError.remove();
    const result = vm.view && vm.view.querySelector('[data-logic-result]');
    if (result) result.replaceChildren(el('p', { class: 'hint', text: 'The task changed. Prepare it again to review its formal reading.' }));
  }
  async function prepare() {
    if (vm.busy) return;
    vm.busy = true; vm.error = ''; vm.compiled = null; vm.stale = false; paint();
    try {
      let domains;
      if (vm.domains.trim()) {
        try { domains = JSON.parse(vm.domains); } catch (_) { throw new Error('Finite domains must be a JSON object of named lists.'); }
      }
      vm.compiled = await Studio.api('/api/automation/symblic/logic/compile',
        { premises: vm.premises, goal: vm.goal, calls: vm.calls, certificate_format: vm.certificateFormat,
          ...(vm.certificateFormat === 'incremental' ? { step_limit: vm.stepLimit } : {}),
          ...(vm.certificateFormat === 'incremental' && vm.inferenceFormat === 'command' ? { inference_format: 'command' } : {}),
          ...(domains === undefined ? {} : { domains }) });
      if (!vm.compiled || !vm.compiled.source || !vm.compiled.formalization) throw new Error('The server returned an incomplete formal task.');
      if (vm.certificateFormat === 'incremental' && vm.inferenceFormat === 'command'
          && vm.compiled.formalization.inference_format !== 'command') throw new Error('The server did not compile the selected command format. Update and restart the server.');
    } catch (error) { vm.error = error.message || 'The task could not be prepared.'; vm.compiled = null; }
    finally { vm.busy = false; paint(); }
  }
  function paint() {
    // The Studio stage is shared by every page. An async response owns only
    // this child view, never the stage after navigation has replaced it.
    const m = vm.view;
    if (!m || !m.isConnected || m.parentElement !== vm.mount) return;
    const premises = el('textarea', { id: 'sy-logic-premises', rows: 7, maxlength: 32768, value: vm.premises,
      spellcheck: 'false', disabled: vm.busy, on: { input: e => { vm.premises = e.target.value; save(); } } });
    const goal = el('textarea', { id: 'sy-logic-goal', rows: 2, maxlength: 8192, value: vm.goal,
      spellcheck: 'false', disabled: vm.busy, on: { input: e => { vm.goal = e.target.value; save(); } } });
    const domains = el('textarea', { id: 'sy-logic-domains', rows: 3, maxlength: 32768, value: vm.domains,
      spellcheck: 'false', disabled: vm.busy, on: { input: e => { vm.domains = e.target.value; save(); } } });
    const incremental = vm.certificateFormat === 'incremental';
    const calls = el('input', { id: 'sy-logic-calls', type: 'number', min: 1, max: incremental ? 64 : 6, value: vm.calls,
      disabled: vm.busy, on: { input: e => { vm.calls = Number(e.target.value); save(); } } });
    const stepLimit = el('input', { id: 'sy-logic-steps', type: 'number', min: 1, max: 32, value: vm.stepLimit,
      disabled: vm.busy, on: { input: e => { vm.stepLimit = Number(e.target.value); save(); } } });
    const format = el('select', { id: 'sy-logic-format', class: 'field', disabled: vm.busy,
      on: { change: e => {
        vm.certificateFormat = e.target.value;
        vm.calls = vm.certificateFormat === 'incremental' ? Math.max(vm.calls, 32) : Math.min(vm.calls, 6);
        save(); paint();
      } } },
      el('option', { value: 'incremental', text: 'One inference per fresh context' }),
      el('option', { value: 'steps', text: 'Flat proof steps' }),
      el('option', { value: 'terms', text: 'Nested proof terms' }));
    format.value = vm.certificateFormat;
    const inference = el('select', { id: 'sy-logic-inference', class: 'field', disabled: vm.busy,
      on: { change: e => { vm.inferenceFormat = e.target.value; save(); } } },
      el('option', { value: 'json', text: 'JSON inference record' }),
      el('option', { value: 'command', text: 'One inference command' }));
    inference.value = vm.inferenceFormat;
    const modelChoice = el('div', { id: 'sy-logic-applicator' });
    const chosenBy = () => vm.by || (vm.actions.currentBy ? vm.actions.currentBy() : '');
    const form = el('div', { class: 'unit sy-logic-form' },
      el('span', { class: 'lbl', text: 'Model-constructed logic' }), el('h2', { text: 'State premises. Ask for a derivation.' }),
      el('p', { class: 'hint', text: 'The model builds the proof. General inference rules check every step. A passed proof is conditional on your premises; failure to find a proof does not make the goal false.' }),
      el('label', { for: 'sy-logic-premises', text: 'Named premises · one per line' }), premises,
      el('label', { for: 'sy-logic-goal', text: 'Goal' }), goal,
      el('p', { class: 'hint', text: 'Put proposition text in double quotes. Combine it with and, or, implies, not and parentheses. Quoted sentences are propositions; English words inside them do not create extra inference rules.' }),
      el('details', { open: vm.domainsOpen, on: { toggle: e => { if (e.target.isConnected) vm.domainsOpen = e.target.open; } } }, el('summary', { text: 'Finite domains and quantified statements' }),
        el('p', { class: 'hint', text: 'Optional: declare the exact finite universe as JSON, for example {"People":["Ada","Ben"]}. Then use forall x in People: Kind(x:People), or Kind(People["Ada"]). Quantifiers range only over this list; its completeness in the real world is an assumption.' }),
        el('label', { for: 'sy-logic-domains', text: 'Finite domains (blank for propositional logic)' }), domains),
      el('details', { open: vm.proofOpen, on: { toggle: e => { if (e.target.isConnected) vm.proofOpen = e.target.open; } } },
        el('summary', { text: 'Proof format' }),
        el('p', { class: 'hint', text: 'One inference per fresh context gives the model your premises, goal and checked progress for each step. It repairs a rejected inference before continuing and stops when a complete proof passes. Flat steps and nested terms ask for the whole proof in one response.' }),
        el('label', { for: 'sy-logic-format', text: 'Proof certificate format' }), format,
        ...(incremental ? [el('label', { for: 'sy-logic-inference', text: 'Inference answer format' }), inference,
          el('p', { class: 'hint', text: 'Commands such as implies_elim s2 s1 use the same proof rules. The model chooses the rule and references; the host checks them. JSON records remain available.' }),
          el('label', { for: 'sy-logic-steps', text: 'Maximum accepted proof steps' }), stepLimit,
          el('p', { class: 'hint', text: 'Every inference and correction uses the shared model-call allowance below. Reaching either limit preserves the evidence and leaves the proof unfinished.' })] : [])),
      el('label', { for: 'sy-logic-calls', text: 'Maximum model calls, including corrections' }), calls,
      el('span', { class: 'lbl', text: 'Who constructs the proof' }), modelChoice,
      el('button', { class: 'btn primary', disabled: vm.busy, text: vm.busy ? 'Preparing…' : 'Prepare proof task', on: { click: prepare } }));
    if (vm.error) form.appendChild(el('p', { class: 'sy-logic-error', role: 'alert', text: vm.error }));
    const result = el('div', { 'data-logic-result': '', 'aria-live': 'polite' });
    if (vm.stale) result.appendChild(el('p', { class: 'hint', text: 'The task changed. Prepare it again to review its formal reading.' }));
    if (vm.compiled) {
      const compiled = vm.compiled;
      const reading = el('div', { class: 'unit' }, el('span', { class: 'lbl', text: 'Formal reading' }),
        el('h3', { text: compiled.formalization.goal }),
        el('p', { class: 'hint', text: compiled.assurance }),
        el('ul', {}, ...compiled.formalization.premises.map(row => el('li', { text: row.name + ': ' + row.formula }))),
        el('p', { class: 'hint', text: 'Preparing this task made no model calls. Open it in Write to inspect and run it with your selected model.' }),
        el('button', { class: 'btn primary', text: 'Open in Write', on: { click: () => vm.actions.open({ ...compiled, by: chosenBy() }) } }));
      const details = el('details', {}, el('summary', { text: 'Inspect generated program and exact inputs' }),
        el('pre', { text: compiled.source }), el('pre', { text: JSON.stringify(compiled.inputs, null, 2) }));
      if (compiled.formalization.certificate_format) {
        const format = compiled.formalization.certificate_format;
        reading.appendChild(el('p', { class: 'hint', 'data-logic-format': '', text: 'Prepared proof format: ' +
          ({ incremental: 'One inference per fresh context', steps: 'Flat proof steps', terms: 'Nested proof terms' }[format] || format) }));
      }
      if (compiled.formalization.inference_format) reading.appendChild(el('p', {
        class: 'hint', 'data-logic-inference': '', text: 'Prepared inference answers: ' +
          ({command: 'One inference command', json: 'JSON inference record'}[compiled.formalization.inference_format]
            || compiled.formalization.inference_format),
      }));
      if (compiled.formalization.domains) {
        reading.appendChild(el('p', { class: 'hint', text: 'Declared finite universe · only these members are quantified over:' }));
        reading.appendChild(el('pre', { text: JSON.stringify(compiled.formalization.domains, null, 2) }));
      }
      reading.appendChild(details); result.appendChild(reading);
    }
    m.replaceChildren(form, result);
    if (window.SymblicPicker?.mountChoices) window.SymblicPicker.mountChoices(modelChoice, {
      label: 'Proof applicator', getValue: chosenBy, disabled: () => vm.busy,
      emptyLabel: 'Use the current Write choice', onSelect: by => { vm.by = by; save(); }
    });
    else modelChoice.textContent = 'The model picker is unavailable. Open in Write to enter an applicator.';
  }
  window.SymblicLogic = { render(mount, actions) {
    vm.mount = mount; vm.actions = actions; vm.view = el('div', { class: 'sy-logic' });
    mount.replaceChildren(vm.view); paint();
  } };
})();
