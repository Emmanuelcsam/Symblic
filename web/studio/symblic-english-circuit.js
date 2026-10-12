/* A source-linked view of parsed English connections. Never executes a program. */
(function () {
  'use strict';
  const LABELS = {remember: 'Input', ask: 'Worker', using: 'Selected inputs', accept: 'Check gate',
    calculate: 'Operation', show: 'Output', display: 'Grid output', build: 'Build objective',
    canvas: 'Canvas contract', presentation: 'Player presentation', rule: 'Worker instruction', finish: 'Step boundary'};
  const LIMITS = {statements: 400, plan: 1200, mappings: 1600, source: 131072};
  const list = value => Array.isArray(value) ? value : [];
  const positive = value => Number.isSafeInteger(value) && value > 0;
  const text = value => typeof value === 'string' ? value : '';

  function sourceText(statement, lines) {
    const {line, col, end_line: endLine, end_col: endCol} = statement;
    if (![line, col, endLine, endCol].every(positive) || endLine < line || endLine > lines.length) return null;
    if (line === endLine) return [...lines[line - 1]].slice(col - 1, endCol).join('');
    return [[...lines[line - 1]].slice(col - 1).join(''), ...lines.slice(line, endLine - 1),
      [...lines[endLine - 1]].slice(0, endCol).join('')].join('\n');
  }

  function projectConstruction(compiled, statements, plan, empty) {
    const build = compiled.construction, units = list(build.units);
    const checked = compiled.check || compiled.native;
    if (!['symblic-english-build/1', 'symblic-english-build/2'].includes(build.version) || build.schema_version !== 1 || checked?.ok !== true || !units.length || units.length > 24 ||
        list(build.unmapped_statements).length)
      return empty('Construction connections need a successful check with complete supported construction metadata.');
    const nodes = [], ids = new Map(), bindings = new Map(), owned = new Set(), edges = [], seen = new Set();
    const planRows = new Map(plan.map(row => [row.line, row]));
    const incomplete = () => empty('The construction statement map is incomplete. Check the source again.');
    for (const statement of statements) {
      if (!positive(statement.index) || ids.has(statement.index) || !LABELS[statement.kind]) return incomplete();
      const node = {id: statement.index, line: statement.line, kind: statement.kind, label: LABELS[statement.kind],
        text: statement.text, binds: [], reads: [], checks: [], type: '', parent: null, selected: [], incoming: [],
        outputs: [], nativeLines: list(statement.native_lines).filter(positive)};
      nodes.push(node); ids.set(node.id, node);
    }
    function wire(from, to, binding, role) {
      const key = JSON.stringify([from.id, to.id, binding]);
      if (seen.has(key)) return;
      seen.add(key);
      const edge = {from: from.id, to: to.id, name: binding, label: from.outputs[0].label,
        sourceLine: from.line, targetLine: to.line, role};
      edges.push(edge); to.incoming.push(edge); to.reads.push(binding);
    }
    for (const unit of units) {
      const group = list(unit.statement_ids).map(id => ids.get(id));
      if (!text(unit.name) || !text(unit.binding) || bindings.has(unit.binding) || group.length < 5 ||
          group.some(node => !node || owned.has(node.id)) || new Set(group.map(node => node.id)).size !== group.length)
        return incomplete();
      const asks = group.filter(node => node.kind === 'ask'), gates = group.filter(node => node.kind === 'accept');
      const uses = group.filter(node => node.kind === 'using'), ends = group.filter(node => node.kind === 'finish');
      if (asks.length !== 1 || gates.length !== 1 || uses.length !== 1 || ends.length !== 1 ||
          !group.some(node => node.kind === 'rule') || group.some(node => !['ask', 'accept', 'using', 'finish', 'rule'].includes(node.kind)))
        return incomplete();
      const worker = asks[0], gate = gates[0], selected = list(unit.selected_bindings), names = list(unit.selected_steps);
      const ask = planRows.get(unit.ask_line), check = planRows.get(unit.check_line), assembly = planRows.get(unit.assembly_line), ensure = planRows.get(unit.gate_line);
      if (ask?.kind !== 'ask' || ask.binds !== unit.binding || !worker.nativeLines.includes(unit.ask_line) ||
          check?.kind !== 'let' || assembly?.kind !== 'let' || ensure?.kind !== 'ensure' || !gate.nativeLines.includes(unit.gate_line) ||
          names.length !== selected.length || new Set(selected).size !== selected.length ||
          list(ask.reads).length !== selected.length || list(ask.reads).some(name => !selected.includes(name))) return incomplete();
      worker.type = 'Model-written implementation'; worker.binds.push(unit.binding);
      worker.outputs.push({name: unit.binding, label: unit.name});
      for (let i = 0; i < selected.length; i++) {
        const earlier = bindings.get(selected[i]);
        if (!earlier || earlier.id >= worker.id || earlier.outputs[0].label !== names[i]) return incomplete();
        wire(earlier, worker, selected[i], 'model_context');
      }
      bindings.set(unit.binding, worker);
      for (const name of [...list(check.reads), ...list(assembly.reads)]) {
        const earlier = bindings.get(name);
        if (!earlier) return incomplete();
        wire(earlier, gate, name, 'candidate_check');
      }
      gate.checks.push({kind: 'selected_scope', status: 'not_run'}, {kind: 'assembled_scope', status: 'not_run'});
      gate.connectionLabel = 'Implementations checked:';
      const shown = unit.visible_examples, additional = unit.additional_construction_checks;
      if (Number.isSafeInteger(shown) && shown >= 0 && Number.isSafeInteger(additional) && additional >= 0)
        gate.checkDetail = `${shown} supplied examples and ${additional} additional construction checks, run with selected dependencies and again with assembled work; not run.`;
      for (const node of group) {
        owned.add(node.id);
        if (node !== worker) { node.parent = worker.id; node.parentRelation = node.kind === 'accept' ? 'Checks worker:' : node.kind === 'using' ? 'Selects memory for:' : 'Belongs to worker:'; }
        if (node.kind === 'using') node.selected = [...worker.incoming];
      }
    }
    const standalone = nodes.filter(node => !owned.has(node.id));
    if (standalone.some(node => !['build', 'canvas', 'presentation', 'display'].includes(node.kind))) return incomplete();
    // Display dependencies are declared by the compiler, never inferred from prose or source order.
    const output = build.output, display = ids.get(output?.statement);
    if (!display || display.kind !== 'display' || !Array.isArray(output.selected_bindings) ||
        !output.selected_bindings.length || new Set(output.selected_bindings).size !== output.selected_bindings.length)
      return incomplete();
    for (const name of output.selected_bindings) {
      const earlier = bindings.get(name);
      if (!earlier || earlier.id >= display.id) return incomplete();
      wire(earlier, display, name, 'assembly');
    }
    display.connectionLabel = 'Assembles accepted implementations:';
    return {nodes, edges, notes: [], available: true, mode: 'construction'};
  }

  function projectPixels(compiled, statements, plan, empty) {
    const build = compiled.pixel_build, presentation = compiled.presentation, checked = compiled.check || compiled.native;
    const units = list(build.units), contracts = list(build.plan?.units), order = list(build.plan?.order);
    const obligations = list(presentation?.clause_obligations), incomplete = () =>
      empty('The pixel instruction map is incomplete. Check the current source again.');
    const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    const sha = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
    if (build.version !== 'symblic-english-pixels/1' || checked?.ok !== true || units.length !== 9 ||
        contracts.length !== units.length || order.length !== units.length || new Set(order).size !== order.length ||
        statements.length !== 34 || obligations.length !== statements.length || list(build.unmapped_statements).length ||
        presentation?.kind !== 'binary-pixel-program' || presentation.version !== 1 ||
        presentation.physical_status !== 'unverified' || presentation.software_checks_are_not_physical_proof !== true ||
        presentation.future_frame_precomputation !== false || build.plan?.sheet?.template?.text !== '/*UNITS*/' ||
        build.plan.sheet.template.file !== presentation.implementation_label) return incomplete();
    const nodes = [], sourceNodes = new Map(), byName = new Map(), byContract = new Map(), workers = new Map();
    const edges = [], seen = new Set(), planRows = new Map(), declarations = new Map();
    for (const row of plan) {
      if (!positive(row.line) || planRows.has(row.line)) return incomplete();
      planRows.set(row.line, row);
      if (text(row.binds)) {
        if (declarations.has(row.binds)) return incomplete();
        declarations.set(row.binds, row);
      }
    }
    function node(id, line, kind, label, content, nativeLines) {
      return {id, line, kind, label, text: content, binds: [], reads: [], checks: [], type: '', parent: null,
        selected: [], incoming: [], outputs: [], nativeLines};
    }
    for (const [index, statement] of statements.entries()) {
      const obligation = obligations[index];
      if (!obligation || statement.index !== index + 1 || statement.kind !== 'pixel_obligation' ||
          obligation.statement !== statement.index || obligation.text !== statement.text ||
          !['physical_host', 'software_host', 'model_behavior', 'definition'].includes(obligation.category) ||
          !['physical_unverified', 'not_run'].includes(obligation.status) ||
          obligation.software_checks_are_not_physical_proof !== true ||
          ['line', 'col', 'end_line', 'end_col'].some(key => obligation[key] !== statement[key]) ||
          ([24,25,26,27,28,29,32,33,34].includes(statement.index) !== (obligation.category === 'physical_host')) ||
          (obligation.category === 'physical_host' && (obligation.status !== 'physical_unverified' || obligation.host_required !== true)))
        return incomplete();
      const physical = obligation.category === 'physical_host';
      const row = node(statement.index, statement.line, 'pixel_obligation', physical ? 'Physical display obligation' :
        obligation.host_required ? 'Host obligation' : 'English rule', statement.text, list(statement.native_lines));
      row.obligationStatus = obligation.status;
      row.checkDetail = physical ? 'Physical requirement retained; unverified. This circuit does not measure a monitor, emitted light or a hardware timer.' :
        obligation.host_required ? 'Host requirement retained; this source view has not executed or verified it.' :
        'Authored requirement. The mapped finite implementation checks have not run in this source view.';
      nodes.push(row); sourceNodes.set(row.id, row);
    }
    for (const contract of contracts) {
      if (!contract || !text(contract.id) || byContract.has(contract.id)) return incomplete();
      byContract.set(contract.id, contract);
    }
    for (const unit of units) {
      if (!unit || !text(unit.name) || !text(unit.binding) || byName.has(unit.name) ||
          !positive(unit.examples) ||
          !['model_request','reused_artifact'].includes(unit.acquisition ?? 'model_request') ||
          (unit.binding_kind ?? 'ask') !== (unit.acquisition === 'reused_artifact' ? 'let' : 'ask') ||
          (unit.acquisition === 'reused_artifact' && (!sha(unit.artifact_sha256) || !sha(unit.code_sha256))) ||
          !list(unit.clauses).length || new Set(unit.clauses).size !== unit.clauses.length ||
          unit.clauses.some(id => !sourceNodes.has(id)) || !Array.isArray(unit.uses) ||
          new Set(unit.uses).size !== unit.uses.length || !Array.isArray(unit.native_lines) ||
          unit.native_lines.some(line => !positive(line) || !planRows.has(line))) return incomplete();
      byName.set(unit.name, unit);
    }
    const retained = units.filter(unit => unit.acquisition === 'reused_artifact').length;
    if ((build.kept ?? 0) !== retained || !equal(presentation.functions, units.map(unit => unit.name))) return incomplete();
    for (const statement of statements) {
      const expected = units.filter(unit => unit.clauses.includes(statement.index)).map(unit => unit.name);
      if (!equal(obligations[statement.index - 1].model_units, expected)) return incomplete();
    }
    function wire(from, to, binding, role) {
      const key = JSON.stringify([from.id, to.id, binding]);
      if (seen.has(key)) return;
      seen.add(key);
      const edge = {from: from.id, to: to.id, name: binding, label: from.outputs[0].label,
        sourceLine: from.line, targetLine: to.line, role};
      edges.push(edge); to.incoming.push(edge); to.reads.push(binding);
    }
    const clientVM = build.client_vm;
    const splitParser = clientVM?.version === 'symblic-english-pixel-checks/2';
    const vmHostBindings = splitParser ? ['pixel_vm_parser', 'pixel_vm_boot'] : ['pixel_vm_boot'];
    if (clientVM && (!['symblic-english-pixel-checks/1','symblic-english-pixel-checks/2'].includes(clientVM.version) ||
        (splitParser && (clientVM.assets?.parser_binding !== 'pixel_vm_parser' ||
          clientVM.assets?.host_input !== 'pixel_vm_boot' || declarations.get('pixel_vm_parser')?.kind !== 'let')) ||
        !equal(Object.keys(clientVM.gates || {}).sort(), [...units.map(unit => unit.name), 'assembly'].sort()) ||
        ['parser','vm','presenter'].some(role => !sha(clientVM.assets?.[role]?.sha256) ||
          presentation.assets?.[role]?.sha256 !== clientVM.assets[role].sha256 ||
          presentation.assets?.[role]?.sri !== clientVM.assets[role].sri))) return incomplete();
    const records = [];
    for (const [index, ident] of order.entries()) {
      const contract = byContract.get(ident), names = list(contract?.exports), unit = byName.get(names[0]);
      if (!unit || !Array.isArray(contract.dependencies) || !Array.isArray(contract.closure) ||
          names.length !== 1 || contract.binding !== unit.binding || workers.has(unit.binding) ||
          !equal(contract.contract?.unit?.uses, unit.uses) || !equal(presentation.dependencies?.[unit.name], unit.uses) ||
          !equal(list(contract.dependencies).map(id => byContract.get(id)?.exports?.[0]).sort(), [...unit.uses].sort()) ||
          list(contract.closure).some(id => !workers.has(byContract.get(id)?.binding))) return incomplete();
      const kept = unit.acquisition === 'reused_artifact';
      if (kept && (build.reuse?.[ident]?.reusable !== true || build.reuse[ident].artifact_sha256 !== unit.artifact_sha256)) return incomplete();
      const ask = declarations.get(unit.binding), selected = list(contract.closure).map(id => byContract.get(id).binding);
      if (ask?.kind !== (kept ? 'let' : 'ask') || !unit.native_lines.includes(ask.line) ||
          !equal(list(ask.reads), kept ? [] : ['card_' + unit.binding]) ||
          unit.clauses.some(id => !sourceNodes.get(id).nativeLines.includes(ask.line))) return incomplete();
      const refs = unit.clauses.map(id => ({statement: id, line: sourceNodes.get(id).line}));
      const worker = node('pixel-worker:' + unit.binding, refs[0].line, kept ? 'retained' : 'ask',
        kept ? 'Reused model function' : 'Generated worker',
        unit.name + ' — model-written function for the linked English requirements.', [ask.line]);
      worker.type = kept ? 'Retained model implementation' : 'Model-written implementation'; worker.binds.push(unit.binding);
      worker.outputs.push({name: unit.binding, label: unit.name}); worker.sourceRefs = refs;
      worker.connectionLabel = kept ? 'Declared implementation dependencies:' : 'Supplied dependency implementations:';
      worker.checkDetail = 'Declared direct helpers: ' + (unit.uses.join(', ') || 'none') +
        '. The task card also supplies their transitive dependencies. This view does not prove helper use.';
      if (kept) {
        worker.checkDetail = 'Reused by artifact identity; no new model request. Native gates recheck the retained code before it is used. Declared direct helpers: ' + (unit.uses.join(', ') || 'none') + '.';
        for (const id of contract.dependencies) { const binding = byContract.get(id).binding; wire(workers.get(binding), worker, binding, 'retained_dependency'); }
      } else for (const binding of selected) wire(workers.get(binding), worker, binding, 'model_context');
      workers.set(unit.binding, worker); nodes.push(worker);
      const checkNames = ['declarations_' + unit.binding, 'test_' + unit.name, 'assembly_check_' + index, 'output_check_' + index];
      const gate = node('pixel-gate:' + unit.binding, refs[0].line, 'accept', 'Generated check gate',
        'Finite implementation checks for ' + unit.name + '.', []);
      gate.sourceRefs = refs; gate.parent = worker.id; gate.parentRelation = 'Checks generated worker:';
      gate.connectionLabel = 'Implementations included by these checks:';
      for (const [position, name] of checkNames.entries()) {
        const check = declarations.get(name), kind = position < 2 && !kept ? 'ensure' : 'assert';
        const guard = check && planRows.get(check.line + 1);
        if (check?.kind !== 'let' || !unit.native_lines.includes(check.line) || guard?.kind !== kind ||
            !unit.native_lines.includes(guard.line) || !equal(list(guard.reads), [name]) ||
            (position === 0 && !equal(list(check.reads), [unit.binding])) ||
            unit.clauses.some(id => !sourceNodes.get(id).nativeLines.includes(guard.line))) return incomplete();
        gate.nativeLines.push(check.line, guard.line);
        gate.checks.push({kind: ['declaration_shape', 'selected_scope', 'assembled_scope', 'output_scope'][position],
          status: 'not_run', nativeLine: guard.line});
      }
      if (clientVM) {
        const mapped = clientVM.gates[unit.name], check = planRows.get(mapped?.check_line), guard = planRows.get(mapped?.guard_line);
        if (mapped?.binding !== 'pixel_vm_' + unit.name || mapped.retained !== kept ||
            check?.kind !== 'let' || check.binds !== mapped.binding || guard?.kind !== (kept ? 'assert' : 'ensure') ||
            !equal(list(check.reads), [...vmHostBindings, ...selected, unit.binding].sort()) ||
            !equal(list(guard.reads), [mapped.binding]) ||
            !unit.native_lines.includes(check.line) || !unit.native_lines.includes(guard.line) ||
            unit.clauses.some(id => !sourceNodes.get(id).nativeLines.includes(guard.line))) return incomplete();
        gate.nativeLines.push(check.line, guard.line);
        gate.checks.push({kind: 'client_vm', status: 'not_run', nativeLine: guard.line});
      }
      const scoped = declarations.get(checkNames[1]);
      if (!equal(list(scoped.reads), [...selected, unit.binding].sort())) return incomplete();
      gate.checkDetail = `${unit.examples} supplied examples are checked in dependency scope, full assembly and output; declaration shape is also checked. ${clientVM ? 'The same client interpreter also checks this unit. ' : ''}Checks not run here. They do not verify physical presentation.`;
      nodes.push(gate); records.push({unit, index, gate});
    }
    const allBindings = [...workers.keys()].sort();
    const code = declarations.get('spec_code'), output = declarations.get('spec_output');
    if (!equal(list(code?.reads), allBindings) || !equal(list(output?.reads), ['spec_code'])) return incomplete();
    for (const {index, gate} of records) {
      const assembly = declarations.get('assembly_check_' + index), outputCheck = declarations.get('output_check_' + index);
      if (!equal(list(assembly?.reads), allBindings) || !equal(list(outputCheck?.reads), ['spec_output'])) return incomplete();
      for (const binding of list(assembly.reads)) wire(workers.get(binding), gate, binding, 'candidate_check');
    }
    if (clientVM) {
      const mapped = clientVM.gates.assembly, check = planRows.get(mapped?.check_line), guard = planRows.get(mapped?.guard_line);
      const ids = [...new Set(units.flatMap(unit => unit.clauses))].sort((a,b) => a-b);
      if (mapped?.binding !== 'pixel_vm_assembly' || mapped.retained !== true || check?.kind !== 'let' ||
          check.binds !== mapped.binding || guard?.kind !== 'assert' ||
          !equal(list(check.reads), [...vmHostBindings, ...allBindings].sort()) ||
          !equal(list(guard.reads), [mapped.binding]) ||
          ids.some(id => !sourceNodes.get(id).nativeLines.includes(guard.line))) return incomplete();
      const gate = node('pixel-client-assembly', sourceNodes.get(ids[0]).line, 'accept', 'Client interpreter gate',
        'Check the complete accepted assembly in the same bounded interpreter used for display.', [check.line,guard.line]);
      gate.sourceRefs = ids.map(id => ({statement:id,line:sourceNodes.get(id).line}));
      gate.checks.push({kind:'client_vm_assembly',status:'not_run',nativeLine:guard.line});
      gate.connectionLabel = 'Complete accepted implementation:';
      gate.checkDetail = 'Parser and interpreter identities are pinned. This finite software check does not verify physical light, display mapping or a hardware timer.';
      for (const binding of allBindings) wire(workers.get(binding),gate,binding,'client_vm_check');
      nodes.push(gate);
    }
    return {nodes, edges, notes: [], available: true, mode: 'pixels', sourceStatementCount: statements.length, retainedWorkerCount: retained};
  }

  function project(compiled, source) {
    const empty = message => ({nodes: [], edges: [], notes: [message], available: false});
    const statements = list(compiled?.statements), plan = list(compiled?.check?.plan || compiled?.native?.plan || compiled?.plan);
    const mappings = list(compiled?.source_map);
    if (!statements.length || !plan.length) return empty('Check these statements to see their parsed connections.');
    if (typeof source !== 'string' || source.length > LIMITS.source || statements.length > LIMITS.statements ||
        plan.length > LIMITS.plan || mappings.length > LIMITS.mappings)
      return empty('This source exceeds the circuit view limits. The original statements remain available.');
    const lines = source.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').split('\n');
    if (statements.some(statement => sourceText(statement, lines) !== statement.text))
      return empty('The source changed. Check the current statements to rebuild their connections.');
    if (compiled?.pixel_build) return projectPixels(compiled, statements, plan, empty);
    if (compiled?.construction) return projectConstruction(compiled, statements, plan, empty);
    if (compiled?.check?.ok === false || compiled?.native?.ok === false || plan.some(row => row.depth !== 0))
      return empty('This view requires a successful check of straight-line English statements.');
    const nodes = [], ids = new Map(), byNative = new Map(), notes = [], edges = [], seenEdges = new Set();
    const readable = new Map(Object.entries(compiled.names || {}).map(([name, id]) => [id, name]));
    for (const statement of statements) {
      if (!positive(statement.index) || ids.has(statement.index)) return empty('The statement map is incomplete. Check the source again.');
      const node = {id: statement.index, line: statement.line, kind: statement.kind, label: LABELS[statement.kind] || 'Statement',
        text: statement.text, binds: [], reads: [], checks: [], type: '', parent: null, selected: [], incoming: [],
        nativeLines: list(statement.native_lines).filter(positive)};
      nodes.push(node); ids.set(node.id, node);
      if (!LABELS[statement.kind]) notes.push(`Line ${node.line}: this statement has no circuit-specific component type.`);
      for (const nativeLine of node.nativeLines) {
        if (!byNative.has(nativeLine)) byNative.set(nativeLine, []);
        byNative.get(nativeLine).push(node);
      }
    }
    // The map is authoritative: one generated Ask can map to both Ask and Using only.
    for (const mapping of mappings) {
      const node = ids.get(mapping.statement);
      if (!node || !positive(mapping.native_line)) continue;
      if (!byNative.has(mapping.native_line)) byNative.set(mapping.native_line, []);
      if (!byNative.get(mapping.native_line).includes(node)) byNative.get(mapping.native_line).push(node);
    }
    const bindings = new Map(), askNodes = new Map();
    for (const row of plan) {
      const candidates = byNative.get(row.line) || [];
      const node = candidates.find(candidate => candidate.kind !== 'using');
      if (!node) {
        if (!['use', 'program', 'note', 'section'].includes(row.kind)) notes.push(`Native line ${row.line}: no authored component mapping.`);
        continue;
      }
      if (['ensure', 'assert', 'expect'].includes(row.kind)) node.checks.push({kind: row.kind, status: 'not_run'});
      if (text(row.type)) node.type = row.type;
      for (const name of list(row.reads)) {
        if (typeof name !== 'string' || node.reads.includes(name)) continue;
        node.reads.push(name);
        const origin = bindings.get(name), label = readable.get(name) || name;
        if (!origin) { notes.push(`Line ${node.line}: the input “${label}” has no earlier mapped source.`); continue; }
        if (origin.id === node.id) continue; // A component can expand into several native statements.
        const key = JSON.stringify([origin.id, node.id, name]);
        if (!seenEdges.has(key)) {
          seenEdges.add(key);
          const edge = {from: origin.id, to: node.id, name, label, sourceLine: origin.line, targetLine: node.line};
          edges.push(edge); node.incoming.push(edge);
        }
      }
      // English currently binds one immutable name per Input/Worker. Never guess comma-separated scopes.
      if (typeof row.binds === 'string' && row.binds) {
        if (!node.binds.includes(row.binds)) node.binds.push(row.binds);
        if (bindings.has(row.binds) && bindings.get(row.binds) !== node) {
          notes.push(`Line ${node.line}: duplicate binding “${readable.get(row.binds) || row.binds}”; its wires are omitted.`);
          bindings.delete(row.binds);
        } else bindings.set(row.binds, node);
        if (node.kind === 'ask') askNodes.set(row.binds, node);
      }
    }
    for (const statement of statements) {
      const node = ids.get(statement.index), ask = askNodes.get(statement.ask);
      if (node.kind === 'using') {
        if (ask) { node.parent = ask.id; node.selected = [...ask.incoming]; }
        else notes.push(`Line ${node.line}: selected inputs have no mapped worker.`);
      }
      if (node.kind === 'accept' && ask) node.parent = ask.id;
      node.outputs = node.binds.map(name => ({name, label: readable.get(name) || name}));
    }
    return {nodes, edges, notes: [...new Set(notes)], available: true};
  }

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function render(container, {compiled, source, onSelectLine} = {}) {
    const projection = project(compiled, source), root = element('section', 'sy-en-circuit');
    root.setAttribute('aria-label', 'English program circuit');
    root.append(element('h3', '', 'Your instruction circuit'),
      element('p', 'hint', projection.mode === 'pixels' ? 'Parsed connections; checks not run. Generated workers and check gates are linked to the exact English requirements. Physical display obligations remain unverified.' : projection.mode === 'construction' ? 'Parsed connections; checks not run. Worker memory uses only selected earlier steps. Check and assembly connections are shown separately.' : 'Parsed connections; checks not run. Wires show named values read by each statement.'));
    function sourceButton(line, label) {
      const button = element('button', 'sy-ec-link', label);
      button.type = 'button';
      button.setAttribute('aria-label', `${label}; select English line ${line}`);
      button.addEventListener('click', () => { if (typeof onSelectLine === 'function') onSelectLine(line); });
      return button;
    }
    if (projection.available) {
      const counters = {worker: projection.nodes.filter(node => node.kind === 'ask').length,
        checks: projection.nodes.reduce((sum, node) => sum + node.checks.length, 0)};
      root.append(element('p', 'sy-ec-summary', `${projection.sourceStatementCount || projection.nodes.length} statements · ${counters.worker} ${counters.worker === 1 ? 'worker' : 'workers'}${projection.retainedWorkerCount ? ' · ' + projection.retainedWorkerCount + ' reused model functions' : ''} · ${counters.checks} ${counters.checks === 1 ? 'check' : 'checks'} · ${projection.edges.length} value connections`));
      const components = element('ol', 'sy-ec-components');
      for (const node of projection.nodes) {
        const card = element('li', 'sy-ec-component');
        card.dataset.kind = node.kind; card.dataset.statement = node.id;
        const head = element('div', 'sy-ec-head');
        head.append(element('span', 'sy-ec-kind', node.label), sourceButton(node.line, `Line ${node.line}`));
        if (node.type) head.append(element('span', 'sy-ec-type', node.type));
        if (node.checks.length) head.append(element('span', 'sy-ec-check', `${node.checks.length === 1 ? 'Check' : node.checks.length + ' checks'} not run`));
        card.append(head, element('p', 'sy-ec-source', node.text));
        const connections = node.kind === 'using' ? node.selected : node.incoming;
        if (connections.length) {
          const inputs = element('div', 'sy-ec-connections');
          inputs.append(element('span', '', node.kind === 'using' ? 'Worker memory:' : node.connectionLabel || (projection.mode === 'construction' && node.kind === 'ask' ? 'Worker memory:' : 'Reads:')));
          for (const edge of connections) inputs.append(sourceButton(edge.sourceLine, `${edge.label} ← line ${edge.sourceLine}`));
          card.append(inputs);
        } else if (node.kind === 'ask') card.append(element('p', 'sy-ec-empty', 'No named values selected as model context.'));
        if (node.sourceRefs?.length) {
          const refs = element('div', 'sy-ec-connections'); refs.append(element('span', '', 'English requirements:'));
          for (const ref of node.sourceRefs) refs.append(sourceButton(ref.line, `Statement ${ref.statement} · line ${ref.line}`));
          card.append(refs);
        }
        if (node.checkDetail) card.append(element('p', 'hint', node.checkDetail));
        if (node.outputs.length) card.append(element('p', 'sy-ec-output', 'Produces: ' + node.outputs.map(output => output.label).join(', ')));
        if (node.parent) {
          const parent = projection.nodes.find(candidate => candidate.id === node.parent);
          const relation = element('div', 'sy-ec-owner');
          relation.append(element('span', '', node.parentRelation || (node.kind === 'accept' ? 'Checks worker:' : 'Selects memory for:')), sourceButton(parent.line, `Line ${parent.line}`));
          card.append(relation);
        }
        components.append(card);
      }
      root.append(components, element('p', 'hint', projection.mode === 'pixels' ? 'These are declared construction connections. The client separately runs the accepted implementation one frame at a time; this view neither runs it nor proves physical light, display mapping or timer behavior.' : projection.mode === 'construction' ? 'The model writes each implementation. Its declared finite checks must pass before later workers can use it. This source view does not execute those checks or establish unrestricted correctness.' : 'Checks gate progress in source order. This view shows declared value connections, not runtime values or proof that the instructions achieve your objective.'));
    }
    for (const note of projection.notes) root.append(element('p', 'hint sy-ec-note', note));
    container.replaceChildren(root);
    return projection;
  }
  window.SymblicEnglishCircuit = Object.freeze({render, project});
})();
