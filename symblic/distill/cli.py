"""Command line for the distillation pipeline: build, split, plan, prepare and compare jobs.

    python3 -m symblic.distill.cli COMMAND ...      (python3 -m symblic.distill.cli --help lists them)

Reads only the files named on the command line (bounded strict JSON), writes only new files (never overwrites),
and never trains, generates, downloads or dispatches anything. ``launch`` and ``launch-infer`` PRINT the worker
command for the operator's runner; they do not execute it. Every result is one line of canonical JSON; a
refusal prints {"status": "refused", "code": ...} and exits 2.

The pipeline, in order (see README.md in this package and docs/reference/DISTILLATION.md):
    export-run / export-contracts  accepted Symblic runs -> records / trusted native contract bundle
    build                          records -> provenance-pinned dataset
    split                          dataset -> frozen, leakage-aware train/validation/test splits
    model-manifest, plan-train     pin a local model snapshot; freeze an SFT/LoRA plan
    prepare-train, launch          job directory; the worker command to run it
    checker-identity, plan-eval, prepare-eval   freeze the baseline-vs-trained evaluation
    compare                        exact paired comparison of the recorded outcomes
    hash, native-check, launch-infer, grpo-status   utilities

Depends on: ``symblic.distill.datasets`` and ``symblic.distill.worker`` (both inert on import); ``contracts`` and
``export`` are imported only by their commands.
"""

import argparse
import json
import os
import sys

from symblic.distill import datasets as D
from symblic.distill import worker as W

# Default --repo for the export commands: the checkout this module belongs to.
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _out(path, value, key):
    """Write `value` to a new file and report its digest field `key`."""
    D.write_json(path, value, exclusive=True)
    return {'status': 'written', 'path': path, 'sha256': value[key]}


