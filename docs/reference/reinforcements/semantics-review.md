# Symblic semantics review: compiler-design pass

Date: 2026-10-02. Reinforcement `symrein-semantics` for the Symblic effort. Review only: no core
file was changed. This is a bounded first pass, not a literature survey.

**Baseline.** Commit `1a13f18e33bee9dfb52b37ef78687d6f6c8e620c` (this checkout's "agents: baseline" commit,
Symblic 2.0). Every `file:line` below refers to that commit.

**Already resolved in the coordinator's current snapshot.** These were present at the baseline and are not
open bugs: canonical tag collisions, conflicting record field aliases, and ensure-retry call caching (see §5.2).

**Evidence labels.**
- [measured]: reproduced on a cluster node at the baseline (Python 3.11.2, UCD 14.0.0). One case was also run
  on Python 3.12.14 (UCD 15.0.0) through `uv run --offline`.
- [reading]: from reading the source; not executed.
- [proposal]: not implemented anywhere.

How the reproductions were run: fake applicators in the style of `tests/kernel/test_symblic.py`, in-memory runs with
no run folder, no network, and CPU and memory limits. The script and its output are in Appendix A.

---

## 1. Findings

- **Deterministic by construction:**
  - parsing;
  - exact kernel arithmetic and logic;
  - acceptance, meaning reply plus type → value or rejection (`read_answer`/`coerce`);
  - consensus given the ordered samples;
  - replay given identical request bytes.

  The kernel-identity claim holds for the programs it was verified on (`docs/reference/kernel-identity.json`).
- **Not guaranteed today, and fixable in the kernel:**
  - Which lines are formal is decided by the line's first ASCII word. Formal-looking lines silently become
    model calls (R1).
  - `ensure … else retry` is not transactional and does not see data that flows through the KB (R2).
  - `ask … for each` builds prompts from thread-shared state (R3).
  - Some kernel results depend on `PYTHONHASHSEED`, `PYTHONINTMAXSTRDIGITS` and the Unicode database version
    of the running Python (R4).
  - `check()` accepts programs whose failure is decidable from their text (R5).
- **Not guaranteeable by any canonicalization:**
  - An ask's meaning or correctness. The kernel can establish `τ(x) ∧ c` (the declared type and the
    ensure/assert conditions) for the bound value. It can never establish that `x` is what the instruction
    meant.
  - Agreement is a property of the applicators' output distribution, not of the truth. In addition, the
    reported agreement number currently overstates support: ties are reported as uncontested, abstentions are
    ignored, and field-wise votes can assemble a record nobody gave (§5.1).
- **Five recommendations (§7), in priority order:**
  1. a transactional, data-flow-anchored retry;
  2. per-item capsule inputs;
  3. a kernel purity gate plus a recorded kernel identity;
  4. an explicit formal/prose boundary;
  5. a sound static check.

## 2. Guarantee map

| Layer | Deterministic (conditions) | Gap | Evidence |
|---|---|---|---|
| Classification and parse | `parse()` is a pure function of the source (and of the Python UCD, through `_NAME_RX`). | Formal vs prose is decided by the first ASCII word (`split_statements` symblic/kernel/language.py:248, `_looks_formal` :267). | R1, G1, G16 |
| Static check (`check` :3101) | Syntax, single assignment, unsafe rules (as written), negation cycles, unknown options and efforts. | Definite assignment, rule binding order, ground facts, enum distinctness, loop alignment, termination. | R5 |
| Kernel | Exact rationals, Decimal series, sorted iteration over sets (`_iterable` :2144, `_seq` :2409), Datalog least fixpoint with sorted query results (`KB.query` :2946). | `str()` of a set depends on the hash seed; the int↔str limit depends on an environment variable; text operations depend on the UCD; the step budget does not bound time (`matches`); value identity is not a congruence (§5.1). | R4 |
| Acceptance (`read_answer` :3457, `coerce` :1720) | A pure function of (reply, type). The normative relation is `coerce`, not the JSON Schema: records ignore extra fields, and ranges and lengths are enforced by the kernel. | Lenient numeric text changes meaning (`"1,5"` → 15). Enum options that collide under normalization cannot be answered. Numeric enum options become Text. | §5.1, G9, G10 |
| Canonical form and fingerprint (`canon` :1453) | Equal canonical JSON means an equal fingerprint. | Equal fingerprints do not imply equal kernel behaviour (`len`, ordering, the value an `Any` ask binds). Paraphrases are never equated. | §5.1 |
| Consensus (`consensus` :3477) | A pure function of the ordered valid samples (plan order, not arrival order). | A 1–1 tie is uncontested; abstentions are ignored; `consensus_fields` :3508 can assemble a record that no sample gave. | §5.1 |
| `ensure`/retry (`Run.exec_block` symblic/kernel/run.py:209) | Deterministic given the replies. | Not transactional; KB data flow has no anchor; blame goes to the nearest ask. | R2, §5.1 |
| Replay (`call_key` symblic/kernel/run.py:131) | The same request bytes give the same cached reply. | Under `for each`, the request bytes depend on thread scheduling (R3). Records carry no kernel or UCD identity (R4). | R3, R4 |

## 3. Grammar draft (EBNF, derived from the parser)

The notation is W3C XML 1.0 §6 EBNF [W3C-EBNF]. Each rule names the parser symbol it was read from.
Keywords and type words are case-insensitive. A trailing `STOP` (period) is optional on every statement
(`Parser.finish` :398).

