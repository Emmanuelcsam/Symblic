// The automation canvas's node catalogue: node types, their fields and help text. Part of the original host's
// automation studio (web/studio/index.html), kept for reference; see web/README.md.
const h = (what, how, why) => `What: ${what}\nHow: ${how}\nWhy: ${why}`;

const HELP = {
  title: h(
    'Display name shown on the canvas and in lists.',
    'Use a short verb + object (e.g., "Summarize Notes").',
    'Clear titles make large workflows readable.'
  ),
  provider: h(
    'Which LLM provider to call for this node.',
    'Choose the provider you have configured.',
    'Different providers offer different models and cost.'
  ),
  model: h(
    'Model name sent to the provider.',
    'Use the exact model id the provider expects.',
    'Controls speed, cost, and output quality.'
  ),
  system: h(
    'System-level instructions that define role and constraints.',
    'Describe behavior, tone, and guardrails.',
    'Strong system prompts produce consistent outputs.'
  ),
  responseStyle: h(
    'Formatting or style constraints for the response.',
    'Request JSON, bullet points, or a specific structure.',
    'Keeps downstream nodes predictable.'
  ),
  prompt: h(
    'Main user prompt content for the LLM.',
    'Write the task and include variables like {{last_output}}.',
    'This is the core instruction the model follows.'
  ),
  fileInputs: h(
    'Files to inject into the prompt context.',
    'Provide comma-separated file paths.',
    'Supplies long references without copy/paste.'
  ),
  fileMaxChars: h(
    'Character cap per attached file.',
    'Set a limit to avoid oversized prompts.',
    'Protects the context window and reduces latency.'
  ),
  contextKey: h(
    'Memory key used to read/write context.',
    'Use "default" or a custom key for parallel threads.',
    'Separate tasks can store different histories.'
  ),
  contextScope: h(
    'Where the context is stored.',
    'Choose workflow, global, or custom.',
    'Prevents accidental cross-workflow leakage.'
  ) + '\nOptions: workflow (this flow), global (shared), custom (use context key).',
  contextMode: h(
    'How this node updates context.',
    'Append adds, clear resets, inherit reads without write.',
    'Keeps memory state intentional.'
  ) + '\nOptions: append (add), clear (reset), inherit (read-only).',
  maxMessages: h(
    'Maximum messages sent to the model.',
    'Set a count cap; blank uses defaults.',
    'Limits history length for cost and speed.'
  ),
  maxChars: h(
    'Maximum characters allowed in prompt or output.',
    'Set a size cap to guard against long data.',
    'Keeps responses manageable and on budget.'
  ),
  maxTokens: h(
    'Maximum tokens for model output.',
    'Set a token cap; blank uses defaults.',
    'Controls cost and response length.'
  ),
  contextWindow: h(
    'Model context window size for Ollama.',
    'Set to match your local model limit.',
    'Prevents truncation and errors.'
  ),
  temperature: h(
    'Randomness of model output.',
    '0.0 is deterministic; higher is more creative.',
    'Tune consistency vs. variety.'
  ),
  outputMode: h(
    'Where to send the model output.',
    'Choose app, email, both, or silent.',
    'Control delivery channel per step.'
  ) + '\nOptions: app, email, both, silent.',
  emailTo: h(
    'Email recipient for model output.',
    'Provide one or more addresses.',
    'Send results outside the app.'
  ),
  emailSubject: h(
    'Subject line for the output email.',
    'Provide a clear subject.',
    'Helps recipients identify the run.'
  ),
  emailToGeneric: h(
    'Email recipients.',
    'Use a comma-separated list or a single address.',
    'Deliver notifications or reports.'
  ),
  emailSubjectGeneric: h(
    'Subject line for the email.',
    'Keep it short and descriptive.',
    'Inboxes are easier to scan.'
  ),
  emailBody: h(
    'Email body content.',
    'Write content or use variables like {{last_output}}.',
    'Delivers results or alerts.'
  ),
  query: h(
    'Search query to run.',
    'Use keywords or operators like site: and quotes.',
    'Pulls external info into the flow.'
  ),
  maxResults: h(
    'Limit for search results.',
    'Set a small number for speed.',
    'Controls downstream noise.'
  ),
  url: h(
    'URL to fetch.',
    'Provide a full http(s) URL.',
    'Ingests page content.'
  ),
  filePath: h(
    'File path on the server.',
    'Use a relative or absolute path.',
    'Allows automations to read or write files.'
  ),
  writeMode: h(
    'How file writes behave.',
    'Append adds to end, overwrite replaces file.',
    'Choose based on audit vs. replacement needs.'
  ) + '\nOptions: append, overwrite.',
  content: h(
    'Content to write to the file.',
    'Use raw text or variables.',
    'Persist outputs or state.'
  ),
  seconds: h(
    'Delay time in seconds.',
    'Use integers; 60 equals one minute.',
    'Throttle or wait between steps.'
  ),
  runAt: h(
    'Target time to run this node.',
    'Use ISO timestamps or natural language.',
    'Schedule execution precisely.'
  ),
  delaySeconds: h(
    'Additional delay before continuing.',
    'Provide seconds; 0 for no delay.',
    'Staggers recurring work.'
  ),
  recurrence: h(
    'Recurrence rule for repeated runs.',
    'Use phrases like "every 2 weeks" or "daily at 09:00".',
    'Automates recurring schedules.'
  ),
  scheduleList: h(
    'List of explicit run times.',
    'One time per line using ISO or natural language.',
    'Precise multi-date schedules.'
  ),
  scheduleMode: h(
    'How the schedule list is used.',
    'Once runs each time once; cycle loops through list.',
    'Control whether schedules repeat.'
  ) + '\nOptions: once, cycle.',
  count: h(
    'Number of loop iterations.',
    '0 means infinite; set a count to cap loops.',
    'Avoid unbounded runs.'
  ),
  action: h(
    'Context action to take.',
    'Clear wipes memory, set replaces, append adds.',
    'Control conversation history.'
  ) + '\nOptions: clear, set, append.',
  role: h(
    'Role used when writing to context.',
    'Choose system, user, or assistant.',
    'Roles influence model behavior.'
  ) + '\nOptions: system, user, assistant.',
  message: h(
    'Message to write into context.',
    'Use plain text or variables.',
    'Provide persistent instructions or data.'
  ),
  variableName: h(
    'Variable name to store.',
    'Use a concise key like "job_list".',
    'Reuse values across nodes.'
  ),
  variableMode: h(
    'How to update the variable.',
    'Set replaces, append adds to existing value.',
    'Build accumulative context.'
  ) + '\nOptions: set, append.',
  variableValue: h(
    'Value to store in the variable.',
    'Use text or variables like {{last_output}}.',
    'Capture outputs for later steps.'
  ),
  mailbox: h(
    'Email mailbox to read.',
    'Use folders like INBOX or custom labels.',
    'Target the right messages.'
  ),
  limit: h(
    'Max number of emails to process.',
    'Set a small number while testing.',
    'Avoid large unintended runs.'
  ),
  dryRun: h(
    'Whether to send real replies.',
    'True logs actions without sending; false sends.',
    'Test safely before going live.'
  ) + '\nTip: keep true while testing.',
  rules: h(
    'Rule list for auto replies.',
    'Add rule rows with match type and reply text.',
    'Automate responses to common patterns.'
  ),
  logPath: h(
    'File path for logs.',
    'Choose a writable path.',
    'Keep an audit trail.'
  ),
  logMessage: h(
    'Message to log.',
    'Compose text and variables like {{last_output}}.',
    'Track what happened in each run.'
  ),
  scriptPath: h(
    'Path to a Python script relative to the scripts folder.',
    'Use a .py file from the Script Library or type a path.',
    'Loads custom logic into the workflow.'
  ),
  functionName: h(
    'Function name to call inside the script.',
    'Defaults to process_image, process, or run if left blank.',
    'Targets the exact entry point you want.'
  ),
  inputVar: h(
    'Variable name to inject into the script call.',
    'Set to a stored variable like image_path or last_output.',
    'Passes data from earlier nodes into the script.'
  ),
  inputParam: h(
    'Parameter name that receives the input value.',
    'Match the function argument name (e.g., image or path).',
    'Ensures the script receives the correct input.'
  ),
  outputVar: h(
    'Variable name to store the script result.',
    'Set a key like processed_image for downstream nodes.',
    'Keeps outputs reusable without re-running the script.'
  ),
  paramsJson: h(
    'JSON object of parameters passed to the script.',
    'Example: {\"threshold\": 120, \"sigma\": 1.4}.',
    'Enables precise, code-level control of script behavior.'
  ),
  scriptParams: h(
    'Editable parameters inferred from the script signature.',
    'Change values to match the function arguments.',
    'Faster than editing JSON while still precise.'
  ),
  shellCommand: h(
    'Shell command to run on the server.',
    'Provide a command string such as ls -la or npm test.',
    'Use when you need OS-level automation (requires enablement).'
  ),
  shellWorkdir: h(
    'Working directory for the shell command.',
    'Provide a path or leave blank to use the server default.',
    'Controls where the command is executed.'
  ),
  shellTimeout: h(
    'Time limit for the shell command in seconds.',
    'Set a limit to prevent hanging commands.',
    'Helps keep runs predictable and safe.'
  ),
  shellMaxChars: h(
    'Maximum characters to return from the command output.',
    'Trim large outputs for safer logs.',
    'Keeps context sizes manageable.'
  )
};

