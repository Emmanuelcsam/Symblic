"""Forge question catalogue: which questions to ask about a project, by domain and engineering dimension.

What it is for
    Templates and idea classification decide which questions the Forge offers; they never decide answers. This
    module holds the fixed vocabulary (lifecycles, modes, roles, dimensions such as INTERFACE, DATA, SECURITY,
    CLUSTER or ACCESSIBILITY), the creative ideation lenses, the per-domain question sets (web, game, agent,
    distributed systems, scientific work, hardware, research, ...), the trade-off notes shown next to suggested
    answers, and the functions classify(idea, template), questions_for(idea, domains, ...),
    active_dimensions(domains) and catalog(). Domain classification is routing metadata only: the operator
    decides relevance and every accepted answer.

Depends on: the standard library only; no model, inventory, persistence or execution. Used by:
symblic.forge.core, .coach and .models. Status: prototype data and functions; tested through tests/forge.
"""
from __future__ import annotations

from copy import deepcopy

SCHEMA = 'symblic-forge/1'
LIFECYCLES = ('IDEA', 'EXPLORING', 'DEFINING', 'ARCHITECTING', 'PLANNING', 'READY',
              'EXPORTED', 'EXECUTION_TRANSFERRED')
MODES = ('DEEP', 'RAPID', 'EXPLORE', 'PRECISION', 'CHALLENGE')
ROLES = ('IDEATOR', 'QUESTIONER', 'CRITIC', 'SPECIFIER')
IDEATION_LENSES = [
    {'id': 'smallest_useful', 'title': 'Smallest useful result',
     'prompt': 'What is the smallest complete outcome that helps the intended user?',
     'alternatives': [{'text': 'One complete workflow first', 'tradeoffs': ['Earlier observable value', 'Other workflows wait']},
                      {'text': 'A reusable foundation first', 'tradeoffs': ['Supports several later workflows', 'Delays the first usable result']}],
     'edge_cases': ['The first-time user has no existing data.', 'The main dependency is unavailable.']},
    {'id': 'user_journey', 'title': 'Walk through the experience',
     'prompt': 'Describe the entry action, visible result and next action for one concrete user journey.',
     'alternatives': [{'text': 'A guided sequence', 'tradeoffs': ['Discoverable steps', 'More interactions']},
                      {'text': 'A direct command', 'tradeoffs': ['Fast repeated use', 'Needs clear errors and examples']}],
     'edge_cases': ['The user repeats the action.', 'The user leaves and returns before completion.']},
    {'id': 'representation', 'title': 'Compare representations',
     'prompt': 'Which data representation makes the required behavior and checks easiest to express?',
     'alternatives': [{'text': 'Explicit typed records', 'tradeoffs': ['Checkable contracts', 'Schema evolution needs care']},
                      {'text': 'Free text with explicit boundaries', 'tradeoffs': ['Flexible input', 'Needs validation before execution']}],
     'edge_cases': ['An input is empty or malformed.', 'A value contains quotes, Unicode or an exact path.']},
    {'id': 'boundaries', 'title': 'Separate responsibilities',
     'prompt': 'Which one responsibility can be implemented using only named inputs and producing one bounded result?',
     'alternatives': [{'text': 'Pure transformation plus separate effects', 'tradeoffs': ['Reproducible checks', 'More explicit interfaces']},
                      {'text': 'One small integrated component', 'tradeoffs': ['Less coordination', 'Effects and logic are harder to test separately']}],
     'edge_cases': ['Two components disagree about units or schema.', 'A dependency changes during a request.']},
    {'id': 'failure_recovery', 'title': 'Design recovery',
     'prompt': 'What should remain durable when the operation stops between two observable steps?',
     'alternatives': [{'text': 'Resume an identified operation', 'tradeoffs': ['Preserves completed work', 'Needs durable checkpoints']},
                      {'text': 'Restart an explicitly idempotent operation', 'tradeoffs': ['Simpler recovery', 'Needs proof repeats are safe']}],
     'edge_cases': ['The reply is lost after work completed.', 'Power is lost while saving.']},
    {'id': 'resource_fit', 'title': 'Fit the available resources',
     'prompt': 'Which measured time, memory, storage or context limit constrains the design?',
     'alternatives': [{'text': 'Sequential bounded tasks', 'tradeoffs': ['Lower peak resource use', 'Longer total latency']},
                      {'text': 'Independent admitted parallel tasks', 'tradeoffs': ['Potential lower latency', 'Needs spare capacity and result reconciliation']}],
     'edge_cases': ['The chosen node is offline.', 'The input exceeds the stated context or memory budget.']},
    {'id': 'verification', 'title': 'Make success observable',
     'prompt': 'Which input and expected observation would distinguish success from a plausible-looking result?',
     'alternatives': [{'text': 'Deterministic example with exact expected output', 'tradeoffs': ['Repeatable evidence', 'Limited case coverage']},
                      {'text': 'An invariant over several cases', 'tradeoffs': ['Broader coverage', 'Requires a precise invariant']}],
     'edge_cases': ['A result looks right but violates an invariant.', 'A test passes without exercising the requested behavior.']},
    {'id': 'alternatives', 'title': 'Explore a different approach',
     'prompt': 'Propose distinct ways to achieve the accepted objective; compare cost, complexity and limitations without choosing for the operator.',
     'alternatives': [{'text': 'Adapt an existing component', 'tradeoffs': ['Less new code', 'Compatibility and dependency constraints']},
                      {'text': 'Build a narrow custom component', 'tradeoffs': ['Direct control', 'More implementation and maintenance work']}],
     'edge_cases': ['The preferred dependency changes its interface.', 'An optional feature becomes a hidden requirement.']},
]
PROVENANCE = ('USER_ORIGINAL', 'USER_ANSWER', 'MODEL_QUESTION', 'MODEL_SUGGESTION',
              'USER_ACCEPTED_SUGGESTION', 'USER_EDITED_SUGGESTION', 'SYSTEM_DERIVED',
              'IMPORTED', 'COMPILER_DERIVED')