```ebnf
/* L0  physical lines -> statement texts      split_statements :223, _scan_open :272 */
source        ::= ( blank | comment-line | formal-text | prose-line )*
comment-line  ::= S* ( '#' | '//' ) [^#xA]*
/* Procedural classification. W = the line's leading [A-Za-z_]+ (ASCII only), lowercased:              */
/*   prose  if (W not in KEYWORDS + EXTENSIONS and not looks-formal) or W in RAW_KEYWORDS or V1_DIRECTIVE */
/*   formal otherwise                                                                                    */
looks-formal  ::= [0-9([{"'¬∀∃-] [^#xA]*                    /* _looks_formal :267 tests the FIRST character only */
formal-text   ::= line ( #xA line )*                         /* joined while a bracket or string is open, or a line ends in '\' */
                | formal-text #xA S* ( 'with' | 'from' | 'by' | 'where' | 'for each' ) [^#xA]*
                                                             /* BLOCK_CONT: glued to the previous FORMAL statement */
prose-line    ::= ( 'program' | 'workflow' ) ':'? REST       /* _prose :981 -> program */
                | ( 'module' | 'section' ) ':'? REST         /*              -> section */
                | 'note' ':'? REST                           /*              -> note    */
                | 'use' WORDS ':' VALUE                      /* v1 directive -> use (only USE_OPTIONS keys) */
                | v1-context? INSTRUCTION                    /* -> ask stepN : Text, context=none|all */

/* L1  tokens                                  tokenize :156, _read_string :128 */
NUM      ::= [0-9]+ ( '.' [0-9]+ )? ( [eE] [+-]? [0-9]+ )?   /* _NUM_RX; refused if a letter or '_' follows; no size gate */
NAME     ::= letter ( letter | digit | '_' )*                /* _NAME_RX [^\W\d]\w* : Unicode classes of the RUNNING Python */
STR      ::= '"' c* '"' | "'" c* "'" | '"""' any* '"""' | "'''" any* "'''"
                                                             /* escapes \n \t \\ \" \' \{ \}; other \x kept verbatim */
OP       ::= longest match of OPERATORS, mapped by CANON_OP  /* && ∧ -> and; || ∨ -> or; ! ¬ -> not; == -> =; ** -> ^;
                                                                ∀ -> all; ∃ -> any; ∈ -> in; ∉ -> not in; ⊆ ⊂ -> subset ... */
ATTR     ::= '.' /* followed by a NAME start */
STOP     ::= '.' /* followed only by spaces and comments */
skip     ::= [#x20#x9#xD] | '\' | '#' [^#xA]*               /* '\' outside a string is dropped anywhere */

/* L2  statements                              parse :911, parse_statement :1026 */
block         ::= ( simple-stmt | if-block | for-block | ext-block )*
if-block      ::= 'if' expr 'then'? block ( ( 'elif' | 'else' 'if' ) expr 'then'? block )* ( 'else' block )? end
for-block     ::= 'for' NAME 'in' expr 'do'? block end
end           ::= 'end' ( 'if' | 'for' | 'loop' )?           /* _end_tail :975: the label is NOT matched to the block */
simple-stmt   ::= use | given | let | define | term | fact | rule | ask | check-stmt | output | group
                | forget-pin | delegate | bare-show
use           ::= 'use' option-list                          /* keys in USE_OPTIONS :902 */
given         ::= 'given' NAME ( ':' type )? ( '=' expr )?
let           ::= 'let' NAME ( ':' type )? '=' expr ( 'with' option-list )?   /* only weight is read */
define        ::= 'define' NAME 'as' type
term          ::= 'term' ( NAME | STR ) NAME* ( 'means' | 'is' ) STR
fact          ::= 'fact' atom ( ',' atom )*                  /* atom ::= NAME call-args; arguments may be ANY expression */
rule          ::= 'rule' atom 'if' body-lit ( ( ',' | 'and' ) body-lit )*      /* check_rule_safety :1313 */
body-lit      ::= 'not' atom                                 /* p_literal :1222 */
                | atom                                       /* only if NAME is not a builtin and no compop or 'in' follows */
                | comparison
ask           ::= 'ask' NAME ( ':' type )? '='? STR ask-clause*                /* p_ask :1269 */
ask-clause    ::= 'for' 'each' NAME 'in' expr | 'from' NAME ( ',' NAME )* | 'by' expr | 'with' option-list
check-stmt    ::= ( 'ensure' | 'assert' | 'expect' ) expr ( 'else' ( 'retry' | 'fail' | 'warn' ) )? ( 'because' expr )?
                                                             /* default: ensure -> retry, assert/expect -> fail (:1136) */
output        ::= ( 'show' | 'return' | 'draw' ) expr ( 'as' expr )?
group         ::= 'group' NAME '='? expr
forget-pin    ::= ( 'forget' | 'pin' ) NAME ( ',' NAME )* ( 'with' option-list )?
delegate      ::= 'delegate' ( NAME '=' )? expr 'to' expr ( 'with' option-list )?
bare-show     ::= expr                                       /* reached only for lines classified formal */
option-list   ::= 'with'? ( 'and' | NAME ( ( '=' | ':' ) ( 'last' NUM | expr ) )? ','? )*
                                                             /* p_options :1238; 'last' NUM only for context; a bare NAME
                                                                means true; stops before by/from (not followed by = or :)
                                                                or 'for each' */

/* L3  expressions                             Parser._expr :414 ... primary :604 */
expr        ::= 'if' expr 'then' expr 'else' expr
              | quant NAME 'in' setop ':' expr               /* only when NAME 'in' follows the quantifier word */
              | implies
quant       ::= 'all' | 'every' | 'any' | 'some' | 'none'    /* ∀ ∃ arrive as ops all/any */
implies     ::= iff ( ( '->' | 'implies' ) implies )?        /* right associative */
iff         ::= or ( ( '<->' | 'iff' ) or )*
or          ::= xor ( 'or' xor )*
xor         ::= and ( 'xor' and )*
and         ::= not ( 'and' not )*
not         ::= 'not' not | comparison
comparison  ::= setop ( compop setop )*                      /* chained: a op b op c = (a op b) and (b op c) */
compop      ::= '=' | '!=' | '<' | '<=' | '>' | '>=' | 'in' | 'not' 'in' | 'subset' | 'divides' | 'is' | 'is' 'not'
setop       ::= range ( ( 'union' | 'intersect' | 'minus' ) range )*   /* ONE level, left associative */
range       ::= additive ( '..' additive )?
additive    ::= term ( ( '+' | '-' ) term )*
term        ::= unary ( ( '*' | '/' | '//' | '%' | 'mod' ) unary )*
unary       ::= ( '-' | '+' ) unary | power
power       ::= postfix ( '^' unary )?                       /* right associative through unary: -2 ^ 2 = -4 */
postfix     ::= primary ( ATTR NAME | '[' expr ']' | call-args )*        /* call-args only right after a NAME */
call-args   ::= '(' ( arg ( ',' arg )* ','? )? ')'
arg         ::= NAME '=' expr | expr                         /* NAME '=' is ALWAYS a keyword argument */
primary     ::= NUM | STR | 'true' | 'false' | '(' expr ')' | '|' expr '|'
              | '[' ( expr 'for' NAME 'in' setop ( 'if' expr )? | ( expr ( ',' expr )* ','? )? ) ']'
              | '{' ( field-init ( ',' field-init )* ','? | expr ( ',' expr )* ','? )? '}'   /* {} is the empty SET */
              | ( 'query' | 'holds' ) NAME call-args          /* both build the same node */
              | NAME
field-init  ::= ( NAME | STR ) ':' expr                      /* record if NAME|STR ':' opens the braces */
STR-body    ::= ( text | '{{' | '}}' | '\{' | '\}' | '{' expr '}' )*  /* parse_interpolation :851 */

/* L4  types                                   Parser.type_expr :703, _options :786 */
type        ::= '(' type ')'
              | ( 'Int' | 'Integer' ) num-range?
              | ( 'Number' | 'Num' | 'Real' | 'Decimal' ) ( 'to' NUM ( 'places' | 'place' | 'decimals' | 'decimal' | 'dp' ) )? num-range?
              | ( 'Bool' | 'Boolean' )
              | ( 'Text' | 'String' | 'Str' ) ( 'up' 'to' NUM ( 'words' | 'word' ) )?
              | 'one' 'of' ( '{' enum-opt ( ',' enum-opt )* '}' | '[' enum-opt ( ',' enum-opt )* ']' )
              | ( 'List' | 'Set' ) 'of' type ( ( 'length' | 'len' | 'size' ) NUM ( '..' NUM )? )?
              | ( 'Record' | 'Object' ) '{' field-ty ( ',' field-ty )* ','? '}'
              | ( 'Svg' | 'Drawing' ) | 'Any'
              | NAME                                         /* a define'd type */
num-range   ::= 'in' '-'? NUM '..' '-'? NUM                  /* literals only; lo <= hi */
enum-opt    ::= ( NAME | STR | NUM ) ( NAME | '-' NAME )*     /* "deep red", pale-yellow; >= 2; no EXACT duplicates */
field-ty    ::= ( NAME | STR ) ':' type
```