def main(argv=None):
    """Parse argv, run one command, print its JSON result. Exit 0 on success, 2 on a refusal."""
    p = argparse.ArgumentParser(prog='python3 -m symblic.distill.cli',
                                description='Build, split, plan, prepare and compare Symblic distillation jobs.')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('hash', help='canonical sha256 of a JSON file')
    s.add_argument('file')
    s = sub.add_parser('native-check', help='recheck a recorded scalar answer locally without any model call')
    s.add_argument('--dataset', required=True)
    s.add_argument('--item-id', required=True)
    s.add_argument('--answer-json', required=True)
    s.add_argument('--native-checker', required=True)
    s = sub.add_parser('export-contracts', help='export trusted closed native predicate contracts; no providers')
    s.add_argument('--repo', default=HERE)
    s.add_argument('--runs', required=True)
    s.add_argument('--dataset', required=True)
    s.add_argument('--out', required=True)
    s = sub.add_parser('export-run', help='strict local native replay -> accepted scalar records; never calls models')
    s.add_argument('--repo', default=HERE)
    s.add_argument('--run-dir', required=True)
    s.add_argument('--group-key', required=True)
    s.add_argument('--lock-file')
    s.add_argument('--out', required=True)
    s = sub.add_parser('build', help='accepted records -> provenance-pinned dataset')
    s.add_argument('--records', required=True)
    s.add_argument('--out', required=True)
    s.add_argument('--allow-unavailable-model-identity', action='store_true')
    s.add_argument('--lenient', action='store_true', help='list rejected records instead of refusing the build')
    s = sub.add_parser('split', help='freeze leakage-aware train/validation/test splits')
    s.add_argument('--dataset', required=True)
    s.add_argument('--seed', required=True)
    s.add_argument('--ratios', default='80,10,10')
    s.add_argument('--exposures')
    s.add_argument('--group-by', default='source,digit_skeleton',
                   help="optional groupings, comma-separated; '' keeps only the mandatory ones (recorded)")
    s.add_argument('--out', required=True)
    s = sub.add_parser('model-manifest', help='pin a local Hugging Face snapshot directory')
    s.add_argument('--model-dir', required=True)
    s = sub.add_parser('plan-train', help='freeze an SFT/LoRA training plan')
    s.add_argument('--dataset', required=True)
    s.add_argument('--splits', required=True)
    s.add_argument('--model-spec', required=True)
    s.add_argument('--options')
    s.add_argument('--method', default='sft_lora')
    s.add_argument('--out', required=True)
    s = sub.add_parser('prepare-train', help='create a training job directory (train/validation rows only)')
    for flag in ('--dataset', '--splits', '--plan', '--jobs-root', '--name'):
        s.add_argument(flag, required=True)
    s.add_argument('--expect-plan-sha256')
    s = sub.add_parser('plan-eval', help='freeze the baseline-vs-trained evaluation')
    for flag in ('--dataset', '--splits', '--plan', '--out'):
        s.add_argument(flag, required=True)
    s.add_argument('--max-new-tokens', type=int, default=256)
    s.add_argument('--prior-test-uses', type=int, default=0)
    s.add_argument('--checker', default='schema', choices=D.CHECKERS)
    s.add_argument('--native-checker', help='checker pin JSON from `checker-identity` (schema_and_native only)')
    s = sub.add_parser('checker-identity', help='pin of a root-registered native checker (trusted module only)')
    s.add_argument('--name', required=True)
    s = sub.add_parser('prepare-eval', help='create an evaluation job directory pinned to one checkpoint')
    for flag in ('--eval-plan', '--plan', '--adapter-manifest-sha256', '--jobs-root', '--name'):
        s.add_argument(flag, required=True)
    s = sub.add_parser('launch', help='print the worker command/manifest for root (does not run it)')
    for flag in ('--job-dir', '--models-root', '--python'):
        s.add_argument(flag, required=True)
    s.add_argument('--adapter-dir')
    s = sub.add_parser('launch-infer', help='print (not run) the explicit inference command')
    for flag in ('--plan', '--prompt', '--out', '--models-root', '--python'):
        s.add_argument(flag, required=True)
    s.add_argument('--arm', default='trained', choices=D.ARMS)
    s.add_argument('--adapter-dir')
    s.add_argument('--adapter-manifest-sha256')
    s.add_argument('--max-new-tokens', type=int, default=256)
    s.add_argument('--dataset')
    s.add_argument('--splits')
    s = sub.add_parser('compare', help='pure comparison of recorded evaluation outcomes')
    s.add_argument('--eval-plan', required=True)
    s.add_argument('--outcomes', required=True)
    sub.add_parser('grpo-status', help='status of the verifiable-reward/GRPO adapter')
    args = p.parse_args(argv)
    try:
        result = _dispatch(args)
    except (D.DistillError, W.WorkerError) as exc:
        print(json.dumps({'status': 'refused', 'code': exc.code}))
        return 2
    print(D.canonical(result))
    return 0