SEVERITIES = ('BLOCKING', 'HIGH', 'MEDIUM', 'LOW', 'OPTIONAL')
STATUSES = ('proposed', 'accepted', 'rejected', 'removed')
QUESTION_STATUSES = ('open', 'active', 'deferred', 'answered', 'dismissed', 'needs_research')
DIMENSIONS = {
    'PURPOSE': 'What the project must accomplish', 'USER': 'Who or what uses it',
    'INPUTS': 'Incoming information or physical signals', 'OUTPUTS': 'Resulting information or effects',
    'INTERFACE': 'How users and systems interact', 'BEHAVIOR': 'Required behavior',
    'STATE': 'Persistent and transient state', 'DATA': 'Represented information',
    'COMPONENTS': 'Major system responsibilities', 'DEPENDENCIES': 'Required external systems',
    'PLATFORM': 'Execution environment', 'HARDWARE': 'Physical hardware', 'MODELS': 'AI models',
    'AGENTS': 'Autonomous actors', 'CLUSTER': 'Distributed computing', 'NETWORK': 'Communications',
    'STORAGE': 'Persistent data location', 'SECURITY': 'Trust and permission boundaries',
    'PRIVACY': 'Private information handling', 'SAFETY': 'Prevention and containment',
    'PERFORMANCE': 'Measured resource and timing targets', 'RELIABILITY': 'Behavior under faults',
    'RECOVERY': 'Restoring operation', 'OBSERVABILITY': 'Logs, metrics and receipts',
    'TESTING': 'Verification of requirements', 'DEPLOYMENT': 'Installation and operation',
    'UPDATE': 'Modification and migration', 'ACCESSIBILITY': 'Usability requirements',
    'VISUAL_DESIGN': 'Appearance', 'AUDIO_DESIGN': 'Sound', 'CONTROLS': 'Operator input',
    'FAILURE_BEHAVIOR': 'Response to errors', 'ACCEPTANCE': 'Observable completion conditions',
}
DOMAIN_DIMENSIONS = {
    'game': ('GAME_RULES', 'WORLD_GEOMETRY', 'PLAYER_CONTROLS', 'SCORING', 'START_STATE',
             'END_STATE', 'COLLISIONS', 'DIFFICULTY', 'FRAME_TIMING', 'RENDERING'),
    'ai': ('MODEL_SELECTION', 'CONTEXT_POLICY', 'OUTPUT_CONTRACT', 'VALIDATION_POLICY', 'FALLBACK_POLICY'),
    'agent': ('AGENT_ROLES', 'AGENT_PERMISSIONS', 'AGENT_MEMORY', 'AGENT_COORDINATION'),
    'cluster': ('NODE_SELECTION', 'JOB_DISTRIBUTION', 'RESOURCE_LIMITS', 'FAILURE_REASSIGNMENT'),
    'web': ('VIEWPORT', 'DOM_STRUCTURE', 'BROWSER_SUPPORT', 'CLIENT_SERVER_BOUNDARY'),
    'hardware': ('POWER', 'PHYSICAL_DIMENSIONS', 'CONNECTORS', 'ENVIRONMENT', 'MATERIALS'),
    'scientific': ('UNITS', 'ASSUMPTIONS', 'UNCERTAINTY', 'VALIDATION_DATA'),
}
for _dimensions in DOMAIN_DIMENSIONS.values():
    for _dimension in _dimensions:
        DIMENSIONS[_dimension] = _dimension.replace('_', ' ').capitalize()
DOMAINS = ('web', 'desktop', 'game', 'operating_system', 'cli', 'ai', 'agent', 'cluster',
           'embedded', 'electronics', 'robotics', 'scientific', 'data_pipeline', 'research',
           'hardware', 'mechanical', 'mixed', 'UNKNOWN')
TEMPLATES = {'web': ['web'], 'game': ['game'], 'ai_agent': ['ai', 'agent'],
             'cluster': ['cluster'], 'operating_system': ['operating_system'],
             'scientific': ['scientific'], 'hardware': ['hardware'], 'research': ['research']}