**Precedence**, from tightest to loosest:

| Level | Operators |
|---|---|
| 1 | postfix `.f`, `[i]`, `f(…)` |
| 2 | `^` (right associative) |
| 3 | unary `- +` |
| 4 | `* / // % mod` |
| 5 | `+ -` |
| 6 | `..` |
| 7 | `union intersect minus` (one level) |
| 8 | comparisons (chained) |
| 9 | `not` |
| 10 | `and` |
| 11 | `xor` |
| 12 | `or` |
| 13 | `iff` |
| 14 | `implies` (right associative) |
| 15 | `if…then…else`, quantifiers |

### Grammar ambiguities found

All of these are [measured] unless marked.

| # | Ambiguity | Example and observed result |
|---|---|---|
| G1 | Prose fallback is decided by the first word. | R1 |
| G2 | A binding named after a keyword shadows that keyword only at the start of a statement. | `let show = 1.` then `show + 1.` outputs `1`: the second line is `show (+1)`. |
| G3 | A conditional expression cannot start a statement. | `if 1 < 2 then 3 else 4.` is a syntax error (it is read as a block `if`); `show if …` works. |
| G4 | `\|\|` lexes as `or`. | `\|\|-3\| - 1\|` fails; `\| \|-3\| - 1 \|` = 2. |
| G5 | `name = e` inside a call is always a keyword argument. | `count(xs, x = 1)` raises "unexpected keyword argument"; write `(x = 1)`. |
| G6 | Chained comparisons include `in`, `subset` and `divides`. | `1 < 2 in [true]` is false (it means `1 < 2 and 2 in [true]`); `(1 < 2) in [true]` is true. |
| G7 | Set operators share one precedence level. | `{1} union {2} intersect {2}` = `{2}`. |
| G8 | `end` labels are not checked against the open block. | `if c then … end for.` closes the `if`. |
| G9 | Enum options are strings. | `one of {1, 2, 3}` answered `1` binds Text `"1"`: `n = 1` is false and `n + 1` is a type error. `one of {true, false}` rejects JSON `true`. |
| G10 | Options are distinct by exact spelling (`_options` :802) but matched by `_norm_option` :1711. | `one of {Red, red}` passes `check` and accepts no answer. |
| G11 | `holds` is `query`: with variables it returns a List, not "there exists". | `if holds p(X) then` is a type error. |
| G12 | Facts may contain logic variables. | `fact p(X).` passes `check`; a later query fails with "value of unsupported kind LVar". |
| G13 | Bare lowercase names in facts and rule bodies are atoms unless bound. They are resolved at solve time through the rule's live `Env` (`KB._pat` :2915, `_ground` :2858). | `rule q(X) if p(X, bob)` gives `[alice]`. After `let bob = 3.` it still gives `[alice]` (cached). After an unrelated `fact` it gives `[]`. |
| G14 | A predicate named like a builtin is parsed as a comparison in a rule body. | `rule big(X) if count(X).` fails with "unsafe rule". |
| G15 | `NUM` has no size gate. | `check("let x = 1e10000000.")` takes 6.03 s (`1e1000000`: 0.15 s), inside the server-side check and preview handlers (integration/host/symblic_engine.py:607–610). |
| G16 | Identifiers use the running Python's Unicode classes, but the first word that classifies a line is ASCII only. | `π > 3.` is a prose ask. |
| G17 | [reading] `ensure c.` defaults to `else retry`. `assert c else warn` and `assert c else retry` parse but fail the run, because only `ensure` warns or retries (symblic/kernel/run.py:216, :349). | — |

## 4. Five highest-priority confirmed reproductions

### R1. Formal-looking lines become model calls [measured]

**Program**

```
let x = 4.
x = 4.
4 = x.
true.
not false.
all v in [1, 2]: v > 0.
lett y = 2.
```

**Observed.** Statement kinds `[(1,'let'), (2,'ask'), (3,'show'), (4,'ask'), (5,'ask'), (6,'ask'), (7,'ask')]`.
`check` returns ok with 5 asks and no warning.

**Cause.** A line is formal only if its first ASCII word is a keyword or its first character is in
`[0-9([{"'¬∀∃-]` (`split_statements` symblic/kernel/language.py:248, `_looks_formal` :267). Anything else becomes
`_prose` :981, an `ask stepN : Text`. So `x = 4.` and `4 = x.` mean different things, and a typo
(`lett`) costs a model call instead of a syntax error.

**Why it matters.** It breaks "the kernel decides everything formal".

### R2. `ensure … else retry` is not transactional and ignores KB data flow [measured]

(a) Take `examples/04-family-logic.sym`, change its `assert "gus" in descendants.` to
`ensure … else retry`, and use `effort=low`.
- **Observed:** the first answer has the typo `Guss`. The run fails after 1 model call. `_anchors` gives
  `{5: 4}`: the new ensure, statement 12, has no anchor.
