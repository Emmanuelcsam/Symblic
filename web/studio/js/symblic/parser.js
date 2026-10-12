// Parses the early Symblic text mode (Program:, Use ...:, Module:, Branch:/If:/Else:, Loop:, Parallel:) into
// statements, warnings and stats. This line-oriented workflow language predates the formal language of
// symblic/kernel/ and is not the same language. Pure ES module; tested by tests/browser/symblic-studio-text-mode.mjs.
import { AMBIGUOUS_WORDS, CONTEXT_DIRECTIVES, COMMAND_MAP, KEY_ALIASES } from './constants.js';
import {
  normalizeContextMode,
  stripQuotes,
  stripTrailingPunctuation,
  splitArgs,
  parseValue,
  parseNumber,
  parseParams,
  normalizeScheduleList,
  previewText,
  composeTitle,
  deriveTitle,
  cleanData
} from './utils.js';

export function parseSymblic(text, baseDefaults) {
  const warnings = [];
  const stats = { lines: 0, steps: 0, blocks: 0 };
  let workflowName = 'Symblic Workflow';
  let moduleName = '';
  let currentDefaults = { ...baseDefaults };

  const root = { kind: 'root', body: [] };
  const stack = [root];

  const pushStatement = (statement) => {
    if (!statement) return;
    const top = stack[stack.length - 1];
    if (top.kind === 'branch' || top.kind === 'parallel') {
      if (!top.active) {
        const fallback = {
          label: top.kind === 'branch' ? 'else' : 'lane',
          body: [],
          line: statement.line
        };
        top.branches.push(fallback);
        top.active = fallback;
        warnings.push({ line: statement.line, message: `Missing ${top.kind === 'branch' ? 'If/Else' : 'Lane'} statement. Created a default branch.` });
      }
      top.active.body.push(statement);
      return;
    }
    top.body.push(statement);
  };

  const ensureBranch = (label, line) => {
    const top = stack[stack.length - 1];
    if (!top || top.kind !== 'branch') return;
    const branch = { label, body: [], line };
    top.branches.push(branch);
    top.active = branch;
  };

  const ensureLane = (label, line) => {
    const top = stack[stack.length - 1];
    if (!top || top.kind !== 'parallel') return;
    const lane = { label, body: [], line };
    top.branches.push(lane);
    top.active = lane;
  };

  const lines = text.split(/\r?\n/);
  lines.forEach((line, index) => {
    const raw = line.trim();
    if (!raw) return;
    if (/^(#|\/\/)/.test(raw)) return;

    stats.lines += 1;

    const programMatch = raw.match(/^(program|workflow)\s*:\s*(.+)$/i);
    if (programMatch) {
      workflowName = programMatch[2].trim().replace(/[.!?]+$/, '') || workflowName;
      return;
    }

    const moduleMatch = raw.match(/^module\s*:\s*(.+)$/i);
    if (moduleMatch) {
      moduleName = moduleMatch[1].trim().replace(/[.!?]+$/, '');
      return;
    }

    if (applyDefaultsDirective(raw, currentDefaults)) {
      return;
    }

    if (/^end\s+loop\.?$/i.test(raw)) {
      if (stack[stack.length - 1].kind !== 'loop') {
        warnings.push({ line: index + 1, message: 'End Loop without matching Loop.' });
      } else {
        stack.pop();
      }
      return;
    }

    if (/^end\s+branch\.?$/i.test(raw)) {
      if (stack[stack.length - 1].kind !== 'branch') {
        warnings.push({ line: index + 1, message: 'End Branch without matching Branch.' });
      } else {
        const closed = stack.pop();
        if (!closed.branches.length) {
          warnings.push({ line: index + 1, message: 'Branch block has no If/Else sections.' });
        }
      }
      return;
    }

    if (/^end\s+parallel\.?$/i.test(raw)) {
      if (stack[stack.length - 1].kind !== 'parallel') {
        warnings.push({ line: index + 1, message: 'End Parallel without matching Parallel.' });
      } else {
        const closed = stack.pop();
        if (!closed.branches.length) {
          warnings.push({ line: index + 1, message: 'Parallel block has no lanes.' });
        }
      }
      return;
    }

    if (/^loop\s*:/i.test(raw)) {
      const meta = parseKeyValuePairs(raw.replace(/^loop\s*:/i, '').trim());
      const count = parseNumber(meta.args.count);
      const delaySeconds = parseNumber(meta.args.delaySeconds);
      const loopStatement = {
        kind: 'loop',
        module: moduleName,
        line: index + 1,
        data: {
          count: Number.isFinite(count) ? count : 0,
          delaySeconds: Number.isFinite(delaySeconds) ? delaySeconds : 0
        },
        body: []
      };
      stats.blocks += 1;
      pushStatement(loopStatement);
      stack.push(loopStatement);
      return;
    }

    if (/^branch\s*:?$/i.test(raw) || /^branch\s*:/i.test(raw)) {
      const branchStatement = {
        kind: 'branch',
        module: moduleName,
        line: index + 1,
        branches: [],
        active: null
      };
      stats.blocks += 1;
      pushStatement(branchStatement);
      stack.push(branchStatement);
      return;
    }

    if (/^parallel\s*:?$/i.test(raw) || /^parallel\s*:/i.test(raw)) {
      const parallelStatement = {
        kind: 'parallel',
        module: moduleName,
        line: index + 1,
        branches: [],
        active: null
      };
      stats.blocks += 1;
      pushStatement(parallelStatement);
      stack.push(parallelStatement);
      return;
    }

    if (stack[stack.length - 1].kind === 'branch') {
      const ifMatch = raw.match(/^if\s*:\s*(.+)$/i);
      const elseMatch = raw.match(/^else\s*:?$/i);
      const regexMatch = raw.match(/^regex\s*:\s*(.+)$/i);
      if (ifMatch) {
        const label = `if:${stripQuotes(ifMatch[1].trim().replace(/[.!?]+$/, ''))}`;
        ensureBranch(label, index + 1);
        return;
      }
      if (regexMatch) {
        const label = `regex:${stripQuotes(regexMatch[1].trim())}`;
        ensureBranch(label, index + 1);
        return;
      }
      if (elseMatch) {
        ensureBranch('else', index + 1);
        return;
      }
    }

    if (stack[stack.length - 1].kind === 'parallel') {
      const laneMatch = raw.match(/^(lane|branch)\s*:\s*(.+)$/i);
      if (laneMatch) {
        const label = laneMatch[2].trim().replace(/[.!?]+$/, '');
        ensureLane(label || `Lane ${stack[stack.length - 1].branches.length + 1}`, index + 1);
        return;
      }
      const bulletMatch = raw.match(/^\-\s+(.+)$/);
      if (bulletMatch) {
        ensureLane(`Lane ${stack[stack.length - 1].branches.length + 1}`, index + 1);
        const statement = parseStatement(bulletMatch[1].trim(), currentDefaults, moduleName, warnings, index + 1);
        if (statement) {
          stats.steps += statement.kind === 'node' ? 1 : 0;
        }
        pushStatement(statement);
        return;
      }
    }

    const statement = parseStatement(raw, currentDefaults, moduleName, warnings, index + 1);
    if (statement) {
      stats.steps += statement.kind === 'node' ? 1 : 0;
    }
    pushStatement(statement);
  });

  if (stack.length > 1) {
    for (let i = stack.length - 1; i > 0; i -= 1) {
      const open = stack[i];
      warnings.push({ line: open.line || lines.length, message: `Unclosed ${open.kind} block.` });
    }
  }

  return { workflowName, statements: root.body, warnings, stats };
}

function applyDefaultsDirective(raw, defaults) {
  const directivePairs = [
    { key: 'provider', pattern: /^(use\s+)?provider\s*:\s*(.+)$/i },
    { key: 'model', pattern: /^(use\s+)?model\s*:\s*(.+)$/i },
    { key: 'system', pattern: /^(use\s+)?system\s*:\s*(.+)$/i },
    { key: 'responseStyle', pattern: /^(use\s+)?response\s*style\s*:\s*(.+)$/i },
    { key: 'contextKey', pattern: /^(use\s+)?context\s*key\s*:\s*(.+)$/i },
    { key: 'contextScope', pattern: /^(use\s+)?context\s*scope\s*:\s*(.+)$/i },
    { key: 'outputMode', pattern: /^(use\s+)?output\s*mode\s*:\s*(.+)$/i },
    { key: 'contextMode', pattern: /^(use\s+)?context\s*mode\s*:\s*(.+)$/i },
    { key: 'maxMessages', pattern: /^(use\s+)?max\s*messages\s*:\s*(.+)$/i },
    { key: 'maxChars', pattern: /^(use\s+)?max\s*chars\s*:\s*(.+)$/i },
    { key: 'maxTokens', pattern: /^(use\s+)?max\s*tokens\s*:\s*(.+)$/i },
    { key: 'contextWindow', pattern: /^(use\s+)?context\s*window\s*:\s*(.+)$/i },
    { key: 'temperature', pattern: /^(use\s+)?temperature\s*:\s*(.+)$/i },
    { key: 'fileInputs', pattern: /^(use\s+)?attach\s*files\s*:\s*(.+)$/i },
    { key: 'fileMaxChars', pattern: /^(use\s+)?file\s*max\s*chars\s*:\s*(.+)$/i }
  ];

  for (const directive of directivePairs) {
    const match = raw.match(directive.pattern);
    if (match) {
      const value = match[2].trim();
      if (directive.key === 'contextMode') {
        defaults.contextMode = normalizeContextMode(value);
      } else if (directive.key === 'maxMessages' || directive.key === 'maxChars' || directive.key === 'maxTokens' || directive.key === 'contextWindow' || directive.key === 'temperature' || directive.key === 'fileMaxChars') {
        defaults[directive.key] = parseNumber(value);
      } else {
        defaults[directive.key] = stripQuotes(value.replace(/[.!?]+$/, ''));
      }
      return true;
    }
  }

  const defaultsMatch = raw.match(/^defaults\s*:\s*(.+)$/i);
  if (defaultsMatch) {
    const parsed = parseKeyValuePairs(defaultsMatch[1]);
    Object.entries(parsed.args).forEach(([key, value]) => {
      if (key === 'contextMode') {
        defaults.contextMode = normalizeContextMode(value);
        return;
      }
      defaults[key] = value;
    });
    return true;
  }

  return false;
}

function parseStatement(raw, defaults, moduleName, warnings, line) {
  const prefixed = stripContextPrefix(raw);
  if (prefixed.changed) {
    if (prefixed.value) {
      return buildLLMStatement(prefixed.value, prefixed.mode, defaults, moduleName, warnings, line);
    }
    warnings.push({ line, message: 'Context directive has no instruction.' });
    return null;
  }

  const commandMatch = raw.match(/^([A-Za-z][A-Za-z0-9 _-]*)\s*:\s*(.*)$/);
  if (commandMatch) {
    const keyword = commandMatch[1].trim().toLowerCase();
    const rest = commandMatch[2].trim();
    const command = normalizeCommand(keyword);
    if (command) {
      if (command === 'llm') {
        const llmPrefixed = stripContextPrefix(rest);
        const prompt = llmPrefixed.value || rest;
        const contextMode = llmPrefixed.changed ? llmPrefixed.mode : null;
        return buildLLMStatement(prompt, contextMode, defaults, moduleName, warnings, line);
      }
      return buildNodeStatement(command, rest, defaults, moduleName, warnings, line);
    }
    warnings.push({ line, message: `Unknown command "${commandMatch[1]}". Treated as LLM.` });
  }

  return buildLLMStatement(raw, null, defaults, moduleName, warnings, line);
}

function stripContextPrefix(text) {
  for (const directive of CONTEXT_DIRECTIVES) {
    for (const pattern of directive.patterns) {
      if (pattern.test(text)) {
        return { changed: true, mode: directive.mode, value: text.replace(pattern, '').trim() };
      }
    }
  }
  return { changed: false, mode: null, value: text };
}

function normalizeCommand(keyword) {
  const normalized = keyword.toLowerCase();
  for (const [command, aliases] of Object.entries(COMMAND_MAP)) {
    if (aliases.includes(normalized)) return command;
  }
  return null;
}

function buildLLMStatement(prompt, contextMode, defaults, moduleName, warnings, line) {
  const finalPrompt = prompt.trim();
  if (!finalPrompt) {
    warnings.push({ line, message: 'Instruction is empty after directives.' });
    return null;
  }

  if (!/[.!?]$/.test(finalPrompt)) {
    warnings.push({ line, message: 'Instruction should end with punctuation.' });
  }

  const ambiguousHits = AMBIGUOUS_WORDS.filter(word => new RegExp(`\\b${word}\\b`, 'i').test(finalPrompt));
  if (ambiguousHits.length) {
    warnings.push({ line, message: `Avoid ambiguous words: ${ambiguousHits.join(', ')}.` });
  }

  if (finalPrompt.length > 240) {
    warnings.push({ line, message: 'Instruction is long; consider splitting into shorter lines.' });
  }

  const data = buildLLMData(finalPrompt, contextMode, defaults);
  return {
    kind: 'node',
    nodeType: 'ollama',
    module: moduleName,
    line,
    title: deriveTitle(finalPrompt, moduleName),
    data
  };
}

function buildLLMData(prompt, contextMode, defaults) {
  const data = {
    provider: defaults.provider,
    model: defaults.model,
    system: defaults.system,
    responseStyle: defaults.responseStyle,
    prompt,
    contextKey: defaults.contextKey,
    contextScope: defaults.contextScope,
    contextMode: contextMode || defaults.contextMode || 'clear',
    outputMode: defaults.outputMode,
    maxMessages: defaults.maxMessages,
    maxChars: defaults.maxChars,
    maxTokens: defaults.maxTokens,
    contextWindow: defaults.contextWindow,
    temperature: defaults.temperature,
    fileInputs: defaults.fileInputs,
    fileMaxChars: defaults.fileMaxChars
  };
  return cleanData(data, ['contextMode']);
}

function buildNodeStatement(command, rest, defaults, moduleName, warnings, line) {
  const parsed = parseKeyValuePairs(rest);
  const hasPairs = Object.keys(parsed.args).length > 0;
  const text = hasPairs ? '' : rest;

  switch (command) {
    case 'websearch': {
      const query = parsed.args.query || stripTrailingPunctuation(text);
      if (!query) {
        warnings.push({ line, message: 'Web Search requires a query.' });
      }
      const data = cleanData({
        query,
        maxResults: parsed.args.maxResults
      });
      return buildSimpleStatement('websearch', `Search - ${previewText(query)}`, data, moduleName, line);
    }
    case 'webfetch': {
      const url = parsed.args.url || stripTrailingPunctuation(text);
      if (!url) {
        warnings.push({ line, message: 'Fetch URL requires a URL.' });
      }
      const data = cleanData({ url, maxChars: parsed.args.maxChars });
      return buildSimpleStatement('webfetch', `Fetch - ${previewText(url)}`, data, moduleName, line);
    }
    case 'readfile': {
      const path = parsed.args.path || stripTrailingPunctuation(text);
      if (!path) {
        warnings.push({ line, message: 'Read File requires a path.' });
      }
      const data = cleanData({ path, maxChars: parsed.args.maxChars });
      return buildSimpleStatement('readfile', `Read - ${previewText(path)}`, data, moduleName, line);
    }
    case 'writefile': {
      const path = parsed.args.path;
      const content = parsed.args.content || parsed.args.message || text;
      if (!path) {
        warnings.push({ line, message: 'Write File requires path=.' });
      }
      if (!content) {
        warnings.push({ line, message: 'Write File requires content=.' });
      }
      const data = cleanData({
        path,
        mode: parsed.args.mode || 'append',
        content
      });
      return buildSimpleStatement('writefile', `Write - ${previewText(path)}`, data, moduleName, line);
    }
    case 'log': {
      const message = parsed.args.message || parsed.args.content || text;
      const data = cleanData({
        path: parsed.args.path,
        message
      });
      if (!message) {
        warnings.push({ line, message: 'Log requires a message.' });
      }
      return buildSimpleStatement('log', `Log - ${previewText(message)}`, data, moduleName, line);
    }
    case 'setvar': {
      const key = parsed.args.key;
      const value = parsed.args.value || text;
      if (!key) {
        warnings.push({ line, message: 'Set Variable requires name= or key=.' });
      }
      if (!value) {
        warnings.push({ line, message: 'Set Variable requires value=.' });
      }
      const data = cleanData({
        key,
        value,
        mode: parsed.args.mode || 'set'
      });
      return buildSimpleStatement('setvar', `Set - ${previewText(key)}`, data, moduleName, line);
    }
    case 'context': {
      const action = parsed.args.action || stripTrailingPunctuation(text ? text.split(/\s+/)[0] : 'clear');
      const message = parsed.args.message || parsed.args.content || (text && text.split(/\s+/).slice(1).join(' '));
      if (!action) {
        warnings.push({ line, message: 'Context requires an action (clear, set, append).' });
      }
      if ((action === 'set' || action === 'append') && !message) {
        warnings.push({ line, message: 'Context set/append requires message=.' });
      }
      const data = cleanData({
        action,
        role: parsed.args.role || 'system',
        message,
        contextKey: parsed.args.contextKey || defaults.contextKey,
        contextScope: parsed.args.contextScope || defaults.contextScope
      });
      return buildSimpleStatement('context', `Context - ${action}`, data, moduleName, line);
    }
    case 'delay': {
      const seconds = parseNumber(parsed.args.seconds || parsed.args.delaySeconds || text);
      if (!Number.isFinite(seconds)) {
        warnings.push({ line, message: 'Delay requires seconds= or a numeric value.' });
      }
      const data = cleanData({ seconds: Number.isFinite(seconds) ? seconds : 0 });
      return buildSimpleStatement('delay', `Delay - ${seconds || 0}s`, data, moduleName, line);
    }
    case 'schedule': {
      const data = cleanData({
        runAt: parsed.args.runAt || stripTrailingPunctuation(text),
        delaySeconds: parsed.args.delaySeconds,
        recurrence: parsed.args.recurrence,
        scheduleList: normalizeScheduleList(parsed.args.scheduleList),
        scheduleMode: parsed.args.scheduleMode
      });
      if (!data.runAt && !data.delaySeconds && !data.recurrence && !data.scheduleList) {
        warnings.push({ line, message: 'Schedule requires runAt=, delaySeconds=, recurrence=, or scheduleList=.' });
      }
      return buildSimpleStatement('schedule', 'Schedule', data, moduleName, line);
    }
    case 'email': {
      const data = cleanData({
        to: parsed.args.to,
        subject: parsed.args.subject,
        body: parsed.args.body || text
      });
      if (!data.to) {
        warnings.push({ line, message: 'Email requires to=.' });
      }
      if (!data.body) {
        warnings.push({ line, message: 'Email requires body=.' });
      }
      return buildSimpleStatement('email', `Email - ${previewText(data.to)}`, data, moduleName, line);
    }
    case 'python_script': {
      const data = cleanData({
        scriptPath: parsed.args.scriptPath || stripTrailingPunctuation(text),
        functionName: parsed.args.functionName,
        inputVar: parsed.args.inputVar,
        inputParam: parsed.args.inputParam,
        outputVar: parsed.args.outputVar,
        params: parseParams(parsed.args.params)
      });
      if (!data.scriptPath) {
        warnings.push({ line, message: 'Python Script requires scriptPath= or a script path.' });
      }
      return buildSimpleStatement('python_script', `Python - ${previewText(data.scriptPath)}`, data, moduleName, line);
    }
    case 'shell': {
      const command = parsed.args.command || parsed.args.cmd || stripTrailingPunctuation(text);
      if (!command) {
        warnings.push({ line, message: 'Shell requires command= or a command string.' });
      }
      const data = cleanData({
        command,
        workdir: parsed.args.workdir || parsed.args.cwd,
        timeoutSeconds: parsed.args.timeoutSeconds || parsed.args.timeout,
        maxChars: parsed.args.maxChars
      });
      return buildSimpleStatement('shell', `Shell - ${previewText(command)}`, data, moduleName, line);
    }
    default:
      warnings.push({ line, message: `Unsupported command: ${command}.` });
      return null;
  }
}

function buildSimpleStatement(nodeType, title, data, moduleName, line) {
  return {
    kind: 'node',
    nodeType,
    module: moduleName,
    line,
    title: composeTitle(title, moduleName),
    data
  };
}

function parseKeyValuePairs(input) {
  if (!input) return { args: {} };
  const parts = splitArgs(input);
  const args = {};
  parts.forEach(part => {
    const trimmed = part.trim();
    if (!trimmed) return;
    let idx = trimmed.indexOf('=');
    if (idx < 0) {
      const colonIdx = trimmed.indexOf(':');
      if (colonIdx > 0 && /^[A-Za-z0-9 _-]+$/.test(trimmed.slice(0, colonIdx).trim())) {
        idx = colonIdx;
      }
    }
    if (idx < 0) return;
    const rawKey = trimmed.slice(0, idx).trim().toLowerCase().replace(/[\s_-]+/g, '');
    const key = KEY_ALIASES[rawKey] || rawKey;
    const rawValue = trimmed.slice(idx + 1).trim();
    const isQuoted = (rawValue.startsWith('"') && rawValue.endsWith('"')) || (rawValue.startsWith("'") && rawValue.endsWith("'"));
    let cleaned = stripQuotes(rawValue);
    if (!isQuoted) {
      cleaned = stripTrailingPunctuation(cleaned);
    }
    args[key] = parseValue(cleaned);
  });
  return { args };
}