ENTITY_SCHEMAS = {
    'objectives': {'required': [], 'fields': ['measure', 'parent_objective_id']},
    'criteria': {'required': ['requirement_ids', 'observable', 'measurement', 'expected'],
                 'fields': ['requirement_ids', 'observable', 'measurement', 'expected', 'subjective']},
    'architectures': {'required': ['requirement_ids', 'components', 'tradeoffs'],
                      'fields': ['requirement_ids', 'components', 'tradeoffs', 'unresolved']},
    'components': {'required': ['responsibility', 'inputs', 'outputs'],
                    'fields': ['requirement_ids', 'responsibility', 'inputs', 'outputs', 'dependencies', 'persistent_state', 'effects']},
    'units': {'required': ['component_id', 'objective', 'inputs', 'outputs', 'dependencies', 'checks'],
              'fields': ['component_id', 'requirement_ids', 'objective', 'inputs', 'outputs', 'dependencies', 'checks',
                         'forbidden_assumptions', 'defines', 'requires', 'paths']},
    'agents': {'required': ['responsibility', 'inputs', 'outputs', 'permissions', 'dependencies', 'verification'],
               'fields': ['requirement_ids', 'responsibility', 'inputs', 'outputs', 'permissions', 'dependencies', 'verification']},
    'models': {'required': ['app'], 'fields': ['app', 'policy', 'requirement_ids', 'output_schema']},
    'cluster': {'required': ['capabilities'], 'fields': ['requirement_ids', 'capabilities', 'model_placement',
                 'task_placement', 'concurrency', 'memory', 'storage', 'memory_bytes', 'storage_bytes', 'node_id',
                 'synchronization', 'failure_reassignment']},
    'evidence': {'required': ['evidence_type'], 'fields': ['evidence_type', 'requirement_ids', 'uri', 'file_id',
                  'file_artifact_id', 'filename', 'sha256', 'media_type', 'size', 'url', 'measurement', 'result',
                  'inventory', 'captured_at', 'repair']},
    'invariants': {'required': ['requirement_ids'], 'fields': ['requirement_ids', 'unit_ids', 'criterion_ids']},
    'forbidden': {'required': ['requirement_ids'], 'fields': ['requirement_ids', 'negative_check']},
    'dependencies': {'required': ['source', 'target', 'kind'], 'fields': ['source', 'target', 'kind']},
}