- **Cause:** `_anchors` (symblic/kernel/run.py:244) follows only names through `free_names`. The data path
  `ask links → fact parent(...) → query ancestor(...)` passes through the KB, so the ensure degrades to an
  `assert`.

(b) When an anchor does exist, state from the rejected attempt survives. The program is
`ask e: Record {a: Text, b: Text}`, then `fact link(e.a, e.b)`, `show e`, and
`ensure e.b != "" and holds reach("s","t") else retry`, with replies `(s, m)` then `(m, t)`.
- **Observed:** status `done`; `e = {a: m, b: t}`; the KB holds **2** facts; the outputs are
  `[{a: s, b: m}, {a: m, b: t}]`.
- **Meaning:** the postcondition holds only because of the rejected answer's fact `link(s, m)`, and the
  rejected attempt's `show` stays in the outputs and in the run fingerprint.
- **Cause:** a retry pops only the bindings of statements `a..i-1` (`exec_block` symblic/kernel/run.py:232–234,
  `_binds` :940). The facts and rules in `KB`, `self.outputs`, `self.types`, `self.terms`, `self.groups`,
  `self.defaults` and `hidden`/`weight` flags are kept.

(c) Put `define Small as Int in 0..9.` between the ask and the ensure.
- **Observed:** the retry fails with "type Small is defined twice" (`exec_statement` :314–316).

The ensure-retry call-caching issue is a separate problem, and it is resolved in the current snapshot.

### R3. `ask … for each` builds capsules from shared instance state [measured]

**Setup.** Two `term` definitions and `ask d: Text "Describe {v}." for each v in ["apple", "pear"]`. To expose
an interleaving, the test process (not a core file) adds a 50 ms delay to `examples_for`.
This widens the race window; it does not control every scheduling decision.

**Observed.**

```
"Describe apple." DEFINITIONS: ['pear']
"Describe pear."  DEFINITIONS: ['pear']
```

**Cause.**
- `_ask_one` writes `self._defs`, `self._examples` (symblic/kernel/run.py:531–532) per item.
- Items run in a `ThreadPoolExecutor` (:493–494).
- `_round` reads the attributes later (:638–639).
- `self.feedback.pop(id(s))` (:534) gives retry feedback to whichever item's thread pops first.

**Why it matters.** A wrong definition is presented as "use exactly these meanings". The prompt, and so the
`call_key`, depends on thread scheduling, so a replay can miss the cache and re-ask.

### R4. Kernel results depend on the environment [measured]

| Program | Observed |
|---|---|
| `show replace({"x", "y", "z"}, " ", "").` | `PYTHONHASHSEED=1..5` gave five different outputs and five fingerprints, e.g. `fa8c594f7fcc7eb1` vs `4971a377e815f450`. `_b_replace` :2661 calls `str()` on a frozenset. So do `starts_with`/`ends_with` :2734–2735, `_b_contains` :2665 (`part`), `_b_words` :2671 and `_b_join` :2657 (`sep`). |
| `let x = 10 ^ 5000.` and `let x = 1e5000.` | `failed`: "internal error: ValueError: Exceeds the limit (4300 digits) for integer string conversion" on default CPython 3.11. `done` with `PYTHONINTMAXSTRDIGITS=0`. `fingerprint` :1493 calls `json.dumps(int)`. The documented `MAX_DIGITS = 20000` (:46) is unreachable by default [PY-INT]. |
| `show words("a\U0001E030b").` | Python 3.11.2 (UCD 14.0.0, category Cn): 2 items, `0473ef2dc0d324ab`. Python 3.12.14 (UCD 15.0.0, Lm): 1 item, `48c1afe011043e64` [PY-UCD]. |
| `eval(t)` with `t = 'matches("a…a!", "(a+)+$")'` | 0.02 / 0.06 / 0.25 s for n = 18 / 20 / 22, using 5 kernel steps each. Backtracking time grows exponentially with n [COX]. `key=eval(it)` passes model text to `_b_eval` :2685, which allows `_b_matches` :2705. |

The cluster-wide identity evidence remains valid for the programs it covered. The general claim needs the
conditions in §7, recommendation 3.

### R5. `check()` accepts programs that fail for static reasons [measured]

| Program | `check` | Run |
|---|---|---|
| `given c: Bool = false. if c then let x = 1. end. show x.` | ok, no warning | "x is not bound": `check` merges branch scopes as *may*-bound (symblic/kernel/language.py:3167–3176). |
| `rule r(Z) if p(X) and Z = Y * 2 and Y = X + 1.` | ok | "Y is not bound": safety (:1313) ignores the left-to-right order that `KB._solve_ordered` :2878 uses. |
| `fact p(X).` | ok | "value of unsupported kind LVar" (G12). |
| `for v in [1, -2, 3] do if v > 0 then let y = v * 10. end. end. show zip(xs, y).` | ok | `[[1, 10], [-2, 30]]`: lifting drops the iterations that did not bind (`Run._for` symblic/kernel/run.py:430), which silently misaligns the lists. |
| `ask c: one of {Red, red} …` | ok | every answer is rejected (G10). |
| `rule nat(N) if nat(M) and N = M + 1.` | ok | the step budget runs out after 1.35 s, so `holds nat(5)` is never answered. The rule is generative recursion. |

## 5. Other findings

### 5.1 Confirmed at the baseline, lower priority

