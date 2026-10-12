"""A scoped record of the OS prototype's state that never promotes a claim it did not check.

build_final_release_manifest(...) is pure: it takes the reports other steps produced (the acceptance
suite, a virtual boot, a physical inspection, model and framework checks) and assembles one manifest.
Only a complete, internally consistent acceptance report of the isolated fixture suite can mark the
hosted terminal engine 'component_tested'; every other subsystem stays 'unverified' whatever the report
it was given says, with the reason written next to it. generate_final_release_manifest(...) also records
the git commit, the kernel release and file hashes, writes <root>/releases/symblicos_final_manifest.json
and stores a receipt. Neither function boots an image, installs a system, checks a provider,
authenticates a receipt or reruns a check.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from symblic.autogen.durable import atomic_json
from symblic.os.paths import default_root
from symblic.os.receipts import compute_runtime_digest, create_receipt, store_receipt

REPO_ROOT = Path(__file__).resolve().parents[2]          # the repository root


def _acceptance_summary(report):
    report = report if isinstance(report, dict) else {}
    rows = report.get('tests')
    total, passed, failed = (report.get(key) for key in ('total_tests', 'passed_tests', 'failed_tests'))
    counts_valid = all(type(value) is int and value >= 0 for value in (total, passed, failed))
    valid = bool(counts_valid and total > 0 and passed + failed == total and isinstance(rows, list)
                 and len(rows) == total and all(isinstance(row, dict) and type(row.get('passed')) is bool for row in rows))
    if valid:
        valid = (sum(row['passed'] for row in rows) == passed and type(report.get('all_passed')) is bool
                 and report['all_passed'] == (failed == 0))
    all_passed = bool(valid and report.get('all_passed') is True and failed == 0)
    scope = report.get('scope') if isinstance(report.get('scope'), str) else 'unreported'
    return {'all_passed': all_passed, 'passed_tests': passed if valid else 0,
            'failed_tests': failed if valid else 0, 'tests_run': total if valid else 0,
            'scope': scope, 'live_validation': report.get('live_validation') is True and valid and scope != 'isolated_fixture_smoke',
            'report_consistent': valid, 'status': 'passed' if all_passed else 'failed' if valid else 'unverified',
            'not_covered': report.get('not_covered', []),
            'evidence_origin': 'Caller-supplied report; this manifest does not rerun checks or authenticate the report.'}


def _report(value):
    return value if isinstance(value, dict) else {}


def build_final_release_manifest(hardware_info, acceptance_results, virtual_boot_results,
                                 physical_inspection, models_info, frameworks_info, *,
                                 source_revisions=None, host_kernel=None, terminal_sha256=None,
                                 image_sha256=None, receipts_directory=None):
    """Pure report assembly; never promotes unvalidated input into verified state."""
    hardware, boot, physical, models, frameworks = map(_report, (
        hardware_info, virtual_boot_results, physical_inspection, models_info, frameworks_info))
    acceptance = _acceptance_summary(acceptance_results)
    component_checked = acceptance['all_passed'] and acceptance['scope'] == 'isolated_fixture_smoke'
    hosted_state = 'component_tested' if component_checked else 'unverified'
    now = time.time()
    return {
        'manifest_schema': 'symblicos.release.manifest/v2',
        'release_identifier': 'symblicos-hosted-prototype',
        'build_timestamp': now,
        'build_iso8601': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)),
        'record_scope': 'Prototype metadata and supplied evidence; no release certification',
        'prototype_target': {'architecture': 'x86_64', 'hosted_on': 'Linux', 'vm_runtime': 'qemu-system-x86_64'},
        'manifest_host_kernel': host_kernel,
        'source_revisions': source_revisions or {},
        'hardware_target': {
            'node_name': hardware.get('name'), 'model': hardware.get('model'),
            'cpu_count': hardware.get('cpus'), 'ram_gib': hardware.get('ram_gib'),
            'storage_free_gib': hardware.get('disk_free_gib'), 'ip_address': hardware.get('ip'),
            'evidence_origin': 'Caller supplied; not probed by manifest generation',
        },
        'subsystem_states': {
            'hosted_terminal_engine': {
                'state': hosted_state, 'document': 'symblic-terminal.html', 'sha256': terminal_sha256,
                'scope': acceptance['scope'], 'live_validation': False,
                'reason': 'Isolated component checks reported passing; HTTP, browser and live execution are separate boundaries.' if component_checked else 'No scoped hosted-component verification was supplied.',
                'endpoints': ['/api/symblicos/vitals', '/api/symblicos/terminal/submit', '/api/symblicos/receipt'],
            },
            'bootable_virtual_environment': {
                'state': 'unverified', 'image_sha256': image_sha256,
                'vm_runtime': 'qemu-system-x86_64', 'virtual_boot_receipt': boot.get('receipt_id'),
                'reported_results': boot,
                'reason': 'An image hash or supplied receipt reference does not prove a successful boot; this writer does not boot or authenticate a VM.',
            },
            'physical_bare_metal_installation': {
                'state': 'unverified', 'reported_inspection': physical,
                'reason': 'No installation or hardware verification is performed by this writer.',
            },
            'local_models': {
                'state': 'unverified', 'models': models.get('models', []),
                'target_node': models.get('target_node') or models.get('node'),
                'reported_results': models,
                'reason': 'Inventory and fixture responses do not prove live inference or the loaded model identity.',
            },
            'framework_integrations': {
                'state': 'unverified', 'reported_results': frameworks,
                'reason': 'Repository presence and adapter declarations are not execution evidence. No framework health is inferred.',
            },
        },
        'acceptance_suite_summary': acceptance,
        'receipts_directory': receipts_directory,
    }


def _sha256(path):
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def generate_final_release_manifest(hardware_info: dict[str, Any], acceptance_results: dict[str, Any],
                                    virtual_boot_results: dict[str, Any], physical_inspection: dict[str, Any],
                                    models_info: dict[str, Any], frameworks_info: dict[str, Any], *,
                                    output_root: str | os.PathLike | None = None) -> dict[str, Any]:
    """Write the manifest and its receipt under `output_root` (default: paths.default_root(), which honors
    SYMBLICOS_ROOT), without any live verification. Tests must pass output_root."""
    root = Path(output_root or default_root()).resolve()
    receipts = root / 'receipts'
    try:
        git = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=5, check=False)
        revision = git.stdout.strip() if git.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        revision = None
    manifest = build_final_release_manifest(
        hardware_info, acceptance_results, virtual_boot_results, physical_inspection, models_info, frameworks_info,
        source_revisions={'git_head': revision, 'git_head_scope': 'Commit only; uncommitted working files may differ',
                          'symblic_runtime_sha256': compute_runtime_digest()},
        host_kernel=os.uname().release, terminal_sha256=_sha256(REPO_ROOT / 'symblic-terminal.html'),
        image_sha256=_sha256(root / 'build' / 'image' / 'symblicos.img'), receipts_directory=str(receipts))
    receipt = create_receipt(original_instruction='Write scoped SymblicOS prototype evidence record',
                             action_category='release_manifest', target_machine_id=os.uname().nodename)
    manifest['manifest_receipt_id'] = receipt['execution_id']
    path = root / 'releases' / 'symblicos_final_manifest.json'
    atomic_json(path, manifest)
    receipt.update(result_status='success', stdout=f'Wrote scoped prototype metadata to {path}; no live subsystem verification was performed.',
                   completion_timestamp=time.time(), final_result={'manifest_path': str(path), 'sha256': _sha256(path)},
                   validation_checks=['scoped_report_assembled', 'manifest_file_written'], validation_results=[True, True])
    store_receipt(receipt, str(receipts))
    return manifest