# Each row is key, dimension, one independent question, concrete alternatives.
# Alternatives are displayed as proposals only. No value is selected by default.
GROUPS = {
 'universal': [
  ('purpose', 'PURPOSE', 'What observable result must this project achieve?', []),
  ('user', 'USER', 'Who or what will use this project?', []),
  ('inputs', 'INPUTS', 'What information or physical signals enter the system?', []),
  ('outputs', 'OUTPUTS', 'What information or physical effects must the system produce?', []),
  ('interface', 'INTERFACE', 'How should the intended user interact with the system?', []),
  ('behavior', 'BEHAVIOR', 'What is the principal behavior the system must perform?', []),
  ('state', 'STATE', 'Which state must persist between sessions?', ['No state persists', 'Persist explicitly named state']),
  ('data', 'DATA', 'Which data types and schemas are required?', []),
  ('components', 'COMPONENTS', 'Which responsibilities must be separate components?', []),
  ('dependencies', 'DEPENDENCIES', 'Which external software, hardware or services are required?', []),
  ('platform', 'PLATFORM', 'Where must the project run?', ['Web browser', 'Desktop application', 'Command-line application', 'Embedded device']),
  ('hardware', 'HARDWARE', 'Does the project require specific physical hardware?', ['No specific hardware is required', 'Specify required hardware']),
  ('models', 'MODELS', 'Is model-driven construction or AI behavior required?', ['No AI model is required', 'AI is optional', 'AI is required']),
  ('agents', 'AGENTS', 'Should autonomous agents build or operate this project?', ['No autonomous agents', 'One bounded implementation agent', 'Several explicitly bounded agents']),
  ('cluster', 'CLUSTER', 'Should construction use one machine or distributed machines?', ['One machine', 'Distributed independent implementation and verification']),
  ('network', 'NETWORK', 'Must components communicate across processes or machines?', ['No networking', 'Local process communication', 'Communication between machines']),
  ('storage', 'STORAGE', 'Where should persistent project data be stored?', []),
  ('security', 'SECURITY', 'Which actions require explicit operator authority?', []),
  ('privacy', 'PRIVACY', 'Which information is private and where may it be sent?', []),
  ('safety', 'SAFETY', 'Which unsafe conditions must be prevented or contained?', []),
  ('performance', 'PERFORMANCE', 'Does an operation have a required measurable performance target?', ['No fixed performance target', 'Specify a measured target']),
  ('reliability', 'RELIABILITY', 'What behavior is required when a major dependency is unavailable?', []),
  ('recovery', 'RECOVERY', 'How should the project recover from an interrupted operation?', []),
  ('observability', 'OBSERVABILITY', 'Which logs, measurements or receipts must be retained?', []),
  ('testing', 'TESTING', 'Which observable checks must verify the required behavior?', []),
  ('deployment', 'DEPLOYMENT', 'How should the completed project be installed and started?', []),
  ('update', 'UPDATE', 'How should future changes and schema migrations preserve existing state?', []),
  ('accessibility', 'ACCESSIBILITY', 'Which accessibility requirements must the interface satisfy?', []),
  ('visual', 'VISUAL_DESIGN', 'Does the project need a visual interface?', ['No visual interface', 'A visual interface is required']),
  ('audio', 'AUDIO_DESIGN', 'Does the project require sound?', ['No sound', 'Sound is required']),
  ('controls', 'CONTROLS', 'Which operator input mechanisms must be supported?', []),
  ('failure', 'FAILURE_BEHAVIOR', 'What must the user observe when an operation fails?', []),
  ('acceptance', 'ACCEPTANCE', 'Which observable condition means the requested outcome is complete?', []),
 ],
 'visual': [
  ('rendering', 'RENDERING', 'Which technology should render the interface?', ['HTML canvas 2D', 'DOM elements', 'WebGL', 'Native UI']),
  ('viewport.width', 'VIEWPORT', 'What is the viewport width in pixels?', ['800 pixels', '640 pixels']),
  ('viewport.height', 'VIEWPORT', 'What is the viewport height in pixels?', []),
  ('background', 'VISUAL_DESIGN', 'What background appearance is required?', []),
  ('foreground', 'VISUAL_DESIGN', 'What foreground appearance is required?', []),
  ('typography', 'VISUAL_DESIGN', 'What typography is required?', []),
  ('layout', 'VISUAL_DESIGN', 'Which major layout regions are required?', []),
  ('responsive', 'VIEWPORT', 'How should the interface adapt to a narrow viewport?', []),
  ('animation', 'VISUAL_DESIGN', 'Which visual elements should animate?', ['No animation', 'Specify animated elements']),
  ('render.frame_rate', 'FRAME_TIMING', 'If continuous animation is required, what rendering frame rate is needed?', []),
  ('loading', 'VISUAL_DESIGN', 'What should be displayed while required content loads?', []),
  ('failure.screen', 'FAILURE_BEHAVIOR', 'What should be displayed after a loading or operation failure?', []),
 ],
 'game': [
  ('game.world', 'WORLD_GEOMETRY', 'What is the game world and its geometry?', ['A rectangular cell grid', 'A continuous two-dimensional world']),
  ('game.start', 'START_STATE', 'Should the game start immediately or show a start screen?', ['Start immediately', 'Show a minimal start screen']),
  ('game.start_control', 'START_STATE', 'Which explicit action begins play from the start screen?', ['Enter', 'Space', 'Pointer click']),
  ('game.player', 'PLAYER_CONTROLS', 'What can the player control?', []),
  ('game.actions', 'GAME_RULES', 'Which player actions are available?', []),
  ('game.keys', 'PLAYER_CONTROLS', 'Which controls move the player or snake?', ['Arrow keys', 'WASD', 'Arrow keys and WASD']),
  ('game.pointer', 'PLAYER_CONTROLS', 'Should pointer controls be supported?', ['No pointer controls', 'Pointer controls']),
  ('game.touch', 'PLAYER_CONTROLS', 'Should touch controls be supported?', ['No touch controls', 'Touch controls']),
  ('game.initial', 'START_STATE', 'What is the exact initial position, direction and size?', []),
  ('game.movement', 'GAME_RULES', 'How does movement occur?', ['One cell per fixed simulation interval', 'Continuous movement']),
  ('game.interval', 'FRAME_TIMING', 'What simulation interval or movement rate is required?', []),
  ('game.food', 'GAME_RULES', 'How does food appear and which locations are permitted?', []),
  ('game.growth', 'GAME_RULES', 'How does collecting food change the snake?', []),
  ('game.score', 'SCORING', 'Which events change the score and by how much?', []),
  ('game.wall', 'COLLISIONS', 'What happens at the game boundary?', ['Game over on boundary collision', 'Wrap to the opposite boundary']),
  ('game.body', 'COLLISIONS', 'Does collision with the snake body end the game?', ['Body collision ends the game', 'Body collision does not end the game']),
  ('game.end', 'END_STATE', 'Which conditions end the game and what is displayed?', []),
  ('game.restart', 'START_STATE', 'Which state must reset when the game restarts?', []),
  ('game.persistence', 'STATE', 'Which game state, if any, persists after closing it?', ['No game state persists', 'Persist explicitly named state']),
  ('game.pause', 'GAME_RULES', 'Is pause behavior required?', ['No pause', 'Pause and resume']),
  ('game.difficulty', 'DIFFICULTY', 'Should difficulty change during play?', ['Fixed difficulty', 'Explicit changing difficulty']),
  ('game.random', 'GAME_RULES', 'Is randomness permitted?', ['No randomness', 'Randomness is permitted']),
  ('game.seed', 'GAME_RULES', 'Must random behavior have a reproducible seed?', ['A reproducible seed is required', 'No fixed reproducibility requirement']),
 ],
 'ai': [
  ('ai.required', 'MODEL_SELECTION', 'Is AI required or optional?', ['Required', 'Optional']),
  ('ai.local', 'MODEL_SELECTION', 'Must all models run locally?', ['Local models only', 'Approved remote models permitted']),
  ('ai.cloud', 'PRIVACY', 'May project information be sent to cloud models?', ['No cloud models', 'Only explicitly approved cloud models and data']),
  ('ai.model', 'MODEL_SELECTION', 'Is an exact model name required?', []),
  ('ai.diversity', 'MODEL_SELECTION', 'Is model-family diversity required?', ['No diversity requirement', 'Specify distinct model families']),
  ('ai.kernel', 'VALIDATION_POLICY', 'Which deterministic operations should bypass models?', []),
  ('ai.fallback', 'FALLBACK_POLICY', 'Is fallback to another model permitted?', ['No automatic fallback', 'Only an explicit ordered fallback list']),
  ('ai.failure', 'FALLBACK_POLICY', 'What happens when every allowed model fails?', []),
  ('ai.schema', 'OUTPUT_CONTRACT', 'What output schema must each model satisfy?', []),
  ('ai.context', 'CONTEXT_POLICY', 'Which project data may enter each model request?', []),
  ('ai.validate', 'VALIDATION_POLICY', 'How must model outputs be independently validated?', []),
  ('ai.identity', 'MODEL_SELECTION', 'Must model identity and digest be recorded?', ['Record model identity and digest', 'Specify the required identity evidence']),
 ],
 'agent': [
  ('agent.roles', 'AGENT_ROLES', 'What bounded responsibility does each agent have?', ['One implementation agent', 'Separate game-logic, rendering and verification agents']),
  ('agent.read', 'AGENT_PERMISSIONS', 'What may each agent read?', []),
  ('agent.write', 'AGENT_PERMISSIONS', 'What may each agent write?', []),
  ('agent.execute', 'AGENT_PERMISSIONS', 'What may each agent execute?', []),
  ('agent.context', 'AGENT_MEMORY', 'Do agents share conversational context?', ['Only explicit dependencies', 'Explicitly scoped shared context']),
  ('agent.children', 'AGENT_COORDINATION', 'May agents create child agents?', ['No child agents', 'Explicitly bounded child agents']),
  ('agent.communication', 'AGENT_COORDINATION', 'May agents communicate directly?', ['Only through the coordinator', 'Explicit direct channels']),
  ('agent.acceptance', 'AGENT_COORDINATION', 'How are agent outputs accepted?', []),
  ('agent.failure', 'FAILURE_BEHAVIOR', 'What happens when an agent fails?', []),
  ('agent.disagreement', 'AGENT_COORDINATION', 'What happens when agents disagree?', []),
  ('agent.reviewer', 'AGENT_ROLES', 'Is an independent reviewer agent required?', ['Reviewer required', 'No reviewer requirement']),
  ('agent.validator', 'VALIDATION_POLICY', 'Which deterministic validator has final authority?', []),
 ],
 'cluster': [
  ('cluster.nodes', 'NODE_SELECTION', 'Are specific physical nodes required?', ['Interchangeable capable nodes', 'Explicitly selected physical nodes']),
  ('cluster.concurrent', 'JOB_DISTRIBUTION', 'Which jobs may run concurrently?', []),
  ('cluster.memory', 'RESOURCE_LIMITS', 'What memory does each job require, including units?', []),
  ('cluster.cpu', 'RESOURCE_LIMITS', 'What processor capacity does each job require?', []),
  ('cluster.accelerator', 'RESOURCE_LIMITS', 'Does a job require a specific accelerator?', []),
  ('cluster.selection', 'NODE_SELECTION', 'How are capable nodes selected?', []),
  ('cluster.unavailable', 'FAILURE_REASSIGNMENT', 'What happens when a selected node is unavailable?', []),
  ('cluster.reassign', 'FAILURE_REASSIGNMENT', 'May failed work move to another node?', ['No reassignment', 'Explicitly authorized reassignment']),
  ('cluster.models', 'NODE_SELECTION', 'Must a model remain on a specific node?', []),
  ('cluster.sync', 'STORAGE', 'How are project artifacts synchronized?', []),
  ('cluster.coordinator', 'JOB_DISTRIBUTION', 'Is there a central coordinator?', []),
  ('cluster.revision', 'DEPLOYMENT', 'Must nodes use the same software revision?', ['Identical pinned revision', 'Explicit compatibility contract']),
 ],
 'hardware': [
  ('hardware.function', 'HARDWARE', 'What exact physical function is required?', []),
  ('hardware.physical', 'CONNECTORS', 'Which physical interfaces are required?', []),
  ('hardware.electrical', 'CONNECTORS', 'Which electrical interfaces and compatibility evidence are required?', []),
  ('hardware.power', 'POWER', 'What power is required, with units?', []),
  ('hardware.voltage', 'POWER', 'What voltage is required, with units?', []),
  ('hardware.current', 'POWER', 'What current is required, if relevant?', []),
  ('hardware.protocol', 'NETWORK', 'Which hardware communication protocols are required?', []),
  ('hardware.dimensions', 'PHYSICAL_DIMENSIONS', 'What physical dimensions are required, with units?', []),
  ('hardware.environment', 'ENVIRONMENT', 'Which environmental conditions must be supported?', []),
  ('hardware.tolerance', 'PHYSICAL_DIMENSIONS', 'Which quantities require explicit tolerance?', []),
  ('hardware.fail_safe', 'SAFETY', 'What fail-safe behavior is required?', []),
  ('hardware.verify', 'TESTING', 'How will physical hardware state be measured?', []),
 ],
 'data': [
  ('data.input', 'DATA', 'Which data enters the system?', []), ('data.output', 'DATA', 'Which data leaves it?', []),
  ('data.persist', 'STATE', 'Which data must persist?', []), ('data.transient', 'STATE', 'Which data may remain transient?', []),
  ('data.types', 'DATA', 'What exact data types are required?', []), ('data.serialization', 'DATA', 'What serialization format is required?', []),
  ('data.index', 'STORAGE', 'Which indexes are required?', []), ('data.volume', 'STORAGE', 'What data volume must be supported?', []),
  ('data.retention', 'PRIVACY', 'How long must the data be retained?', []), ('data.backup', 'RECOVERY', 'What backup policy is required?', []),
  ('data.deletion', 'PRIVACY', 'What deletion policy is required?', []), ('data.migration', 'UPDATE', 'How will schema migration be handled?', []),
 ],
 'network': [
  ('network.sender', 'NETWORK', 'Which component initiates communication?', []),
  ('network.receiver', 'NETWORK', 'Which component receives communication?', []),
  ('network.protocol', 'NETWORK', 'Which communication protocol is required?', []),
  ('network.scope', 'NETWORK', 'What is the intended network scope?', ['Local only', 'Explicit remote endpoints']),
  ('network.auth', 'SECURITY', 'What authentication is required?', []),
  ('network.encryption', 'SECURITY', 'What encryption is required?', []),
  ('network.reconnect', 'RECOVERY', 'What reconnect behavior is required?', []),
  ('network.timeout', 'FAILURE_BEHAVIOR', 'What timeout behavior is required?', []),
  ('network.retry', 'FAILURE_BEHAVIOR', 'What retry behavior is permitted?', []),
  ('network.duplicate', 'RELIABILITY', 'How must duplicate requests be handled?', []),
 ],
 'security': [
  ('security.effects', 'SECURITY', 'Which operations create external side effects?', []),
  ('security.privilege', 'SECURITY', 'Which privileged operations are necessary?', []),
  ('security.inputs', 'SECURITY', 'Which untrusted, model-generated or network inputs are accepted?', []),
  ('security.paths', 'SECURITY', 'Which exact paths may be written or executed?', []),
  ('security.credentials', 'PRIVACY', 'Which component may possess credentials?', []),
  ('security.network', 'SECURITY', 'Which components may access the network?', []),
  ('security.sandbox', 'SECURITY', 'Which operations require sandboxing?', []),
  ('security.receipts', 'OBSERVABILITY', 'Which operations require execution receipts?', []),
 ],
 'scientific': [
  ('science.units', 'UNITS', 'Which physical quantities and units are used?', []),
  ('science.assumptions', 'ASSUMPTIONS', 'Which assumptions and validity limits apply to the model?', []),
  ('science.uncertainty', 'UNCERTAINTY', 'Which uncertainties and tolerances must be reported?', []),
  ('science.validation', 'VALIDATION_DATA', 'Which independent reference data will validate the result?', []),
 ],
}