| ID | Finding | Symbols |
|---|---|---|
| S-a | `"x" + " " = "x"` is true but the lengths differ. NFD `c` vs NFC `d`: both `c = d` and `c < d` are true. [measured] | `values_equal` :2014, `_cmp_order` :2022, `canon_text` :1480 |
| S-b | Bool and int collapse in sets and facts: `{1, true} = {true, 1}` is false, `len({1, true}) = 1`, and `{1} subset {true}` is true while `1 in {true}` is false. `holds p(true)` is true after `fact p(1)`. [measured] | `_hashable` :1869, `Kernel.eval` set :2064, `_as_set` :2224, `KB.add_fact` :2781, `_unify` :2929, `query` :2946 |
| S-c | `fact title("[1, 2]")` comes back from `query title(X)` as the list `[[1, 2]]`; `fact p([{a: 1}])` is an internal TypeError. [measured] | `_fact_key` :2765, `_unkey` :2975 |
| S-d | `Any` answers that agree by fingerprint bind the first applicator's raw value: `len` 3 vs 1, and the run fingerprints differ by applicator order. [measured] | `coerce` any :1724, `consensus` :3486 |
| S-e | A 1–1 tie reports agreement 0.5 and `contested` false, which `test_ties_are_deterministic` accepts. [measured] | `consensus` :3502 |
| S-f | Abstentions are ignored: 5 planned, 4 failed, `strict` gives `done` with agreement 1.0. [measured] | `_ask_one` symblic/kernel/run.py:570–572 |
| S-g | A field vote over `(1,5) (1,7) (2,6) (3,6)` gives `{x: 1, y: 6}`, which no sample gave, at agreement 0.5, uncontested. This is an intended feature (test at tests/kernel/test_symblic.py:583) but it needs a guard: propositionwise majority over interconnected fields can give an inconsistent whole [LP02]. [measured] | `consensus_fields` :3508, `by_fields` auto symblic/kernel/run.py:567 |
| S-h | `ahead` stops on vote counts while the vote ranks by weight. [reading] | symblic/kernel/run.py:553–556 |
| S-i | Blame goes to the nearest ask. `ensure a + b = 10` re-asks only `b`, and `a = 7` is accepted. `examples/06-small-model-council.sym` has the same shape: its second ensure retries only `apples_holds`. [measured] | `_anchors` :244 |
| S-j | Lenient numbers: `"1,5"` → 15, `"50%"` → 50, `"12 apples"` → 12. JSON `0.12345678901234567890123` → `0.12345678901234568` (read through a float). [measured] | `_NUM_IN_TEXT` :1717, `_coerce_num` :1814, `extract_json` :3402 |
| S-k | `"ab" * 2.5` = `"abab"`: the non-integer count is truncated silently. [measured] | `Kernel._bin` :2187–2192 |

### 5.2 Resolved in the coordinator's current snapshot

These were baseline issues; they are recorded here for traceability only.

| Finding | Baseline evidence | Status |
|---|---|---|
| Canonical tag collision: the record `{"#q": "1/2"}` had the fingerprint of the number 1/2. | [measured] `canon_json` was equal for both. | Fixed by the core operator; verified by the coordinator. |
| Conflicting record field aliases: case-variant keys were resolved silently, exact key first, otherwise the last case variant. | [reading] `coerce` record :1797–1803 | Fixed by the core operator; verified by the coordinator. Not re-tested in this worker checkout. |
| Ensure-retry call caching: with `retries=3` and replies 12, 12, the remaining attempts were served from the cache and the run failed. The key lacked the attempt number. | [measured] 2 real calls, 2 cached. | Fixed by the core operator; verified by the coordinator. |

## 6. Architecture proposal: kernel rules for the unresolved behaviours

Each rule is decided by code and testable by a unit test. All rules are [proposal].

| Rule | Normative statement | Enforcement point | Verification |
|---|---|---|---|
| K1 classification | A model is reached only by `ask` or by a line that does not parse as a formal statement; `check` lists every prose line. | `split_statements`, `_looks_formal`, `check` | R1 |
| K2 purity | A kernel result is a function of (program, inputs, accepted replies, KERNEL_ID): no `str()`/`repr()` of kernel values; integers are gated below the int↔str limit; no time-unbounded builtin is reachable from `eval`. | string builtins, `Kernel._big`, `parse_number_literal`, `_b_eval` | R4 under several seeds and environments |
| K3 identity | `a = b` ⇔ `canon(a) = canon(b)`, and every operation respects it: sets, facts, unification, `len`, ordering. | `values_equal`, `_hashable`, KB keys, text construction | S-a…S-d |
| K4 transaction | A retry restarts from its anchor in the state saved before the anchor ask. Anchors are the asks in the condition's backward slice, including KB provenance. No effect may sit inside a retry span. | `exec_block`, `_anchors`, `_binds`, `KB` | R2, S-i |
| K5 static soundness | `check` rejects any failure that is decidable from the text (§7, recommendation 5) and flags generative recursion. | `check`, `check_rule_safety`, `_options`, `Run._for` | R5 |
| K6 agreement | agreement = winner weight / planned weight; a tie is contested; an assembled record is contested unless a record invariant holds. | `consensus`, `consensus_fields`, `_ask_one` | S-e…S-h |
| K7 acceptance | `coerce` accepts only unambiguous numeric text; JSON numbers are read exactly. | `_NUM_IN_TEXT`, `_coerce_num`, `extract_json` | S-j |
| K8 provenance | Every run and every kernel-identity row records KERNEL_ID = (kernel source hash, Python version, `unicodedata.unidata_version`, `int_max_str_digits`); replay warns when it differs. | `Run.report` :898, `integration.host.symblic_engine` meta :215, `kernel-identity.json` | R4 |

**Operational rule for `ensure … else retry`.** σ = (bindings, KB, outputs, types/terms/groups/defaults, flags).

Current behaviour:

```
eval(c, σ) = false,  a = nearest ask j < i with binds(j) ∩ slice_names(c) ≠ ∅,  n < k
    ⟹  ⟨i, σ⟩ → ⟨a, σ with binds(a..i−1) removed⟩
```

Proposed behaviour:

```
entering ask a:  σ_a := snapshot(σ)
eval(c, σ) = false,  a ∈ anchors(i),  n < k   ⟹   ⟨i, σ⟩ → ⟨a, σ_a⟩     (feedback f; attempt n+1 in the call key)
anchors(i)     = asks in the backward slice of c, where:
                 • a fact statement carries the names it reads,
                 • a query reads the fact statements of its predicate's rule-dependency closure;
                 default: the latest such ask; `else retry a, b` overrides
delegate in a..i  ⟹  check-time error
```

This mirrors Eiffel's contract: a `retry` restarts the routine only after the `rescue` clause has brought the
object back to a state that satisfies its invariant [EIFFEL]. In Symblic, the snapshot plays the rescue
role, automatically. On success the kernel establishes only `τ(x) ∧ c` in the state built from the accepted
attempt. That is a runtime contract, not a proof about the instruction.

## 7. Five prioritized recommendations (implementable now)

### 1. Make retry transactional and data-flow anchored (K4)

**Change.**
- Replace the binding pop in `Run.exec_block` (symblic/kernel/run.py:216–237) with a snapshot taken when the anchor
  ask starts. The snapshot holds:
  - `dict(env.vars)` and each binding's `(hidden, weight)`;
  - `{p: set(ts) for p, ts in kb.facts.items()}`, `list(kb.rules)`;
  - `len(self.outputs)`, and copies of `types`, `terms`, `groups`, `defaults`.
