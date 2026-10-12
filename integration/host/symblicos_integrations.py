"""HOST-ONLY: adapter stubs and a runtime registry for programs the original host ran beside Symblic.

Why this file is in integration/host/
    The original host ran several agent and model programs next to the Symblic OS prototype: a
    workstation agent service on 127.0.0.1:7000, an autonomous task agent with its own client tests,
    and a fast classifier reached through a host bridge module. None of them is part of this
    repository, and the adapters below reached them only on that host.

Honest status
    Most adapters here are STUBS. invoke(), execute_cell(), dispatch_task() and dispatch_bounded()
    perform no work and return a canned answer marked 'simulated'. The health and smoke checks do
    real but shallow work (a folder or a package.json exists, an HTTP health endpoint answers, a test
    command exits 0). AgentRuntimeRegistry is a hand-written declaration, not a discovery: its
    'health' says 'not checked' because nothing measures it. SymblicOSOrchestration records a job
    order and dependency checks without running any job.

Third-party projects named here
    Transformers.js  https://github.com/huggingface/transformers.js (Hugging Face; revision 511bb61)
    ipy-llm-kernel   https://github.com/haesleinhuepf/ipy-llm-kernel (Robert Haase; revision 397df79)
    Their repositories were expected under <SYMBLICOS_ROOT>/repos/; nothing here installs them.
"""
from __future__ import annotations
import json
import os
import subprocess
import time
import urllib.request
from typing import Any, Dict, List, Optional

from symblic.os.paths import default_root


class AutonomousAdapterError(RuntimeError):
    pass


class TransformersJSAdapter:
    """Transformers.js (https://github.com/huggingface/transformers.js): a repository smoke check only."""

    def __init__(self, repo_dir: Optional[str] = None):
        self.repo_dir = repo_dir or os.path.join(default_root(), 'repos', 'transformers.js')
        self.revision = "511bb61a7c46b73e33f1af3fb308fbd1afe98c02"

    def smoke_test(self) -> Dict[str, Any]:
        """The repository folder exists and its package.json names a version."""
        if not os.path.exists(self.repo_dir):
            return {"ok": False, "error": f"Repository not found at {self.repo_dir}"}
        pkg_file = os.path.join(self.repo_dir, "package.json")
        if os.path.exists(pkg_file):
            with open(pkg_file, "r") as f:
                data = json.load(f)
            return {"ok": True, "version": data.get("version"), "revision": self.revision}
        return {"ok": False, "error": "package.json missing"}

    def invoke(self, text: str) -> Dict[str, Any]:
        """STUB: no inference is performed."""
        return {"adapter": "transformers.js", "input": text, "status": "simulated"}


class IpyLLMKernelAdapter:
    """ipy-llm-kernel (https://github.com/haesleinhuepf/ipy-llm-kernel): a repository smoke check only."""

    def __init__(self, repo_dir: Optional[str] = None):
        self.repo_dir = repo_dir or os.path.join(default_root(), 'repos', 'ipy-llm-kernel')
        self.revision = "397df79cc66fd38bb3131d27d2250b9753dc6524"

    def smoke_test(self) -> Dict[str, Any]:
        """The repository folder exists and holds setup.py or pyproject.toml."""
        if not os.path.exists(self.repo_dir):
            return {"ok": False, "error": "Repo not found"}
        exists = (os.path.exists(os.path.join(self.repo_dir, "setup.py"))
                  or os.path.exists(os.path.join(self.repo_dir, "pyproject.toml")))
        return {"ok": exists, "revision": self.revision, "status": "isolated_smoke_passed" if exists else "missing"}

    def execute_cell(self, code: str) -> Dict[str, Any]:
        """STUB: nothing is executed."""
        return {"adapter": "ipy_llm_kernel", "status": "simulated", "input": code[:30]}


class WorkstationAgentAdapter:
    """A workstation agent service the original host ran on 127.0.0.1:7000 (not part of this repository)."""

    def __init__(self, endpoint: str = "http://127.0.0.1:7000"):
        self.endpoint = endpoint

    def health_check(self) -> Dict[str, Any]:
        """GET <endpoint>/api/health; ok when it answers with JSON."""
        try:
            req = urllib.request.Request(f"{self.endpoint}/api/health")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"ok": True, "status": data.get("status")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def dispatch_task(self, task: str) -> Dict[str, Any]:
        """STUB: nothing is sent."""
        return {"adapter": "workstation_agent", "task": task, "result": "simulated", "bounded": True}


