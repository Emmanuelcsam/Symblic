"""HOST-ONLY: the OS prototype's model registry and model calls through the original host.

Why this file is in integration/host/
    Its inventory came from the original host's agent hub (each node's installed Ollama models), and
    every model call went through the host's admitted provider path (symblic.providers.applicators,
    which on that host launched calls through its admission-checked node launcher). Neither the hub
    nor that launcher is part of this repository, so this module cannot run elsewhere. Its pure parts
    are tested with fakes in tests/integration/test_symblicos_model_engine.py.

What it does
    SymblicOSModelEngine(target_node_id, hub=...) builds a registry of the models listed on one node,
    plans whether a set of models fits a node's free space (capacity_plan: exact byte sizes only,
    unknown sizes block), checks a model's health by asking for the exact word READY, and invokes a
    model with a prompt while recording it in an OS receipt. A model that is not in the registry is
    refused; there is no fallback to another model.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional

from symblic.os.paths import default_root


class SymblicOSModelEngine:
    def __init__(self, target_node_id: str = '', receipts_dir: Optional[str] = None, hub=None):
        self.target_node_id = target_node_id
        self.receipts_dir = receipts_dir or os.path.join(default_root(), 'receipts')
        self.hub = hub                  # the host's agent hub: fleet_nodes() with each node's 'models'
        self.registry: dict[str, dict] = {}

    def _inventory(self, node_id=''):
        if self.hub is None:
            raise RuntimeError('No model inventory source: SymblicOSModelEngine(hub=...) needs the host\'s agent hub.')
        rows = []
        for node in self.hub.fleet_nodes():
            if node_id and node['id'] != node_id:
                continue
            for model in node.get('models') or []:
                rows.append({'identifier': model['name'], 'runtime': 'ollama', 'node': node['id'],
                             'family': model.get('vendor', 'unknown'), 'size_bytes': model.get('size'),
                             'digest': model.get('digest'), 'availability': 'listed' if node.get('online') else 'offline'})
        return rows

    def inventory_host(self) -> List[Dict[str, Any]]:
        """The models listed on the hub's own machine."""
        return self._inventory(getattr(self.hub, 'LOCAL_NODE', ''))

    def inventory_target(self) -> List[Dict[str, Any]]:
        return self._inventory(self.target_node_id)

    def capacity_plan(self, models, target_free_bytes):
        """Whether `models` (rows with exact size_bytes) fit `target_free_bytes` with a 20% working
        allowance. Any unknown size blocks the plan: rounded catalogue sizes cannot prove capacity."""
        sizes = [m.get('size_bytes') for m in models]
        known = all(isinstance(size, int) and size >= 0 for size in sizes)
        total = sum(sizes) if known else None
        allowance = (total + 4) // 5 if known else None
        needed = total + allowance if known else None
        fits = known and needed <= target_free_bytes
        return {'total_model_bytes': total, 'working_allowance_bytes': allowance,
                'required_total_bytes': needed, 'target_free_bytes': target_free_bytes,
                'all_fit': fits, 'planned_models': [m['identifier'] for m in models],
                'status': 'accepted' if fits else 'blocked',
                'reason': '' if known else 'Exact model byte sizes are unavailable; rounded catalogue sizes cannot prove capacity.'}

    def build_registry(self):
        self.registry = {m['identifier']: {'model_identifier': m['identifier'], 'runtime': 'ollama',
                         'node': self.target_node_id or '', 'digest': m.get('digest'), 'family': m['family'],
                         'max_context': None, 'availability': m['availability'], 'provenance': 'local',
                         'transport': 'symblic.providers.applicators (the host\'s admitted provider path)'}
                         for m in self.inventory_target()}
        return self.registry

    def _call(self, model_identifier, prompt, timeout=120):
        from symblic.providers.applicators import Applicators
        from symblic.autogen.runner import execution_fence
        execution_fence()
        stop = threading.Event()
        timer = threading.Timer(timeout, stop.set)
        timer.daemon = True
        timer.start()
        try:
            return Applicators(owner_label='operator (SymblicOS)', allow_web=False, thermal=True).call({
                'app': {'engine': 'ollama', 'model': model_identifier, 'node': self.target_node_id},
                'system': 'Answer only the current explicit instruction. No previous conversation is supplied.',
                'prompt': prompt, 'schema': None, 'stop': stop, 'tools': 'none', 'temperature': 0,
            })
        finally:
            timer.cancel()

    def verify_local_model_health(self, model_identifier, timeout=60.0):
        """Healthy only when the model answers exactly READY."""
        started = time.time()
        result = self._call(model_identifier, 'Respond with the single word: READY', timeout)
        answer = str(result.get('text') or '').strip()
        return {'healthy': result.get('ok') is True and answer == 'READY', 'model': model_identifier,
                'startup_latency_s': time.time() - started, 'status': 'completed' if result.get('ok') else 'failed',
                'response': answer, 'parsed': result.get('ok') is True, 'error': result.get('error', ''),
                'node': result.get('node'), 'model_identity': result.get('model_identity')}

    def invoke_model_adapter(self, model_identifier, prompt, require_local=True, receipt=None):
        """Call a registered model; refuse an unregistered one (no fallback is ever attempted)."""
        if model_identifier not in self.registry:
            raise RuntimeError(f"Model '{model_identifier}' is not in the visible local registry. No fallback was attempted.")
        started = time.time()
        if receipt is not None:
            receipt['models_invoked'].append(model_identifier)
            receipt['model_identifiers'].append(model_identifier)
            receipt['action_category'] = 'model_invocation'
        result = self._call(model_identifier, prompt)
        if not result.get('ok'):
            if receipt is not None:
                receipt.update(result_status='runtime_failure', stderr=result.get('error') or 'Model invocation failed')
            raise RuntimeError(result.get('error') or 'Model invocation failed')
        response = {'ok': True, 'response': result.get('text', ''), 'latency_s': time.time() - started,
                    'provenance': 'local', 'node': result.get('node'), 'model_identity': result.get('model_identity')}
        if receipt is not None:
            receipt.update(stdout=response['response'], result_status='success', final_result=response)
        return response