MANDATORY = frozenset({'purpose', 'behavior', 'platform', 'acceptance'})
SNAKE_MANDATORY = frozenset({'rendering', 'viewport.width', 'viewport.height', 'game.world', 'game.start',
    'game.initial', 'game.keys', 'game.movement', 'game.interval', 'game.food', 'game.growth', 'game.score',
    'game.wall', 'game.body', 'game.end', 'game.restart', 'agents', 'cluster'})
DEPENDENCIES = {'viewport.width': ['rendering'], 'viewport.height': ['viewport.width'],
    'game.interval': ['game.movement'], 'game.start_control': ['game.start'], 'game.seed': ['game.random']}

# External engineering rationale, never a hidden chain of thought or accepted rule.
# Entries correspond to the explicit alternatives above and avoid choosing a winner.
TRADEOFFS = {
 'state': ['Avoids retention and migration work; state is lost after a session.', 'Supports continuity; requires named retention, recovery and migration rules.'],
 'platform': ['Distribution is through a browser; browser permissions and compatibility constrain integration.', 'Can integrate with desktop facilities; packaging and updates need an operating-system contract.', 'Supports scripts and automation; visual interaction requires a separate interface.', 'Can work near physical inputs; resource, power and hardware verification become explicit constraints.'],
 'hardware': ['Keeps deployment portable; hardware-specific capabilities cannot be assumed.', 'Allows named device capabilities; acquisition and compatibility become dependencies.'],
 'models': ['Avoids inference dependencies; required behavior must have a deterministic implementation.', 'Allows a deterministic operating path; the optional AI path still needs validation.', 'Makes inference central to the design; availability, output contracts and failure behavior must be defined.'],
 'agents': ['Keeps control with explicit deterministic steps; automation must be specified separately.', 'Keeps one bounded responsibility; independent review must be provided separately if required.', 'Separates responsibilities; coordination, ownership and handoff checks must be explicit.'],
 'cluster': ['Avoids artifact synchronization across machines; capacity is limited to the selected machine.', 'Can separate independent work; revisions, artifact transport and resource admission need explicit checks.'],
 'network': ['Avoids network dependencies; remote services cannot be required.', 'Supports local component separation; process boundaries and failure behavior still need contracts.', 'Supports remote components; authentication, retries, duplicates and connectivity become design concerns.'],
 'performance': ['Avoids inventing a numerical target; acceptance cannot claim a particular latency or throughput.', 'Makes performance testable; measurement conditions and units must be supplied.'],
 'visual': ['Supports nonvisual interaction; discoverability must come from the selected interface.', 'Supports visual interaction; layout, rendering, accessibility and failure screens need decisions.'],
 'audio': ['Avoids audio assets and output requirements; audible feedback cannot be assumed.', 'Adds audible feedback; volume, mute, timing and nonaudio alternatives need decisions.'],
 'rendering': ['Offers explicit pixel drawing; hit testing and accessible semantic controls need separate design.', 'Uses document elements and layout; many moving visual elements need deliberate state and rendering choices.', 'Supports programmable graphics; shader, resource and compatibility behavior adds design work.', 'Integrates with a chosen platform toolkit; cross-platform portability depends on that toolkit.'],
 'viewport.width': ['Provides more horizontal drawing area at the same height; narrow-screen adaptation needs a rule.', 'Uses less horizontal drawing area at the same height; visible detail and cell size need review.'],
 'animation': ['Avoids continuous visual updates; movement feedback must use another chosen mechanism.', 'Can communicate changes visually; timing and reduced-motion behavior need rules.'],
 'game.world': ['Gives discrete cell coordinates and collisions; movement is constrained to the grid.', 'Allows arbitrary positions; numerical precision, collision geometry and timing need explicit choices.'],
 'game.start': ['Begins play with fewer actions; the player has no separate preparation phase.', 'Allows preparation and control discovery; start transitions and activation controls must be specified.'],
 'game.start_control': ['Supports keyboard activation; touch-only devices need another path if supported.', 'Supports keyboard activation; scrolling and focused-control behavior need handling.', 'Supports pointer activation; keyboard-only users need another path if supported.'],
 'game.keys': ['Uses directional keyboard labels; alternate layouts and nonkeyboard input remain separate decisions.', 'Uses a compact key cluster; key naming and keyboard-layout assumptions need review.', 'Supports both chosen mappings; simultaneous inputs and duplicate actions need one arbitration rule.'],
 'game.pointer': ['Reduces input paths to verify; pointer-only play is unavailable.', 'Enables pointer input; targeting, focus and interaction geometry need checks.'],
 'game.touch': ['Reduces gesture and target handling; touch-only play is unavailable.', 'Enables touch interaction; target sizes and browser gesture conflicts need checks.'],
 'game.movement': ['Separates simulation ticks from rendering; the exact interval and input ordering must be chosen.', 'Allows continuous positions; elapsed-time integration and collision precision must be specified.'],
 'game.wall': ['Makes the boundary an explicit hazard; collision and end-state behavior need tests.', 'Connects opposite boundaries; wrap coordinates and edge cases need tests.'],
 'game.body': ['Makes body avoidance part of the rules; moving-tail exceptions need a decision.', 'Removes body collision as a loss condition; overlap appearance and remaining end conditions need decisions.'],
 'game.persistence': ['Avoids saved-game migration; progress is lost on closing.', 'Supports selected continuity; the exact saved fields and recovery rules must be named.'],
 'game.pause': ['Keeps fewer game states; temporary interruption cannot preserve a suspended run.', 'Supports interruption; timers and input must resume without duplicate simulation steps.'],
 'game.difficulty': ['Keeps rules stable during a run; progression must come from other chosen mechanics.', 'Allows progression; thresholds, limits and fairness checks must be explicit.'],
 'game.random': ['Allows fully predetermined behavior; variation must come from inputs or fixed sequences.', 'Allows variation; permitted distributions and reproducibility must be chosen.'],
 'game.seed': ['Makes random fixtures repeatable; seed initialization and recording become part of the contract.', 'Avoids a fixed reproducibility promise; exact replay cannot be assumed.'],
 'ai.required': ['Makes AI availability part of the operating contract; refusal and fallback behavior are necessary.', 'Keeps an AI-free path possible; the boundary between optional and required behavior must be clear.'],
 'ai.local': ['Keeps inference within selected local systems; local model capability and resource limits apply.', 'Allows approved remote capability; data permission, availability and accounting need explicit rules.'],
 'ai.cloud': ['Avoids cloud disclosure; capability is limited to the explicitly available noncloud path.', 'Allows specifically approved disclosure; every model and data category must be identified.'],
 'ai.diversity': ['Avoids requiring multiple model families; correlated mistakes need another mitigation if relevant.', 'Allows independent approaches; agreement still requires evidence rather than a truth vote.'],
 'ai.fallback': ['Preserves one exact attempted model; its failure remains visible without another dispatch.', 'Can continue through known alternatives; order, data permission and actual selected model must be recorded.'],
 'ai.identity': ['Supports reproducible attribution; missing or unavailable identity evidence must remain visible.', 'Lets the project choose its evidence threshold; weaker evidence limits reproducibility claims.'],
 'agent.roles': ['Reduces coordination; implementation and verification independence need separate consideration.', 'Separates logic, rendering and review; shared interfaces and artifact handoffs need explicit contracts.'],
 'agent.context': ['Keeps each capsule bounded and inspectable; all necessary facts must be declared.', 'Allows selected shared facts; scope and stale-context handling must be explicit.'],
 'agent.children': ['Keeps the worker topology fixed; additional decomposition requires a coordinator decision.', 'Allows further decomposition; child count, permissions and ownership need bounds.'],
 'agent.communication': ['Centralizes coordination and records; coordinator availability matters.', 'Permits direct exchange; message scope, authority and conflict resolution need rules.'],
 'agent.reviewer': ['Adds independent inspection; review criteria and resource costs must be specified.', 'Avoids a dedicated reviewer requirement; acceptance still needs the chosen verification evidence.'],
 'cluster.nodes': ['Allows placement on any admitted capable node; capability and revision checks remain necessary.', 'Pins placement; an unavailable selected machine needs an explicit failure policy.'],
 'cluster.reassign': ['Preserves placement identity; failed work stays unresolved until another operator decision.', 'Can recover on another admitted node; duplicate work and artifact ownership must be controlled.'],
 'cluster.revision': ['Reduces revision drift; every participating node must obtain the same admitted version.', 'Allows declared version differences; compatibility evidence must identify the supported combinations.'],
 'network.scope': ['Keeps endpoints within the declared local boundary; remote integration is unavailable.', 'Allows named remote integration; endpoint identity, authentication and connectivity need checks.'],
}


