// The text mode's example program and its vocabulary: ambiguous words, context directives, command aliases.
export const DEFAULT_SOURCE = `Program: Symblic Example.
Use Provider: ollama.
Use Model: llama3.1.
Use System: You are a deterministic execution engine. Follow instructions literally.
Module: Intake.
Summarize the client request in one paragraph.
Continue with context. Extract exactly 5 requirements as bullet points.
Branch:
If: "approved"
  Continue with context. Draft the response email.
Else:
  Continue with context. Draft a clarification request.
End Branch.
Loop: count=2, delaySeconds=1.
Continue with context. Refine for clarity.
End Loop.`;

export const AMBIGUOUS_WORDS = [
  'maybe', 'might', 'could', 'should', 'usually', 'often', 'sometimes',
  'likely', 'probably', 'approximately', 'about', 'some', 'various', 'etc'
];

export const CONTEXT_DIRECTIVES = [
  { mode: 'append', patterns: [/^continue with context[.:]?\s*/i, /^continue context[.:]?\s*/i, /^context:\s*(continue|keep|append)[.:]?\s*/i] },
  { mode: 'inherit', patterns: [/^inherit context[.:]?\s*/i, /^context:\s*inherit[.:]?\s*/i] },
  { mode: 'clear', patterns: [/^clear context[.:]?\s*/i, /^reset context[.:]?\s*/i, /^context:\s*(clear|reset)[.:]?\s*/i] }
];

export const COMMAND_MAP = {
  llm: ['llm', 'prompt', 'instruction', 'ask', 'command'],
  websearch: ['web search', 'search web'],
  webfetch: ['fetch url', 'fetch', 'download url'],
  readfile: ['read file', 'readfile'],
  writefile: ['write file', 'writefile'],
  log: ['log', 'audit log'],
  setvar: ['set variable', 'set var', 'variable'],
  context: ['context', 'memory'],
  delay: ['delay', 'wait', 'sleep'],
  schedule: ['schedule', 'run at'],
  email: ['email', 'send email'],
  python_script: ['python', 'python script', 'script'],
  shell: ['shell', 'shell command', 'terminal', 'cli']
};

export const KEY_ALIASES = {
  provider: 'provider',
  model: 'model',
  system: 'system',
  responsestyle: 'responseStyle',
  response_style: 'responseStyle',
  response: 'responseStyle',
  contextkey: 'contextKey',
  context_key: 'contextKey',
  contextscope: 'contextScope',
  context_scope: 'contextScope',
  outputmode: 'outputMode',
  output_mode: 'outputMode',
  contextmode: 'contextMode',
  context_mode: 'contextMode',
  maxmessages: 'maxMessages',
  maxchars: 'maxChars',
  maxtokens: 'maxTokens',
  contextwindow: 'contextWindow',
  temperature: 'temperature',
  fileinputs: 'fileInputs',
  fileinput: 'fileInputs',
  filemaxchars: 'fileMaxChars',
  maxresults: 'maxResults',
  url: 'url',
  path: 'path',
  mode: 'mode',
  content: 'content',
  message: 'message',
  query: 'query',
  key: 'key',
  name: 'key',
  value: 'value',
  action: 'action',
  role: 'role',
  seconds: 'seconds',
  delay: 'delaySeconds',
  delayseconds: 'delaySeconds',
  count: 'count',
  runat: 'runAt',
  recurrence: 'recurrence',
  schedulelist: 'scheduleList',
  schedulemode: 'scheduleMode',
  to: 'to',
  subject: 'subject',
  body: 'body',
  script: 'scriptPath',
  scriptpath: 'scriptPath',
  function: 'functionName',
  functionname: 'functionName',
  inputvar: 'inputVar',
  inputparam: 'inputParam',
  outputvar: 'outputVar',
  params: 'params',
  command: 'command',
  cmd: 'command',
  workdir: 'workdir',
  cwd: 'workdir',
  timeout: 'timeoutSeconds',
  timeoutseconds: 'timeoutSeconds'
};