def _dispatch(a):
    """Run the parsed command `a.cmd` and return its JSON-able result."""
    if a.cmd == 'hash':
        return {'sha256': D.digest(D.read_json(a.file))}
    if a.cmd == 'native-check':
        data = D.read_json(a.dataset)
        D.verify_dataset(data)
        items = [it for it in data['items'] if it['item_id'] == a.item_id]
        if len(items) != 1 or len(a.answer_json) > 100000:
            raise D.DistillError('native_check_input')
        try:
            answer = json.loads(a.answer_json)
        except ValueError:
            raise D.DistillError('native_check_input') from None
        pin = D.native_checker_pin(D.read_json(a.native_checker))
        checker = W.load_native_checker(pin)
        try:
            receipt = checker.check(D.native_contract(items[0]), answer)
        except ValueError:
            raise W.WorkerError('native_contract_refused') from None
        return {'scope': 'local_recorded_answer_recheck', 'model_calls': 0, 'item_id': a.item_id,
                'answer_sha256': D.digest(answer), 'checker': pin, 'receipt': receipt}
    if a.cmd == 'export-contracts':
        from symblic.distill import contracts as C
        from symblic.distill import checkers as N
        try:
            bundle = C.build_bundle(a.repo, D.read_json(a.runs), D.read_json(a.dataset))
        except N.NativeContractError:
            raise D.DistillError('native_contract_export_refused') from None
        D.write_json(a.out, bundle, exclusive=True)
        return {'status': 'written', 'path': a.out, 'bundle_sha256': bundle['bundle_sha256'],
                'supported': len(bundle['contracts']), 'rejected': bundle['rejected']}
    if a.cmd == 'export-run':
        from symblic.distill import export as E
        try:
            rows, receipt = E.export_run(a.repo, a.run_dir, a.group_key, a.lock_file)
        except E.ExportError:
            raise D.DistillError('native_export_refused') from None
        D.write_json(a.out, rows, exclusive=True)
        return {**receipt, 'status': 'written', 'path': a.out, 'records_sha256': D.digest(rows)}
    if a.cmd == 'build':
        return _out(a.out, D.build_dataset(D.read_json(a.records),
                                           allow_unavailable_model_identity=a.allow_unavailable_model_identity,
                                           strict=not a.lenient), 'dataset_sha256')
    if a.cmd == 'split':
        try:
            ratios = [int(x) for x in a.ratios.split(',')]
        except ValueError:
            raise D.DistillError('ratios') from None
        exposures = D.read_json(a.exposures) if a.exposures else None
        group_by = [g for g in a.group_by.split(',') if g]
        return _out(a.out, D.freeze_splits(D.read_json(a.dataset), seed=a.seed, ratios=ratios, exposures=exposures,
                                           group_by=group_by), 'splits_sha256')
    if a.cmd == 'model-manifest':
        return W.model_manifest(os.path.abspath(a.model_dir))
    if a.cmd == 'plan-train':
        options = D.read_json(a.options) if a.options else None
        return _out(a.out, D.plan_training(D.read_json(a.dataset), D.read_json(a.splits),
                                           model=D.read_json(a.model_spec), options=options, method=a.method), 'plan_sha256')
    if a.cmd == 'prepare-train':
        plan = D.read_json(a.plan)
        D.verify_plan(plan, expected_sha256=a.expect_plan_sha256)
        job = D.training_job(D.read_json(a.dataset), D.read_json(a.splits), plan)
        return {'status': 'prepared', 'job_dir': W.prepare_job(a.jobs_root, a.name, job), 'job_sha256': job['job_sha256']}
    if a.cmd == 'plan-eval':
        return _out(a.out, D.plan_evaluation(D.read_json(a.dataset), D.read_json(a.splits), D.read_json(a.plan),
                                             max_new_tokens=a.max_new_tokens, prior_test_uses=a.prior_test_uses,
                                             checker=a.checker,
                                             native_checker=D.read_json(a.native_checker) if a.native_checker
                                             else None), 'eval_sha256')
    if a.cmd == 'prepare-eval':
        job = W.eval_job(D.read_json(a.eval_plan), D.read_json(a.plan),
                         adapter_manifest_sha256=a.adapter_manifest_sha256)
        return {'status': 'prepared', 'job_dir': W.prepare_job(a.jobs_root, a.name, job), 'job_sha256': job['job_sha256']}
    if a.cmd == 'launch':
        return W.launch_manifest(a.job_dir, models_root=a.models_root, python=a.python, adapter_dir=a.adapter_dir)
    if a.cmd == 'checker-identity':
        return W.checker_identity(a.name)
    if a.cmd == 'launch-infer':
        if (a.dataset is None) != (a.splits is None):
            raise D.DistillError('overlap_needs_dataset_and_splits')
        return W.infer_manifest(plan_path=a.plan, prompt_path=a.prompt, out_path=a.out, models_root=a.models_root,
                                python=a.python, arm=a.arm, adapter_dir=a.adapter_dir,
                                adapter_manifest_sha256=a.adapter_manifest_sha256, max_new_tokens=a.max_new_tokens,
                                dataset_path=a.dataset, splits_path=a.splits)
    if a.cmd == 'compare':
        return D.compare(D.read_json(a.eval_plan), D.read_json(a.outcomes))
    if a.cmd == 'grpo-status':
        return D.grpo_status()
    raise D.DistillError('unknown_command')


if __name__ == '__main__':
    sys.exit(main())