- Extend `_anchors` (:244) with KB provenance:
  - a `fact` statement reads its free names; inside a `for`, that includes the loop source;
  - `query`/`holds` reads the fact statements of the predicates in its rule-dependency closure.
- Make a `delegate` between an anchor and its ensure a `check` error.
- Optional: add `ensure c else retry a, b`.
- Keep the coordinator's attempt-keyed calls.

**Accept when.**
- R2 (a) retries, using 2 calls, and passes.
- R2 (b) evaluates the ensure over 1 fact and leaves 1 output row.
- R2 (c) retries instead of failing with "defined twice".

### 2. Pass capsule inputs per item (prompt determinism under `for each`)

**Change.**
- In `Run._ask_one` (symblic/kernel/run.py:531–534), compute `defs`, `examples` and `feedback` as locals and pass
  them to `_round` (:632) as arguments. Remove `self._defs` and `self._examples`.
- For a `for each` ask, pop the retry feedback once in `ask()` (:474) before fanning out, and give it to
  every item.

**Accept when.**
- R3 shows each item its own definitions.
- Two fresh-process runs of the same program produce identical sets of `call_key`s.

### 3. Add a kernel purity gate and record KERNEL_ID (K2, K8)

**Change.**
- (a) The string builtins `_b_replace` :2661, `starts_with`/`ends_with` :2734–2735, `_b_contains` :2665,
  `_b_words` :2671 and `_b_join` :2657 require Text, or convert through `show()`, which sorts sets. They never
  call `str()` on a kernel value.
- (b) One integer gate:
  - apply `Kernel._big` :2219 to literals (`parse_number_literal` :841, before the `Fraction` is built), to
    `^`, and to `_b_factorial` :2549, `_b_choose` :2556 and every builtin that returns an int;
  - set `MAX_DIGITS` ≤ `sys.int_info.default_max_str_digits` (4300), so `fingerprint` never depends on
    `PYTHONINTMAXSTRDIGITS`.
- (c) `_b_eval` :2685 gets an allowlist without `matches`, `eval` and the renderers. `_b_matches` :2705
  either accepts a linear-time subset (Thompson-style [COX]) or refuses nested quantifiers and caps the input
  length.
- (d) Write KERNEL_ID into `meta.json` and the report (`Run.report` :898, which today records only `version`
  :912) and into every `kernel-identity.json` row.
- (e) For text: either reject code points that are unassigned (Cn) in UCD 14.0, the oldest Python on the
  fleet, or state identity per UCD version. NFC is stable only for assigned characters [UNICODE-STAB].

**Accept when.**
- The R4 programs give identical fingerprints for `PYTHONHASHSEED=0..4`.
- `10 ^ 5000` gives the same `SymblicError` whatever `PYTHONINTMAXSTRDIGITS` is.
- `check("let x = 1e10000000.")` fails in milliseconds.
- The published identity fingerprints `c2351a32c05cc58d` and `fff6d4efbecb4a3a` stay unchanged.

### 4. Make the formal/prose boundary explicit (K1)

**Change.**
- In `split_statements` (symblic/kernel/language.py:248), classify a line as formal when it tokenizes and parses as an
  expression (`Parser.expr` + `finish`) that contains an operator, literal or call. A single bare word stays
  prose.
- `check` (:3101):
  - errors on a first word within edit distance 1 of a keyword ("did you mean `let`?");
  - warns on every prose line: "line N is sent to a model as natural language";
  - errors when a prose line starts with a bound name.
- v1 prose sentences such as "Summarize the request." still fail `finish()` and stay prose
  (`test_v1_prose_program_runs`, example 08).

**Accept when.** In R1 only `lett y = 2.` is reported, as an error with a suggestion, and the other lines are
shows.

### 5. Make the static check sound (K5)

**Change.**
- (a) Definite assignment: after `if`, intersect the branch scopes, and treat a missing `else` as an empty
  branch (`check` :3167–3176). Reading a maybe-bound name is an error.
- (b) `check_rule_safety` :1313 simulates the `_solve_ordered` order: positive literals in order, then the
  rest in order. Every comparison's right-hand side must be bound when it is reached.
- (c) Facts must be ground (`parse_statement` fact :1109).
- (d) In `_options` :786, options must be distinct under `_norm_option`. Numeric and boolean options are
  refused, with a suggestion of `Int in a..b` or `Bool`.
- (e) A recursive rule whose head variable is bound by arithmetic is flagged "may not terminate".
- (f) `holds` returns a Bool, meaning "there exists" (`Parser.primary` :634, `KB.query` :2967).
- (g) `KB.add_rule` :2792 snapshots the atoms' values when the rule is added. Predicate names may not be
  builtin names.
- (h) `Run._for` :414 refuses to lift a name that is not bound in every iteration, or lifts `nothing`
  placeholders.

**Accept when.** Every R5 program is a `check` error, or has one documented deterministic result.

### Next, after the five

- **K3 identity:**
  - key sets and facts by `canon_json`;
  - apply NFC when text is created;
  - let `canon_text` keep outer whitespace, while acceptance may still strip it;
  - tag fact values instead of re-parsing strings in `_unkey`.
- **K6 agreement:**
  - count abstentions against the planned weight;
  - treat a tie as contested;
  - flag a field-assembled record, and count it as contested under `strict` unless a record invariant
    holds;
  - make `ahead` use weights.
- **K7 acceptance:**
  - accept thousands separators only in the form `\d{1,3}(,\d{3})+`;
  - convert or refuse `%`;
  - refuse trailing words unless they are a declared unit;
  - parse JSON with `parse_float=Decimal`.

## 8. Claim wording these results support

- "Kernel statements give identical results for the same KERNEL_ID." Until recommendation 3 lands, add:
  "for programs that do not stringify sets, stay under 4300-digit integers, and use text assigned in UCD
  14.0."
- "A finished run replays exactly from its record when the KERNEL_ID matches." Until recommendation 2 lands,
  add: "and it uses no `for each` ask with terms or examples."
- "Passing checks establishes the stated postconditions under the declared semantics." Correctness
  additionally requires an adequate specification and truth oracle. Transactional retries are needed
  for postconditions over the accepted attempt: today rejected facts can satisfy a postcondition.
- "Agreement is reported over valid samples; ties are not resolved by agreement." This stays true until K6
  lands.