def suggestion_tradeoffs(key: str, text: str) -> list[str]:
    for rows in GROUPS.values():
        for name, _dimension, _question, options in rows:
            if name == key and text in options:
                choices = TRADEOFFS.get(key, [])
                index = options.index(text)
                return [choices[index]] if index < len(choices) else []
    return []


def classify(idea: str, template: str = '') -> list[str]:
    """Deterministic routing hints; not accepted project requirements."""
    if template:
        if template not in TEMPLATES:
            raise ValueError('Unknown project template')
        return list(TEMPLATES[template])
    words = idea.lower()
    hints = {'game': ('game', 'snake'), 'web': ('website', 'web app', 'browser'),
             'desktop': ('desktop',), 'operating_system': ('operating system',), 'cli': ('command-line', 'cli tool'),
             'ai': ('model', 'artificial intelligence', ' ai '), 'agent': ('agent',), 'cluster': ('cluster', 'distributed'),
             'embedded': ('embedded',), 'electronics': ('circuit', 'electronics'), 'robotics': ('robot',),
             'scientific': ('scientific', 'simulation', 'experiment'), 'data_pipeline': ('pipeline', 'dataset'),
             'research': ('research',), 'hardware': ('hardware', 'sensor'), 'mechanical': ('mechanical',)}
    found = [domain for domain, terms in hints.items() if any(term in words for term in terms)]
    return found or ['UNKNOWN']