class TaskAgentAdapter:
    """An autonomous task agent the original host ran; its client tests lived in `client_dir`."""

    def __init__(self, client_dir: Optional[str] = None):
        self.client_dir = client_dir

    def smoke_test(self) -> Dict[str, Any]:
        """`node --test client.test.mjs` in the client folder exits 0."""
        if not self.client_dir:
            return {"ok": False, "error": "No client folder configured"}
        try:
            res = subprocess.run(["node", "--test", "client.test.mjs"], cwd=self.client_dir,
                                 capture_output=True, text=True, timeout=10)
            return {"ok": res.returncode == 0, "output": res.stdout[:200]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def dispatch_bounded(self, action_plan: Dict[str, Any]) -> Dict[str, Any]:
        """STUB: refuses a plan that asks for a raw shell; otherwise nothing is sent."""
        if "raw_shell" in action_plan or "cmd" in action_plan:
            raise PermissionError("The task agent adapter rejects host shell execution")
        return {"adapter": "task_agent", "action": action_plan.get("action", "unknown"), "status": "simulated"}


class ClassifierAdapter:
    """A fast classifier the original host reached through a bridge module (status() and
    decide(...)); pass that bridge in, nothing is imported."""

    def __init__(self, bridge=None):
        self.bridge = bridge

    def health_check(self) -> Dict[str, Any]:
        if self.bridge is None:
            return {"ok": False, "error": "No classifier bridge configured"}
        try:
            return {"ok": True, "status": self.bridge.status()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def query(self, question: str) -> Optional[Dict[str, Any]]:
        if self.bridge is None:
            return None
        try:
            return self.bridge.decide({}, {"answer": question}, consumer="symblic", timeout=5, start_wait=0)
        except Exception:
            return None


class AgentRuntimeRegistry:
    """A hand-written declaration of the runtimes the prototype was meant to use. Nothing here is
    measured: every entry's health is 'not checked'."""

    def __init__(self):
        self.runtimes: dict[str, dict] = {}
        self._init_runtimes()

    def _init_runtimes(self):
        declared = {
            "native_symblic": ("Native Symblic Execution", "2.5",
                               ["deterministic_kernel", "formal_logic", "exact_arithmetic", "effects"], "sandboxed_kernel"),
            "local_ollama": ("Local Ollama node", "ollama", ["llama3.2:1b", "qwen3:4b-instruct", "granite3.3:2b"],
                             "one node, local models only"),
            "transformers_js": ("Transformers.js", "511bb61", ["in_browser_inference", "onnx_quantized"], "local_worker"),
            "ipy_llm_kernel": ("ipy-llm-kernel", "397df79", ["interactive_cells", "model_repl"], "isolated_env"),
            "workstation_agent": ("Workstation agent service", "unknown", ["workspace_management", "document_rag"],
                                  "loopback port 7000, authenticated"),
            "task_agent": ("Autonomous task agent", "unknown", ["bounded_task_dispatch"], "scoped tools on one node"),
            "classifier": ("Fast classifier", "1.0", ["fast_forward_pass", "typed_choice", "score"], "bridge module"),
        }
        for key, (name, version, capabilities, boundary) in declared.items():
            self.runtimes[key] = {"name": name, "version": version, "capabilities": capabilities,
                                  "boundary": boundary, "health": "not checked"}

    def get_runtime(self, name: str) -> Optional[Dict[str, Any]]:
        return self.runtimes.get(name)

    def list_runtimes(self) -> List[Dict[str, Any]]:
        return list(self.runtimes.values())


class SymblicOSOrchestration:
    """Job ordering with explicit dependencies. STUB: jobs are checked and recorded, never run."""

    def __init__(self, registry: AgentRuntimeRegistry):
        self.registry = registry

    def dispatch_sequential(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Each job's dependency must be an earlier job; the 'artifact' is a placeholder name."""
        results = []
        artifacts: dict[str, Any] = {}
        for job in jobs:
            dep = job.get("depends_on")
            if dep and dep not in artifacts:
                raise ValueError(f"Missing required dependency '{dep}' for job '{job['id']}'")
            runtime_id = job.get("runtime")
            if not self.registry.get_runtime(runtime_id):
                raise ValueError(f"Runtime '{runtime_id}' unavailable")
            out = {"job_id": job["id"], "runtime": runtime_id, "status": "simulated",
                   "artifact": f"result_of_{job['id']}", "timestamp": time.time()}
            results.append(out)
            artifacts[job["id"]] = out["artifact"]
        return results

    def dispatch_parallel(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{"job_id": job["id"], "runtime": job.get("runtime"), "status": "simulated", "parallel": True}
                for job in jobs]