## 9. Sources

Primary sources only. Each one supports one recommendation.

- [W3C-EBNF] W3C, *Extensible Markup Language (XML) 1.0 (Fifth Edition)*, §6 Notation. The EBNF notation
  used in §3. https://www.w3.org/TR/xml/#sec-notation
- [PY-INT] Python 3.11 documentation, "Integer string conversion length limitation": "The default limit is
  4300 digits"; configurable with `PYTHONINTMAXSTRDIGITS`. Supports recommendation 3(b).
  https://docs.python.org/3.11/library/stdtypes.html#integer-string-conversion-length-limitation
- [PY-HASH] Python 3.11 data model, `object.__hash__`: str and bytes hashes are "salted with an unpredictable
  random value … Changing hash values affects the iteration order of sets." Supports recommendation 3(a).
  https://docs.python.org/3.11/reference/datamodel.html#object.__hash__
- [PY-UCD] Python `unicodedata`: 3.11 is "compiled from the UCD version 14.0.0", 3.12 from 15.0.0. Supports
  recommendation 3(e). https://docs.python.org/3.11/library/unicodedata.html ;
  https://docs.python.org/3.12/library/unicodedata.html
- [UNICODE-STAB] Unicode Character Encoding Stability Policies, Normalization Stability: a string "contains
  only characters from a given version" → normalized identically in later versions. Supports
  recommendation 3(e). https://www.unicode.org/policies/stability_policy.html
- [COX] R. Cox, "Regular Expression Matching Can Be Simple And Fast", January 2007. Backtracking can need
  exponential time; a Thompson NFA needs O(mn). Supports recommendation 3(c).
  https://swtch.com/~rsc/regexp/regexp1.html
- [EIFFEL] Eiffel documentation, "I2E: Exceptions": `rescue` brings the object to "a stable state (one
  satisfying the class invariant)"; `retry` restarts the routine "from the beginning". Supports
  recommendation 1. https://www.eiffel.org/doc/eiffel/I2E-_Exceptions
- [LP02] C. List, P. Pettit, "Aggregating Sets of Judgments: An Impossibility Result", *Economics and
  Philosophy* 18(1):89–110, 2002. https://doi.org/10.1017/S0266267102001098. Supports K6 (S-g).

## Appendix A. Reproduction script and output

Run it from the repository root on the baseline commit. For R4, also run it with `PYTHONHASHSEED=1..5`,
with `PYTHONINTMAXSTRDIGITS=0`, and under `uv run --offline --python 3.12 --no-project python …`.

```python
import os, resource, sys, threading, time
resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
sys.path.insert(0, os.getcwd())
import symblic as S, symblic.kernel.run as SR


class FakeApps:                                   # as in tests/kernel/test_symblic.py
    def __init__(self, answer):
        self.answer, self.reqs, self.lock = answer, [], threading.Lock()

    def call(self, req):
        with self.lock:
            self.reqs.append(req)
        return {'ok': True, 'json': self.answer(S.app_label(req['app']), req['prompt'], req), 'ms': 1}


def run(src, answer=lambda *a: {'answer': 'x'}, **opts):
    apps = FakeApps(answer)
    rep = SR.Run(src, {}, apps, {'by': 'fake:a', **opts}).execute()
    return rep, apps


def outs(rep):
    return [o.get('value') for o in rep['outputs']]


def err(rep):
    return (rep['error'] or {}).get('message')


print('R1 formal-looking lines become prose asks')
src = 'let x = 4.\nx = 4.\n4 = x.\ntrue.\nnot false.\nall v in [1, 2]: v > 0.\nlett y = 2.\n'
print('  ', [(s.line, s.k) for s in S.parse(src)['statements']], '| check:', S.check(src)['ok'], S.check(src)['asks'])

print('R2 ensure ... else retry is not transactional')
ex = (open('04-family-logic.sym').read()
      .replace('assert "gus" in descendants.', 'ensure "gus" in descendants else retry.')
      .replace('with effort=high', 'with effort=low'))
good = [{'parent': p, 'child': c} for p, c in
        (('Ada', 'Ben'), ('Ben', 'Cleo'), ('Ben', 'Dov'), ('Cleo', 'Eli'), ('Dov', 'Fay'), ('Fay', 'Gus'))]
seq = iter([good[:5] + [{'parent': 'Fay', 'child': 'Guss'}], good])
rep, apps = run(ex, lambda *a: {'answer': next(seq)})
print('  (a)', rep['status'], '| model calls:', len(apps.reqs), '|', err(rep),
      '| anchors:', SR.Run(ex)._anchors(S.parse(ex)['statements']))
src = ('rule reach(X, Y) if link(X, Y).\nrule reach(X, Z) if link(X, Y) and reach(Y, Z).\n'
       'ask e: Record {a: Text, b: Text} "Give one link." with effort=low\n'
       'fact link(e.a, e.b).\nshow e.\nensure e.b != "" and holds reach("s", "t") else retry.\n')
seq = iter([{'a': 's', 'b': 'm'}, {'a': 'm', 'b': 't'}])
rep, _ = run(src, lambda *a: {'answer': next(seq)})
print('  (b)', rep['status'], '| e =', [b['value'] for b in rep['bindings'] if b['name'] == 'e'], '| facts:',
      rep['facts'], '| outputs:', outs(rep))
seq = iter([12, 3])
rep, _ = run('ask n: Int "Pick." with effort=low\ndefine Small as Int in 0..9.\nensure n < 10 else retry.\n',
             lambda *a: {'answer': next(seq)})
print('  (c)', rep['status'], '|', err(rep))

print('R3 for-each capsules share instance state')
orig = SR.Run.examples_for
SR.Run.examples_for = lambda self, s, ty, env: (time.sleep(0.05), orig(self, s, ty, env))[1]   # widen the window
rep, apps = run('term apple means "a pome fruit".\nterm pear means "a different pome fruit".\n'
                'ask d: Text "Describe {v}." for each v in ["apple", "pear"] with effort=low\n',
                lambda *a: {'answer': 'ok'}, parallel=4)
SR.Run.examples_for = orig
for req in apps.reqs:
    stmt = req['prompt'].split('STATEMENT:')[1].split('\n')[2].strip()
    print('  ', stmt, 'DEFINITIONS:', [ln.split('"')[1] for ln in req['prompt'].splitlines() if ln.startswith('- "')])

print('R4 environment-dependent kernel results')
rep, _ = run('show replace({"x", "y", "z"}, " ", "").\n')
print(f'   PYTHONHASHSEED={os.environ.get("PYTHONHASHSEED", "random")}:', outs(rep), rep['outputs'][0]['hash'])
for src in ('let x = 10 ^ 5000.\n', 'let x = 1e5000.\n'):
    rep, _ = run(src)
    print(f'   {src.strip()} -> {rep["status"]} {(err(rep) or "")[:72]} (int_max_str_digits={sys.get_int_max_str_digits()})')
import unicodedata
rep, _ = run('show words("a\U0001E030b").\n')
print(f'   Python {sys.version.split()[0]} UCD {unicodedata.unidata_version}: words -> {len(outs(rep)[0])} item(s),',
      rep['outputs'][0]['hash'])

print('R5 check accepts programs that fail for static reasons')
for src in ('given c: Bool = false.\nif c then\n  let x = 1.\nend.\nshow x.\n',
            'fact p(1).\nrule r(Z) if p(X) and Z = Y * 2 and Y = X + 1.\nshow query r(Z).\n',
            'fact p(X).\nshow query p(Y).\n',
            'let xs = [1, -2, 3].\nfor v in xs do\n  if v > 0 then\n    let y = v * 10.\n  end.\nend.\nshow zip(xs, y).\n'):
    rep, _ = run(src)
    print('   check ok:', S.check(src)['ok'], '| run:', rep['status'], outs(rep) or err(rep))
ty = S.parse('ask c: one of {Red, red} "Pick."\n')['statements'][0].type
for v in ('red', 'Red'):
    try:
        S.coerce(v, ty)
    except S.SymblicError as e:
        print('   one of {Red, red}: check ok:', S.check('ask c: one of {Red, red} "Pick."\n')['ok'], '|', e.message)
```