export const NODE_TYPES = [
  { type: 'start', title: 'Start', help: h('Entry point for the workflow.', 'Place one Start node and connect it to the first step.', 'Defines where execution begins.') },
  { type: 'ollama', title: 'Ollama Prompt', help: h('Call an LLM to generate or transform text.', 'Set provider, model, prompts, and context fields.', 'Use for reasoning, summarizing, or writing steps.') },
  { type: 'context', title: 'Context Control', help: h('Manage stored conversation context.', 'Choose clear/set/append, role, and message.', 'Control memory across LLM nodes.') },
  { type: 'setvar', title: 'Set Variable', help: h('Store or append a variable value.', 'Set a key and value, optionally using {{last_output}}.', 'Reuse data across nodes.') },
  { type: 'email', title: 'Send Email', help: h('Send a custom email message.', 'Set recipients, subject, and body.', 'Notify people or deliver results.') },
  { type: 'websearch', title: 'Web Search', help: h('Run a search query and return results.', 'Enter query text and limit results.', 'Gather external information.') },
  { type: 'webfetch', title: 'Fetch URL', help: h('Download content from a URL.', 'Provide a full URL and size cap.', 'Ingest web pages into the workflow.') },
  { type: 'readfile', title: 'Read File', help: h('Read a local file into the workflow.', 'Provide the file path and size limit.', 'Use local data as input.') },
  { type: 'writefile', title: 'Write File', help: h('Write content to a local file.', 'Choose append or overwrite and specify content.', 'Persist outputs or logs.') },
  { type: 'delay', title: 'Delay', help: h('Pause execution for a period.', 'Set the number of seconds to wait.', 'Throttle or space out actions.') },
  { type: 'schedule', title: 'Schedule', help: h('Wait until a scheduled time before continuing.', 'Set run time, recurrence, or a list of times.', 'Align automation with real-world timing.') },
  { type: 'branch', title: 'Branch', help: h('Split the flow into conditional paths.', 'Label outgoing edges with if: or else.', 'Route execution based on conditions.') },
  { type: 'parallel', title: 'Parallel', help: h('Fan out work into parallel branches.', 'Connect multiple outgoing edges.', 'Run tasks concurrently.') },
  { type: 'loop', title: 'Loop', help: h('Repeat a section of the workflow.', 'Use loop/after edge labels and set count/delay.', 'Automate repeated tasks.') },
  { type: 'email_reply', title: 'Email Auto Reply', help: h('Auto-reply to emails based on rules.', 'Set mailbox, limit, and rules; start in dry run.', 'Automate responses safely.') },
  { type: 'log', title: 'Log', help: h('Write a message to a log file.', 'Set a log path and message.', 'Keep an audit trail for runs.') },
  { type: 'python_script', title: 'Python Script', help: h('Run a Python script from the script library.', 'Select a script, set params, and wire inputs/outputs.', 'Bring custom code into the workflow.') },
  { type: 'shell', title: 'Shell Command', help: h('Run a shell command on the server.', 'Provide a command and optional working directory.', 'Use for OS-level automation when enabled.') },
  { type: 'agent', title: 'Agent', help: h('Ask any agent the host runs: Claude, Codex, Antigravity, or a local model on a worker node.', 'Pick the agent and effort, write the prompt; {{last_output}} works.', 'Agents run on the worker nodes, not on the host machine.') },
  { type: 'council', title: 'Council', help: h('Put the prompt to a full council of the host\'s agents (several agents propose, debate, vote).', 'Pick a council template and write the question.', 'For decisions too important for one model. Takes minutes.') },
  { type: 'triad', title: 'Pipeline', help: h('Hand a coding task to the three-agent pipeline on the host.', 'Write the task; the step returns the agent id at once.', 'Long work runs on the host\'s agent hub; the workflow carries on.') },
  { type: 'symblic', title: 'Symblic Program', help: h('Run a Symblic program as one step.', 'Paste the program; its `given` inputs come from this workflow\'s variables, its results come back as symblic_<name>.', 'Formal steps are exact; model steps are typed and checked.') }
];

