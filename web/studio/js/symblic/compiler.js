// Compiles parsed text-mode statements (./parser.js) into an automation-canvas workflow
// {id, name, graph: {nodes, edges}}: a start node, one node per step, branch, loop and parallel blocks. Pure.
import { uuid } from '../utils.js';
import { composeTitle } from './utils.js';

export function buildWorkflow(parsed, settings) {
  const name = settings.workflowName || parsed.workflowName || 'Symblic Workflow';
  const nodes = {};
  const edges = [];
  const layout = {
    index: 0,
    baseX: 140,
    baseY: 140,
    gapX: 240,
    gapY: 160
  };

  const addNode = (type, title, data, yOffset = 0) => {
    const id = uuid();
    const x = layout.baseX + layout.index * layout.gapX;
    const y = layout.baseY + yOffset;
    layout.index += 1;
    nodes[id] = { id, type, title, x, y, data: data || {} };
    return id;
  };

  const connect = (fromList, toId, label) => {
    fromList.forEach(conn => {
      edges.push({ from: conn.id, to: toId, label: conn.label || label || '' });
    });
  };

  const startId = addNode('start', 'Start', {});

  const compileStatements = (statements, connections, yOffset) => {
    let current = connections;
    statements.forEach(statement => {
      if (!statement) return;
      if (statement.kind === 'node') {
        const nodeId = addNode(statement.nodeType, statement.title, statement.data, yOffset);
        connect(current, nodeId);
        current = [{ id: nodeId, label: '' }];
        return;
      }
      if (statement.kind === 'loop') {
        const title = composeTitle(`Loop - ${statement.data.count || 'inf'}x`, statement.module);
        const loopId = addNode('loop', title, statement.data, yOffset);
        connect(current, loopId);
        compileStatements(statement.body || [], [{ id: loopId, label: 'loop' }], yOffset + layout.gapY);
        current = [{ id: loopId, label: 'after' }];
        return;
      }
      if (statement.kind === 'branch') {
        const title = composeTitle('Branch', statement.module);
        const branchId = addNode('branch', title, {}, yOffset);
        connect(current, branchId);
        const branchEnds = [];
        (statement.branches || []).forEach((branch, idx) => {
          if (!branch.body.length) {
            branchEnds.push({ id: branchId, label: branch.label || 'else' });
            return;
          }
          const ends = compileStatements(branch.body, [{ id: branchId, label: branch.label || 'else' }], yOffset + (idx + 1) * layout.gapY);
          ends.forEach(end => branchEnds.push({ id: end.id, label: '' }));
        });
        current = branchEnds.length ? branchEnds : [{ id: branchId, label: '' }];
        return;
      }
      if (statement.kind === 'parallel') {
        const title = composeTitle('Parallel', statement.module);
        const parallelId = addNode('parallel', title, {}, yOffset);
        connect(current, parallelId);
        const laneEnds = [];
        (statement.branches || []).forEach((lane, idx) => {
          if (!lane.body.length) {
            laneEnds.push({ id: parallelId, label: '' });
            return;
          }
          const ends = compileStatements(lane.body, [{ id: parallelId, label: '' }], yOffset + (idx + 1) * layout.gapY);
          ends.forEach(end => laneEnds.push({ id: end.id, label: '' }));
        });
        current = laneEnds.length ? laneEnds : [{ id: parallelId, label: '' }];
      }
    });
    return current;
  };

  compileStatements(parsed.statements, [{ id: startId, label: '' }], 0);

  return {
    id: null,
    name,
    graph: { nodes, edges }
  };
}