def questions_for(idea: str, domains: list[str], active_dimensions: list[str] | None = None) -> list[dict]:
    groups = ['universal']
    if set(domains) & {'game', 'web', 'desktop'}:
        groups.append('visual')
    groups += [name for name in ('game', 'ai', 'agent', 'cluster') if name in domains]
    if set(domains) & {'hardware', 'embedded', 'electronics', 'robotics', 'mechanical', 'mixed'}:
        groups.append('hardware')
    if set(domains) & {'data_pipeline', 'scientific', 'research', 'ai'}:
        groups.append('data')
    if set(domains) & {'scientific', 'research'}:
        groups.append('scientific')
    if set(domains) & {'web', 'cluster', 'agent'}:
        groups.append('network')
    groups.append('security')
    allowed = set(active_dimensions) if active_dimensions is not None else None
    snake = 'snake' in idea.lower()
    result = []
    for group in groups:
        for key, dimension, text, options in GROUPS[group]:
            if allowed is not None and dimension not in allowed:
                continue
            mandatory = key in MANDATORY or (snake and key in SNAKE_MANDATORY)
            severity = 'BLOCKING' if key in {'purpose', 'platform'} else 'HIGH' if mandatory else 'MEDIUM'
            result.append({'key': key, 'dimension': dimension, 'text': text, 'severity': severity,
                'mandatory': mandatory, 'suggestions': list(options), 'depends_on': DEPENDENCIES.get(key, []),
                'reason': f'Clarify {DIMENSIONS[dimension].lower()} without assuming an answer.'})
    if 'simple' in idea.lower():
        result.append({'key': 'meaning.simple', 'dimension': 'PURPOSE',
            'text': 'Which concrete limits or behaviors make this project simple for you?', 'severity': 'MEDIUM',
            'mandatory': False, 'suggestions': [], 'depends_on': [], 'reason': 'The original idea uses the ambiguous adjective simple.'})
    return result


