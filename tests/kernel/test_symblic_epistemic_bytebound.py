"""Finite JSON byte preflight/parity checks; no provider, store or native Run imports."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import tracemalloc
import unittest
from unittest import mock

from symblic.kernel import epistemic as E


def load_baseline():
    # Pin the actual pre-bytebound implementation, including its reference
    # claim validator; an older schema-only fixture cannot exercise this path.
    # The file is that implementation (sha256 c3710aed5345...) with one line changed: its import-identity marker
    # now imports symblic.kernel.identity, the package path, instead of the old top-level module name.
    path = Path(__file__).resolve().parent / 'fixtures/symblic_epistemic_prebytebound_c3710aed.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == \
        '0ca32348134d238d4ffd9c8462f62a97b019545aabd1bc1d659df4efd7f0e531'
    spec = importlib.util.spec_from_file_location('_bytebound_preimage', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OLD = load_baseline()
REAL_DUMPS = json.dumps


def result(module, fn, *args, **kwargs):
    try:
        return ('ok', fn(*args, **kwargs))
    except module.EpistemicError as exc:
        return ('error', exc.code, str(exc))


class ByteBound(unittest.TestCase):
    def test_exact_encoding_digest_and_sorting_finite_corpus(self):
        values = [None, True, False, 0, -1, 2**4096 - 1, -(2**4096 - 1), [], {},
                  ''.join(chr(i) for i in range(128)), 'é日本😀\u2028\u2029',
                  {'z': [True, None, {'"\\\0': 'é'}], 'a': '😀'}, {'β': 2, 'a': 3, 'é': 1}]
        rng = random.Random(7301)
        alphabet = 'aé日本😀"\\\n\0\t\u2028'
        for _ in range(100):
            values.append({str(rng.randrange(100)): [''.join(rng.choice(alphabet) for _ in range(40)),
                           rng.randrange(-10**30, 10**30), bool(rng.randrange(2))]})
        for value in values:
            with self.subTest(kind=type(value).__name__):
                expected = OLD._json(value)
                self.assertEqual(E._json(value), expected)
                self.assertEqual(E.digest(value), hashlib.sha256(expected.encode('utf-8')).hexdigest())

    def test_exact_utf8_and_escape_boundaries(self):
        values = ['a'*126, '"'*63, '\\'*63, '\0'*21, '\n'*63, 'é'*63, '日'*42, '😀'*31+'aa',
                  {'é': ['😀', '"\\\n\x1f', -10, True, None]}, []]
        for value in values:
            encoded = REAL_DUMPS(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            size = len(encoded.encode('utf-8'))
            for cap in (size - 1, size, size + 1):
                with self.subTest(size=size,cap=cap), mock.patch.object(E,'MAX_BYTES',cap), mock.patch.object(OLD,'MAX_BYTES',cap):
                    self.assertEqual(result(E,E._json,value),result(OLD,OLD._json,value))
                    self.assertEqual(E._json_fits(value),size<=cap)

    def test_structural_first_error_after_oversized_prefix_is_unchanged(self):
        shared = 'x'*64
        deep=0
        for _ in range(E.MAX_DEPTH+1):deep=[deep]
        cyclic=[];cyclic.append(cyclic)
        values = [[shared]*8+[1.5], [shared]*8+['\ud800'], [shared]*8+[2**4096],
                  [shared]*8+['y'*129], [shared]*8+[deep], [shared]*8+[cyclic],
                  {'z':shared,'later':1.5}, {'z':'\ud800',0:shared}, ['\ud800',shared*3],
                  ['y'*129,1.5], [None]*E.MAX_NODES+[1.5], E._END]
        with mock.patch.object(E,'MAX_BYTES',128),mock.patch.object(OLD,'MAX_BYTES',128):
            for value in values:
                self.assertEqual(result(E,E._json,value),result(OLD,OLD._json,value))

    def test_large_shared_value_never_reaches_whole_encoder(self):
        shared='x'*E.MAX_BYTES
        value=[shared]*(E.MAX_NODES-1)
        def forbidden(*args,**kwargs):raise AssertionError('whole encoder reached')
        with mock.patch.object(E.json,'dumps',side_effect=forbidden):
            self.assertEqual(result(E,E._json,value),('error','limit','Encoded claim exceeds the byte limit'))
            self.assertEqual(result(E,E.digest,value),('error','limit','Encoded claim exceeds the byte limit'))

    def test_repeated_escaped_values_have_bounded_scratch(self):
        value=['\0'*4096]*4096
        tracemalloc.start()
        try:
            got=result(E,E._json,value)
            peak=tracemalloc.get_traced_memory()[1]
        finally:tracemalloc.stop()
        self.assertEqual(got,('error','limit','Encoded claim exceeds the byte limit'))
        self.assertLess(peak,65536)

    def test_fast_make_validate_and_receipt_never_render_oversized_tree(self):
        shared='x'*E.MAX_BYTES
        content=[shared]*4096
        claim=OLD.make_claim('A',0,origin='assumption')
        claim['content']=content
        def contains_big(value):
            frames=[iter((value,))]
            while frames:
                try:item=next(frames[-1])
                except StopIteration:frames.pop();continue
                if type(item)is str and item is shared:return True
                if type(item)is list:frames.append(iter(item))
                if type(item)is dict:frames.append(iter(item.values()))
            return False
        real_canon=E._CANON
        def guarded_canon(value):
            if contains_big(value):raise AssertionError('oversized fast encoder reached')
            return real_canon(value)
        def guarded_dumps(value,*args,**kwargs):
            if contains_big(value):raise AssertionError('oversized reference encoder reached')
            return REAL_DUMPS(value,*args,**kwargs)
        with mock.patch.object(E,'_CANON',side_effect=guarded_canon),mock.patch.object(E.json,'dumps',side_effect=guarded_dumps):
            calls=[lambda:E.make_claim('A',content,origin='assumption'),lambda:E.validate_claim(claim),
                   lambda:E.receipt(subject=content,predicate=1,scope='encoded_schema',passed=True,inputs=[]),
                   lambda:E.receipt(subject=1,predicate=content,scope='encoded_schema',passed=True,inputs=[]),
                   lambda:E.receipt(subject=1,predicate=content,predicate_sha256='0'*64,scope='encoded_schema',passed=True,inputs=[])]
            for call in calls:self.assertEqual(result(E,call),('error','limit','Encoded claim exceeds the byte limit'))

    def test_under_cap_claim_receipt_bytes_and_digest_reuse_unchanged(self):
        for content in [True,2**4096-1,{'é':['😀','"\\\n',-7]},['é'*120]*3]:
            old_receipt=OLD.receipt(subject=content,predicate={'field':'é'},scope='encoded_schema',passed=True,inputs=[])
            new_receipt=E.receipt(subject=content,predicate={'field':'é'},scope='encoded_schema',passed=True,inputs=[])
            self.assertEqual(new_receipt,old_receipt)
            args={'origin':'model_proposal','checks':[old_receipt]}
            old=OLD.make_claim('A',content,**args)
            self.assertEqual(E.make_claim('A',content,**args),old)
            self.assertEqual(E.validate_claim(old),OLD.validate_claim(old))
            cached=E.receipt(subject=content,predicate={'field':'é'},predicate_sha256=old_receipt['predicate_sha256'],scope='encoded_schema',passed=True,inputs=[])
            self.assertEqual(cached,old_receipt)

    def test_malformed_claim_first_errors_match_original_reference(self):
        base=OLD.make_claim('A',0,origin='assumption')
        cases=[]
        for change in [{'origin':'bogus','content':['x'*1000]*8}, {'content':['x'*1000]*8+[1.5]},
                       {'content':['x'*1000]*8+['\ud800']}, {'version':True}, {'checks':[1.5]},
                       {'id':5,'origin':[]}, {'content':{'z':'\ud800',0:1}}, {'content':{'a':1.5}}]:
            row=copy.deepcopy(base);row.update(change);cases.append(row)
        with mock.patch.object(E,'MAX_BYTES',4096),mock.patch.object(OLD,'MAX_BYTES',4096):
            for row in cases:
                expected=result(OLD,OLD._validate_claim_reference,row)
                self.assertEqual(result(E,E.validate_claim,row),expected)
            for content in (['x'*1000]*8,[1.5],['\ud800'],{0:1},2**4096):
                self.assertEqual(result(E,E.make_claim,'A',content,origin='bogus'),
                                 result(OLD,OLD._make_claim_reference,'A',content,origin='bogus'))


if __name__=='__main__':unittest.main()