export const APPLICATORS = ['claude:haiku', 'claude:sonnet', 'claude:opus', 'codex', 'agy', 'mistral', 'ollama:qwen3:4b-instruct',
  'ollama:llama3.2:1b', 'ollama:gemma3:4b', 'ollama:phi4-mini', 'gemini:flash', 'gemini:pro', 'chatgpt'];

export const NODE_HELP = NODE_TYPES.reduce((acc, node) => {
  acc[node.type] = node.help;
  return acc;
}, {});

export const NODE_FIELDS = {
  start: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title }
  ],
  ollama: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'provider', label: 'Provider', type: 'select', options: ['ollama', 'openai', 'anthropic', 'gemini', 'perplexity'], help: HELP.provider },
    { key: 'model', label: 'Model', type: 'text', help: HELP.model },
    { key: 'system', label: 'System Prompt', type: 'textarea', help: HELP.system },
    { key: 'responseStyle', label: 'Response Style (optional)', type: 'textarea', placeholder: 'e.g., short bullet points, JSON, formal', help: HELP.responseStyle },
    { key: 'prompt', label: 'User Prompt', type: 'textarea', help: HELP.prompt },
    { key: 'fileInputs', label: 'Attach Files (optional)', type: 'textarea', placeholder: 'path/to/file.txt, notes.md', help: HELP.fileInputs },
    { key: 'fileMaxChars', label: 'File Max Chars', type: 'number', help: HELP.fileMaxChars },
    { key: 'contextKey', label: 'Context Key', type: 'text', placeholder: 'default', help: HELP.contextKey },
    { key: 'contextScope', label: 'Context Scope', type: 'select', options: ['workflow', 'global', 'custom'], help: HELP.contextScope },
    { key: 'contextMode', label: 'Context Mode (inherit = read-only)', type: 'select', options: ['append', 'clear', 'inherit'], help: HELP.contextMode },
    { key: 'maxMessages', label: 'Max Messages', type: 'number', help: HELP.maxMessages },
    { key: 'maxChars', label: 'Max Chars', type: 'number', help: HELP.maxChars },
    { key: 'maxTokens', label: 'Max Tokens', type: 'number', help: HELP.maxTokens },
    { key: 'contextWindow', label: 'Ollama Context Window', type: 'number', placeholder: 'e.g., 4096', help: HELP.contextWindow },
    { key: 'temperature', label: 'Temperature', type: 'number', step: '0.1', help: HELP.temperature },
    { key: 'outputMode', label: 'Output Mode', type: 'select', options: ['both', 'app', 'email', 'silent'], help: HELP.outputMode },
    { key: 'emailTo', label: 'Email Output To', type: 'text', help: HELP.emailTo },
    { key: 'emailSubject', label: 'Email Subject', type: 'text', help: HELP.emailSubject }
  ],
  email: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'to', label: 'To', type: 'text', help: HELP.emailToGeneric },
    { key: 'subject', label: 'Subject', type: 'text', help: HELP.emailSubjectGeneric },
    { key: 'body', label: 'Body', type: 'textarea', help: HELP.emailBody }
  ],
  websearch: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'query', label: 'Query', type: 'textarea', help: HELP.query },
    { key: 'maxResults', label: 'Max Results', type: 'number', help: HELP.maxResults }
  ],
  webfetch: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'url', label: 'URL', type: 'text', help: HELP.url },
    { key: 'maxChars', label: 'Max Chars', type: 'number', help: HELP.maxChars }
  ],
  readfile: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'path', label: 'File Path', type: 'text', help: HELP.filePath },
    { key: 'maxChars', label: 'Max Chars', type: 'number', help: HELP.maxChars }
  ],
  writefile: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'path', label: 'File Path', type: 'text', help: HELP.filePath },
    { key: 'mode', label: 'Mode', type: 'select', options: ['append', 'overwrite'], help: HELP.writeMode },
    { key: 'content', label: 'Content', type: 'textarea', help: HELP.content }
  ],
  delay: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'seconds', label: 'Seconds', type: 'number', help: HELP.seconds }
  ],
  schedule: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'runAt', label: 'Run At (ISO)', type: 'text', placeholder: '2026-01-15T14:00 | tomorrow 09:00 | thu this week 14:00', help: HELP.runAt },
    { key: 'delaySeconds', label: 'Delay Seconds', type: 'number', help: HELP.delaySeconds },
    { key: 'recurrence', label: 'Recurrence', type: 'text', placeholder: 'every 2 weeks | daily at 09:00 | weekly on mon,thu at 14:00', help: HELP.recurrence },
    { key: 'scheduleList', label: 'Schedule List (optional)', type: 'textarea', placeholder: '2026-01-01T09:00\n2026-01-15T09:00\nthu this week 09:00\nfri next week 09:00', help: HELP.scheduleList },
    { key: 'scheduleMode', label: 'Schedule Mode', type: 'select', options: ['once', 'cycle'], help: HELP.scheduleMode }
  ],
  branch: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title }
  ],
  parallel: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title }
  ],
  loop: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'count', label: 'Count (0 = infinite)', type: 'number', help: HELP.count },
    { key: 'delaySeconds', label: 'Delay Seconds', type: 'number', help: HELP.delaySeconds }
  ],
  context: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'action', label: 'Action', type: 'select', options: ['clear', 'set', 'append'], help: HELP.action },
    { key: 'role', label: 'Role', type: 'select', options: ['system', 'user', 'assistant'], help: HELP.role },
    { key: 'message', label: 'Message', type: 'textarea', placeholder: '{{last_output}}', help: HELP.message },
    { key: 'contextKey', label: 'Context Key', type: 'text', placeholder: 'default', help: HELP.contextKey },
    { key: 'contextScope', label: 'Context Scope', type: 'select', options: ['workflow', 'global', 'custom'], help: HELP.contextScope }
  ],
  setvar: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'key', label: 'Variable Name', type: 'text', placeholder: 'job_list', help: HELP.variableName },
    { key: 'mode', label: 'Mode', type: 'select', options: ['set', 'append'], help: HELP.variableMode },
    { key: 'value', label: 'Value', type: 'textarea', placeholder: '{{last_output}}', help: HELP.variableValue }
  ],
  email_reply: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'mailbox', label: 'Mailbox', type: 'text', placeholder: 'INBOX', help: HELP.mailbox },
    { key: 'limit', label: 'Limit', type: 'number', help: HELP.limit },
    { key: 'dryRun', label: 'Dry Run', type: 'select', options: ['true', 'false'], help: HELP.dryRun },
    { key: 'rules', label: 'Rules', type: 'rules', help: HELP.rules }
  ],
  log: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'path', label: 'Log Path', type: 'text', placeholder: 'automation_data/logs/run.log', help: HELP.logPath },
    { key: 'message', label: 'Message', type: 'textarea', help: HELP.logMessage }
  ],
  python_script: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'scriptPath', label: 'Script Path', type: 'text', placeholder: 'my_script.py', help: HELP.scriptPath },
    { key: 'functionName', label: 'Function Name', type: 'text', placeholder: 'process_image', help: HELP.functionName },
    { key: 'inputVar', label: 'Input Variable', type: 'text', placeholder: 'image_path', help: HELP.inputVar },
    { key: 'inputParam', label: 'Input Param Name', type: 'text', placeholder: 'image', help: HELP.inputParam },
    { key: 'outputVar', label: 'Output Variable', type: 'text', placeholder: 'processed_image', help: HELP.outputVar },
    { key: 'params', label: 'Params (JSON)', type: 'json', placeholder: '{\"threshold\": 120}', help: HELP.paramsJson },
    { key: 'scriptParams', label: 'Script Parameters', type: 'script_params', help: HELP.scriptParams }
  ],
  agent: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'by', label: 'Agent', type: 'select', options: ['claude:haiku', 'claude:sonnet', 'claude:opus', 'codex', 'agy', 'mistral', 'ollama:qwen3:4b-instruct', 'ollama:llama3.2:1b', 'gemini:flash', 'chatgpt'], help: h('Which agent answers.', 'Agent CLIs and Ollama run on a worker node; gemini/chatgpt use the browser.', 'Same prompt, any agent.') },
    { key: 'effort', label: 'Effort', type: 'select', options: ['medium', 'low', 'high', 'max', 'ultra'], help: h('How hard to think.', 'high = 3 votes, max = 5, ultra = 5 plus a round where they see each other.', 'More effort, more agreement, more time.') },
    { key: 'prompt', label: 'Prompt', type: 'textarea', help: HELP.prompt }
  ],
  council: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'template', label: 'Council', type: 'select', options: ['panel', 'debate', 'chain', 'layers'], help: h('Which council template the host offers.', 'panel: answer and vote; debate: argue to a majority; chain: second and third opinions; layers: mixture of agents.', 'Different procedures for different questions.') },
    { key: 'prompt', label: 'Question', type: 'textarea', help: HELP.prompt }
  ],
  triad: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'task', label: 'Task', type: 'textarea', help: h('The coding task for the three-agent pipeline.', 'Write it as you would for any coding agent; {{last_output}} works.', 'The pipeline plans, implements and reviews it.') },
    { key: 'cwd', label: 'Folder (optional)', type: 'text', placeholder: '~/project', help: h('Where the pipeline works.', 'Leave empty for your home folder.', 'Keeps the change in the right repository.') }
  ],
  symblic: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'by', label: 'Default agent', type: 'select', options: ['claude:haiku', 'claude:sonnet', 'codex', 'agy', 'mistral', 'ollama:qwen3:4b-instruct', 'ollama:llama3.2:1b'], help: h('Who applies asks that do not name an agent.', 'A program can override it per statement with by=.', 'Formal statements never need one.') },
    { key: 'source', label: 'Program', type: 'textarea', placeholder: 'given last_output: Text.\nask summary: Text up to 60 words "Summarize {last_output}."\nshow summary.', help: h('A Symblic program.', 'Write it here or in /automation-studio/symblic.html and paste it.', 'Typed, checked, fingerprinted steps.') }
  ],
  shell: [
    { key: 'title', label: 'Title', type: 'text', target: 'title', help: HELP.title },
    { key: 'command', label: 'Command', type: 'textarea', help: HELP.shellCommand },
    { key: 'workdir', label: 'Workdir (optional)', type: 'text', help: HELP.shellWorkdir },
    { key: 'timeoutSeconds', label: 'Timeout Seconds', type: 'number', help: HELP.shellTimeout },
    { key: 'maxChars', label: 'Max Chars', type: 'number', help: HELP.shellMaxChars }
  ]
};