def active_dimensions(domains: list[str]) -> list[str]:
    names = list(DIMENSIONS)[:33]
    domains = list(domains)
    if set(domains) & {'embedded', 'electronics', 'robotics', 'mechanical', 'mixed'}:
        domains.append('hardware')
    if 'research' in domains:
        domains.append('scientific')
    for domain in domains:
        for name in DOMAIN_DIMENSIONS.get(domain, ()):
            if name not in names:
                names.append(name)
    if set(domains) & {'game', 'desktop'}:
        for name in ('VIEWPORT', 'RENDERING', 'FRAME_TIMING'):
            if name not in names:
                names.append(name)
    return names


def catalog() -> dict:
    return deepcopy({'schema': SCHEMA, 'lifecycle_states': list(LIFECYCLES), 'modes': list(MODES),
        'presentations': ['FOCUS', 'OVERVIEW'], 'roles': list(ROLES), 'domains': list(DOMAINS),
        'dimensions': DIMENSIONS, 'domain_dimensions': DOMAIN_DIMENSIONS, 'templates': TEMPLATES,
        'provenance': list(PROVENANCE), 'severities': list(SEVERITIES), 'entity_schemas': ENTITY_SCHEMAS,
        'question_groups': GROUPS, 'ideation_lenses': IDEATION_LENSES,
        'suggestion_tradeoffs': {key: {text: suggestion_tradeoffs(key, text) for text in options}
            for rows in GROUPS.values() for key, _dimension, _question, options in rows if options}})
