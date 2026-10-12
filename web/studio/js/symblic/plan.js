// Lists parsed text-mode statements as indented plan rows {depth, title, meta}. Pure.
import { composeTitle } from './utils.js';

export function buildPlanItems(statements, depth = 0, items = []) {
  statements.forEach(statement => {
    if (!statement) return;
    if (statement.kind === 'node') {
      items.push({
        depth,
        title: statement.title,
        meta: planMetaForNode(statement)
      });
      return;
    }
    if (statement.kind === 'loop') {
      items.push({
        depth,
        title: composeTitle('Loop', statement.module),
        meta: `count=${statement.data.count || 'inf'}, delay=${statement.data.delaySeconds || 0}s`
      });
      buildPlanItems(statement.body || [], depth + 1, items);
      return;
    }
    if (statement.kind === 'branch') {
      items.push({ depth, title: composeTitle('Branch', statement.module), meta: 'routes by last output' });
      (statement.branches || []).forEach(branch => {
        items.push({ depth: depth + 1, title: branch.label || 'else', meta: 'path' });
        buildPlanItems(branch.body || [], depth + 2, items);
      });
      return;
    }
    if (statement.kind === 'parallel') {
      items.push({ depth, title: composeTitle('Parallel', statement.module), meta: 'runs lanes concurrently' });
      (statement.branches || []).forEach(lane => {
        items.push({ depth: depth + 1, title: lane.label || 'lane', meta: 'lane' });
        buildPlanItems(lane.body || [], depth + 2, items);
      });
    }
  });
  return items;
}

function planMetaForNode(statement) {
  if (statement.nodeType === 'ollama') {
    const mode = statement.data.contextMode || 'clear';
    return `LLM - context ${mode}`;
  }
  const labels = {
    websearch: 'Web Search',
    webfetch: 'Fetch URL',
    readfile: 'Read File',
    writefile: 'Write File',
    log: 'Log',
    setvar: 'Set Variable',
    context: 'Context Control',
    delay: 'Delay',
    schedule: 'Schedule',
    email: 'Email',
    python_script: 'Python Script',
    shell: 'Shell Command'
  };
  return labels[statement.nodeType] || 'Node';
}