**Output** with `PYTHONHASHSEED=1` on Python 3.11.2. The other lines are from the reruns named above.

```
R1 formal-looking lines become prose asks
   [(1, 'let'), (2, 'ask'), (3, 'show'), (4, 'ask'), (5, 'ask'), (6, 'ask'), (7, 'ask')] | check: True 5
R2 ensure ... else retry is not transactional
  (a) failed | model calls: 1 | ensure failed: "gus" in descendants | anchors: {5: 4}
  (b) done | e = [{'a': 'm', 'b': 't'}] | facts: 2 | outputs: [{'a': 's', 'b': 'm'}, {'a': 'm', 'b': 't'}]
  (c) failed | type Small is defined twice
R3 for-each capsules share instance state
   "Describe apple." DEFINITIONS: ['pear']
   "Describe pear." DEFINITIONS: ['pear']
R4 environment-dependent kernel results
   PYTHONHASHSEED=1: ["frozenset({'x','z','y'})"] fa8c594f7fcc7eb1
   let x = 10 ^ 5000. -> failed internal error: ValueError: Exceeds the limit (4300 digits) for integer  (int_max_str_digits=4300)
   let x = 1e5000. -> failed internal error: ValueError: Exceeds the limit (4300 digits) for integer  (int_max_str_digits=4300)
   Python 3.11.2 UCD 14.0.0: words -> 2 item(s), 0473ef2dc0d324ab
R5 check accepts programs that fail for static reasons
   check ok: True | run: failed x is not bound (define it with let, given or ask before using it)
   check ok: True | run: failed Y is not bound (define it with let, given or ask before using it)
   check ok: True | run: failed value of unsupported kind LVar
   check ok: True | run: done [[[1, 10], [-2, 30]]]
   one of {Red, red}: check ok: True | answer must be exactly one of Red, red; got "red"
   one of {Red, red}: check ok: True | answer must be exactly one of Red, red; got "Red"
# PYTHONHASHSEED=2, PYTHONINTMAXSTRDIGITS=0:
   PYTHONHASHSEED=2: ["frozenset({'y','z','x'})"] 4971a377e815f450
   let x = 10 ^ 5000. -> done  (int_max_str_digits=0)
   let x = 1e5000. -> done  (int_max_str_digits=0)
# uv run --offline --python 3.12:
   Python 3.12.14 UCD 15.0.0: words -> 1 item(s), 48c1afe011043e64
```

## Appendix B. Scope and checks

- Read in full or in the relevant parts:
  - `CLAUDE.md`;
  - the `/automation-studio` and Symblic contract (docs/agents/CONTRACTS.md:801–833);
  - `docs/reference/SPEC.md`, `PRIOR-ART.md`, `RESULTS.md`;
  - `symblic/kernel/language.py` (parser, types, kernel, KB, check, capsule, consensus);
  - `symblic/kernel/run.py` (interpreter, ensure/retry, ask/consensus, replay key);
  - the check and preview handlers in `integration/host/symblic_engine.py`;
  - examples 04 and 06;
  - `tests/kernel/test_symblic.py` (names and the relevant tests).
- Not done:
  - no core file, test, UI or API was edited;
  - no applicator, model, benchmark, service or power setting was touched;
  - no private run data was read.
- Checks:
  - `bin/devcheck`: OK, 0 blocking. shellcheck and gitleaks are absent on the node, so those checks were
    skipped.
  - `bin/devtest tests/kernel/test_symblic.py`: 61 passed at the baseline.
  - The reproductions ran in one process at a time under `nice`, `timeout` and CPU/memory rlimits.

## Coordinator verification after integration

The coordinator independently ran Appendix A against a fresh immutable core
snapshot (with two fake item threads rather than four):
- `symblic/kernel/language.py` SHA-256: `6864a1bbeaefd8c5a56f896fa584cf84de8f7125880a5267769773939cd9587f`
- `symblic/kernel/run.py` SHA-256: `036cba552e431b7155521689e7ca82b1f74392464e51a3a3b7bb1373429769dc`

The KB anchor gap, retained rejected facts/outputs, repeated type-definition
failure, and wrong per-item definitions reproduced. The first-word prose
classification and the four shown static-check cases also reproduced. Set
stringification matched the baseline's hash-seed-1 result; the two 5000-digit
integer cases failed at the configured conversion limit. The root's Python
3.12.3/UCD 15.0.0 produced one word in the Unicode fixture, matching the
worker's Python 3.12 result. This single root run does not independently repeat
the worker's five-seed or cross-UCD study.

The exact reproduction results and snapshot identities were sent to both core
operators. Findings here are bounded to the named snapshots; concurrent later
changes require rechecking. The grammar is an implementation-derived draft
for the baseline, rather than a normative grammar for subsequent extensions.
