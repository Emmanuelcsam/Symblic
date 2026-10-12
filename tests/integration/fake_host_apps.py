"""A stand-in for the host's store module (`host_apps`) so host-route tests can run without the host.

integration/host/symblic_engine.py and its neighbours save run records through a host module named `host_apps`
(atomic JSON files, an inter-process lock and the host's data folder). That module is not part of this
repository. Tests that only need the store install this fake for their own duration:

    fake_host_apps.install(self)                                   # in setUp, for one test
    setUpModule, tearDownModule = fake_host_apps.module_fixture()  # for a whole test module

Both leave the real module in place when the host is present. It implements exactly the four helpers the
store-only routes call. The host's application router (`handle_get`, `handle_post`, `_modules`) is
deliberately absent: `router(test)` returns the real router or skips the test with a reason. With
`fleet=True`, empty `host_fleet` / `host_agents` modules are installed too, so a test can patch their
functions by name.
"""
import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path

DASHBOARD_DIR = str(Path(__file__).resolve().parents[2])   # the repository root plays the host checkout


def data_dir(name, env_var):
    """The folder the environment variable names (tests point it at a temporary folder)."""
    path = os.environ.get(env_var) or os.path.join(tempfile.gettempdir(), 'symblic-fake-host-' + name)
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def save_json(path, value):
    """Write JSON atomically: a temporary file in the same folder, then a rename."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, temporary = tempfile.mkstemp(prefix='.save-', suffix='.json', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_json(path, default=None):
    """The parsed file, or `default` when it is missing or unreadable."""
    try:
        with open(path, encoding='utf-8') as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return default


@contextlib.contextmanager
def store_lock(path):
    """An exclusive flock on PATH.lock for the duration of the block."""
    with open(str(path) + '.lock', 'a', encoding='utf-8') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


# --- installing the fake -------------------------------------------------------------------------------------

def _real_host_present():
    """True when the host's own store module is importable (then tests use it, never this fake)."""
    import importlib
    import sys
    current = sys.modules.get('host_apps')
    if current is not None:
        return current is not sys.modules[__name__]
    try:
        importlib.import_module('host_apps')
        return True
    except ImportError:
        return False


def _fleet_modules():
    """Empty stand-ins for the host's fleet records, so tests can patch their functions by name."""
    import types
    fleet = types.ModuleType('host_fleet')
    fleet.nodes = lambda refresh=False: []
    fleet._draining = lambda ident: False
    agents = types.ModuleType('host_agents')
    agents.active_runs = lambda **_filters: []
    agents.capabilities = lambda *_args, **_kwargs: {}
    return {'host_fleet': fleet, 'host_agents': agents}


def _patcher(fleet=False):
    import sys
    from unittest import mock
    modules = {} if _real_host_present() else {'host_apps': sys.modules[__name__]}
    if fleet:
        modules.update({name: module for name, module in _fleet_modules().items() if name not in sys.modules})
    return mock.patch.dict(sys.modules, modules)


def install(test, *, fleet=False):
    """For one test: the fake store (and, with fleet=True, empty fleet modules) unless the host is present."""
    patcher = _patcher(fleet)
    patcher.start()
    test.addCleanup(patcher.stop)


def module_fixture(*, fleet=False):
    """(setUpModule, tearDownModule) installing the fakes for a whole test module:

        setUpModule, tearDownModule = fake_host_apps.module_fixture()
    """
    state = {}

    def set_up():
        state['patcher'] = _patcher(fleet)
        state['patcher'].start()

    def tear_down():
        state.pop('patcher').stop()
    return set_up, tear_down


def router(test):
    """The host's application router (`host_apps.handle_get` / `handle_post`), or skip the test."""
    import sys
    module = sys.modules.get('host_apps')
    if module is None:
        try:
            import host_apps as module
        except ImportError:
            module = None
    if module is None or not hasattr(module, 'handle_get'):
        test.skipTest("host-only: needs the host's application router (host_apps.handle_get/handle_post), "
                      'which is not part of this repository')
    return module
