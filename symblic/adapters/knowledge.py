"""Exact knowledge on a finite set of possible states: Aumann's partition model and the announcement process.

States are the integers 1..n (n <= MAX_STATES). An agent's information is a PARTITION of the states: a list of
cells, each a list or set of states, covering every state exactly once. An EVENT is a list or set of states. At
a state w an agent KNOWS an event when the agent's cell containing w lies inside the event (Aumann 1976).

Builtins (kernel convention fn(kernel, node, *args); the kernel step budget is charged before the work):
- knows_event(partition, event, state) -> Bool.
- common_partition(partitions) -> the meet of 1..MAX_AGENTS partitions: the finest partition that every given
  partition refines. Two states share a cell when a chain of states links them, each consecutive pair sharing a
  cell in some agent's partition. A list of cells, each sorted, cells ordered by their smallest state.
- common_knowledge(partitions, event, state) -> Bool: the cell of the meet containing the state lies inside the
  event (Aumann's characterisation of common knowledge).
- posterior_given(prior, cell, event) -> the exact conditional probability of the event given the cell. The
  prior is a list of n non-negative rationals with a positive sum (n is its length); it is normalised.
- agreement_process(priors, partitions, event, state) -> the process of Geanakoplos and Polemarchakis (1982).
  `priors` is one prior (common to every agent) or a list of m priors, one per agent. Agents 1..m speak in turn,
  agent 1 first. A public set W of states starts as all n states; an agent's current cells are its cells
  intersected with W. The speaker announces its posterior of the event given its current cell at the true
  state. The listeners learn that the true state lies in the union of the speaker's current cells that give
  the announced number, so every state of W whose speaker cell gives a different number leaves W, and every
  agent's information is intersected with the new W. The speaker learns nothing from its own announcement.
  The process stops when m consecutive announcements remove no state: it has converged. It always converges
  within n*m announcements (at most MAX_STATES * MAX_AGENTS = 512); see _announcement_bound for the argument.
  Reaching that bound without convergence would be an internal defect: the call then raises a SymblicError
  (kind runtime) and returns no partial result. Result record:
    posteriors        each agent's posterior given its final information, agent 1 first (a list of m numbers);
                      after convergence it is also the agent's last announcement;
    agreed            Bool: all of `posteriors` are equal;
    announcements     how many announcements were made (the full count, 1..n*m);
    history           the first MAX_HISTORY announced numbers in order (announcement k is made by agent
                      ((k - 1) mod m) + 1);
    history_truncated Bool: more than MAX_HISTORY announcements were made;
    common_prior      Bool: every agent's normalised prior is the same distribution (true for one prior);
    converged         Bool: the stopping rule ended the process (true in every returned record).
  With a common prior the converged posteriors are equal (the theorem); with different priors they need not be.

Lists in results are tuples, numbers are int or Fraction normalised with S.norm_num, results pass S.canon.
Lists of states may come in any order; a list that names a state twice is refused. Sets are read in increasing
order, so every refusal and result is the same on every machine.

Refusals raise KnowledgeError (a SymblicError):
- kind type: a value of the wrong kind (not a list or set, a state that is not a whole number, a float, a bool,
  text, a non-canonical Fraction, priors that mix numbers and lists);
- kind check: values that do not form the model (a state in two cells or listed twice, a state in no cell, an
  empty cell, a state outside 1..n, no partitions, an empty prior, a negative prior entry, a prior summing to
  zero, a cell of zero prior weight, a number of priors or prior entries that does not match, partitions of
  different state sets, and in agreement_process a current cell of zero weight under the speaker's prior, whose
  posterior is undefined);
- kind budget: a hard limit (more than MAX_STATES states, more than MAX_AGENTS partitions, a prior entry, its
  common denominator or a weight after clearing denominators above MAX_BITS bits).
An exhausted kernel step budget raises the kernel's own SymblicError. A plain SymblicError of kind runtime from
agreement_process means an internal defect (the process did not stop within its proven bound).

This computes on the finite model that the program writes down. It does not say what a person or a language
model knows, a transcript is not a partition, and agreement needs the common prior that is passed in.
Pure: no I/O, no model, nothing runs on import.

Depends on: symblic.kernel.language. Used by: the knows_event, common_partition, common_knowledge,
posterior_given and agreement_process builtins (symblic.kernel.language.ADAPTERS). See docs/reference/KNOWLEDGE.md.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction
from math import gcd

from symblic.kernel import language as S

VERSION = 1
MAX_STATES = 64
MAX_AGENTS = 8
MAX_HISTORY = 64                                 # announced numbers kept in a result's history
MAX_ANNOUNCEMENTS = MAX_STATES * MAX_AGENTS      # 512: the largest n*m, so no admissible process is longer
MAX_BITS = 4096


class KnowledgeError(S.SymblicError):
    """An invalid finite knowledge model or an exhausted deterministic limit."""


def _ticker(budget, node):
    if budget is None:
        return lambda units: None
    if not isinstance(budget, S.Budget):
        raise KnowledgeError('budget must be a Symblic Budget', kind='type')
    return lambda units: budget.tick(units, node)


def _whole(value):
    """The integer a whole kernel number stands for; None for anything else (bool, float, text, 3/2 ...)."""
    if type(value) is int:
        return value
    if (type(value) is Fraction and type(value.numerator) is int and type(value.denominator) is int
            and value.denominator == 1):
        return value.numerator
    return None


def _text(number):
    return str(number) if -10 ** 9 <= number <= 10 ** 9 else 'a very large number'


def _describe(value):
    """A refused entry, safely: its kind, and its value only when that is a short scalar (no deep rendering)."""
    name = S.type_name(value)
    if isinstance(value, bool):
        return f'{name} {"true" if value else "false"}'
    if type(value) is float:
        return f'{name} {value!r}'
    if (type(value) is Fraction and type(value.numerator) is int and type(value.denominator) is int
            and abs(value.numerator) < 10 ** 9 and value.denominator < 10 ** 9):
        return f'{name} {value.numerator}/{value.denominator}'
    if type(value) is str and len(value) <= 20:
        return f'{name} {value!r}'
    return name


def _members(value, label, tick):
    """The entries of a list or set as integers: a list in its own order, a set in increasing order."""
    if type(value) in (list, tuple):
        is_set = False
    elif isinstance(value, frozenset):          # S.ValueSet included
        is_set = True
    else:
        raise KnowledgeError(f'{label} must be a list or set of states, not {S.type_name(value)}', kind='type')
    if len(value) > MAX_STATES:
        raise KnowledgeError(f'{label} has {len(value)} entries; at most {MAX_STATES} states are supported',
                             kind='budget')
    tick(1 + len(value))
    entries = list(value)
    states = [_whole(entry) for entry in entries]
    if None in states:
        if is_set:                              # a set has no order: name the kinds, not one member
            kinds = ', '.join(sorted({S.type_name(e) for e, s in zip(entries, states) if s is None}))
            raise KnowledgeError(f'{label} must contain whole-number states, not {kinds}', kind='type')
        entry = entries[states.index(None)]
        raise KnowledgeError(f'{label} contains {_describe(entry)}; a state is a whole number', kind='type')
    return sorted(states) if is_set else states


def _state_set(value, n, label, tick):
    """An event or a cell over the states 1..n, as a frozenset."""
    seen = set()
    for state in _members(value, label, tick):
        if not 1 <= state <= n:
            raise KnowledgeError(f'{label} names state {_text(state)}, outside the states 1..{n}', kind='check')
        if state in seen:
            raise KnowledgeError(f'{label} lists state {state} twice', kind='check')
        seen.add(state)
    return frozenset(seen)


def _state(value, n):
    state = _whole(value)
    if state is None:
        raise KnowledgeError(f'the state must be a whole number, not {S.type_name(value)}', kind='type')
    if not 1 <= state <= n:
        raise KnowledgeError(f'the state {_text(state)} is outside the states 1..{n}', kind='check')
    return state


def _partition(value, label, tick):
    """Validated cells (sorted tuples, ordered by smallest state) and n, the number of states covered."""
    if type(value) not in (list, tuple):
        raise KnowledgeError(f'{label} must be a list of cells, not {S.type_name(value)}', kind='type')
    if not value:
        raise KnowledgeError(f'{label} has no cells', kind='check')
    if len(value) > MAX_STATES:
        raise KnowledgeError(f'{label} has {len(value)} cells; at most {MAX_STATES} states are supported',
                             kind='budget')
    tick(1 + len(value))
    cells, seen = [], set()
    for number, cell in enumerate(value, 1):
        states = _members(cell, f'{label}, cell {number},', tick)
        if not states:
            raise KnowledgeError(f'{label} has an empty cell (cell {number})', kind='check')
        for state in states:
            if state < 1:
                raise KnowledgeError(f'{label} names state {_text(state)}; states are numbered from 1',
                                     kind='check')
            if state > MAX_STATES:
                raise KnowledgeError(f'{label} names state {_text(state)}; at most {MAX_STATES} states are '
                                     'supported', kind='budget')
            if state in seen:
                raise KnowledgeError(f'state {state} appears twice in {label}', kind='check')
            seen.add(state)
        cells.append(tuple(sorted(states)))
    n = max(seen)
    if len(seen) != n:
        missing = min(set(range(1, n + 1)) - seen)
        raise KnowledgeError(f'{label} has no cell for state {missing}', kind='check')
    return tuple(sorted(cells)), n


def _partitions(value, tick):
    if type(value) not in (list, tuple):
        raise KnowledgeError(f'the partitions must be a list of partitions, not {S.type_name(value)}', kind='type')
    if not value:
        raise KnowledgeError('the list of partitions is empty', kind='check')
    if len(value) > MAX_AGENTS:
        raise KnowledgeError(f'{len(value)} partitions; at most {MAX_AGENTS} agents are supported', kind='budget')
    validated, n = [], None
    for number, item in enumerate(value, 1):
        cells, size = _partition(item, f'partition {number}', tick)
        if n is None:
            n = size
        elif size != n:
            raise KnowledgeError(f'partition {number} covers the states 1..{size} but partition 1 covers 1..{n}',
                                 kind='check')
        validated.append(cells)
    return tuple(validated), n


def _owner(cells, n):
    """owner[w] is the index of the cell that holds state w."""
    owner = [0] * (n + 1)
    for index, cell in enumerate(cells):
        for state in cell:
            owner[state] = index
    return owner


def _meet(partitions, n, tick):
    """Connected components of 'shares a cell in some partition'; each root is its component's smallest state."""
    tick(n * (len(partitions) + 1))
    root = list(range(n + 1))

    def find(state):
        while root[state] != state:
            root[state] = root[root[state]]
            state = root[state]
        return state

    for cells in partitions:
        for cell in cells:
            first = find(cell[0])
            for state in cell[1:]:
                other = find(state)
                if other != first:
                    low, high = min(first, other), max(first, other)
                    root[high] = low
                    first = low
    groups = {}
    for state in range(1, n + 1):
        groups.setdefault(find(state), []).append(state)
    return tuple(tuple(groups[key]) for key in sorted(groups))


def _rational(value, label):
    """(numerator, denominator) of an exact kernel number; refuses bool, float, Decimal, text, odd Fractions."""
    if type(value) is int:
        numerator, denominator = value, 1
    elif type(value) is Fraction:
        numerator, denominator = value.numerator, value.denominator
        if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
            raise KnowledgeError(f'{label} is not a canonical rational', kind='type')
    else:
        raise KnowledgeError(f'{label} must be an exact number, not {S.type_name(value)}', kind='type')
    if numerator.bit_length() > MAX_BITS or denominator.bit_length() > MAX_BITS:
        raise KnowledgeError(f'{label} has more than {MAX_BITS} bits', kind='budget')
    if gcd(numerator, denominator) != 1:
        raise KnowledgeError(f'{label} is not a canonical rational', kind='type')
    return numerator, denominator


def _prior(value, label, tick, size=None):
    """Integer weights proportional to the prior (denominators cleared exactly); each at most MAX_BITS bits."""
    if type(value) not in (list, tuple):
        raise KnowledgeError(f'{label} must be a list of numbers, not {S.type_name(value)}', kind='type')
    if not value:
        raise KnowledgeError(f'{label} is empty', kind='check')
    if len(value) > MAX_STATES:
        raise KnowledgeError(f'{label} has {len(value)} entries; at most {MAX_STATES} states are supported',
                             kind='budget')
    if size is not None and len(value) != size:
        raise KnowledgeError(f'{label} has {len(value)} entries but the partitions cover {size} states',
                             kind='check')
    tick(1 + 3 * len(value))
    pairs = []
    for index, entry in enumerate(value, 1):
        numerator, denominator = _rational(entry, f'{label}, entry {index},')
        if numerator < 0:
            raise KnowledgeError(f'{label}, entry {index}, is negative', kind='check')
        pairs.append((numerator, denominator))
    common = 1
    for _, denominator in pairs:
        common = common // gcd(common, denominator) * denominator
        if common.bit_length() > MAX_BITS:
            raise KnowledgeError(f'the common denominator of {label} has more than {MAX_BITS} bits', kind='budget')
    weights = tuple(numerator * (common // denominator) for numerator, denominator in pairs)
    if any(weight.bit_length() > MAX_BITS for weight in weights):
        raise KnowledgeError(f'{label} needs more than {MAX_BITS} bits once its denominators are cleared',
                             kind='budget')
    if not any(weights):
        raise KnowledgeError(f'{label} sums to zero', kind='check')
    return weights


def _priors(value, n, m, tick):
    """One weight tuple per agent, and whether all agents share one normalised prior."""
    if type(value) not in (list, tuple):
        raise KnowledgeError(f'priors must be a list, not {S.type_name(value)}', kind='type')
    if not value:
        raise KnowledgeError('priors is empty', kind='check')
    if len(value) > MAX_STATES:
        raise KnowledgeError(f'priors has {len(value)} entries; at most {MAX_STATES} states are supported',
                             kind='budget')
    nested = {type(item) in (list, tuple) for item in value}
    if nested == {False}:
        weights = (_prior(value, 'the prior', tick, n),) * m
    elif nested == {True}:
        if len(value) != m:
            raise KnowledgeError(f'there are {len(value)} priors for {m} agents', kind='check')
        weights = tuple(_prior(item, f'prior {k}', tick, n) for k, item in enumerate(value, 1))
    else:
        raise KnowledgeError('priors must be one prior (a list of numbers) or one list of numbers per agent',
                             kind='type')
    tick(1 + m * n)
    first, first_total = weights[0], sum(weights[0])
    common = all(other[i] * first_total == first[i] * total
                 for other, total in ((w, sum(w)) for w in weights[1:]) for i in range(n))
    return weights, common


def knows_event(partition, event, state, *, budget=None, node=None):
    """True when the agent's cell containing `state` lies inside `event`."""
    tick = _ticker(budget, node)
    cells, n = _partition(partition, 'the partition', tick)
    target = _state_set(event, n, 'the event', tick)
    where = _state(state, n)
    tick(1 + n)
    cell = next(c for c in cells if where in c)
    return all(s in target for s in cell)


def common_partition(partitions, *, budget=None, node=None):
    """The meet: the finest partition that every given partition refines."""
    tick = _ticker(budget, node)
    validated, n = _partitions(partitions, tick)
    return _meet(validated, n, tick)


def common_knowledge(partitions, event, state, *, budget=None, node=None):
    """True when the meet cell containing `state` lies inside `event`."""
    tick = _ticker(budget, node)
    validated, n = _partitions(partitions, tick)
    target = _state_set(event, n, 'the event', tick)
    where = _state(state, n)
    meet = _meet(validated, n, tick)
    tick(1 + n)
    cell = next(c for c in meet if where in c)
    return all(s in target for s in cell)


def posterior_given(prior, cell, event, *, budget=None, node=None):
    """P(event | cell) under the normalised prior, exactly; a cell of zero prior weight is refused."""
    tick = _ticker(budget, node)
    weights = _prior(prior, 'the prior', tick)
    n = len(weights)
    given = _state_set(cell, n, 'the cell', tick)
    target = _state_set(event, n, 'the event', tick)
    tick(1 + len(given))
    total = sum(weights[s - 1] for s in given)
    if not total:
        raise KnowledgeError('the cell has zero prior weight, so the conditional probability is undefined',
                             kind='check')
    return S.norm_num(Fraction(sum(weights[s - 1] for s in given if s in target), total))


def _announcement_bound(n, m):
    """The process stops within n*m announcements.

    W, the states consistent with every announcement so far, always holds the true state, and at any w in W the
    same announcements would have been made, so agent i's information at w is its cell at w intersected with W.
    An informative announcement removes at least one state from W, so there are at most n - 1 of them. Before
    each informative announcement there are at most m - 1 uninformative ones (m in a row stop the process), and
    the process ends with exactly m. So there are at most (n - 1) * m + m = n * m announcements."""
    return n * m


def _defect(message):
    return S.SymblicError(f'agreement_process: {message}; this is an internal defect, not a property of the model',
                          kind='runtime')


def agreement_process(priors, partitions, event, state, *, budget=None, node=None):
    """Announce posteriors in turn until m consecutive announcements remove no state (at most n*m of them)."""
    tick = _ticker(budget, node)
    validated, n = _partitions(partitions, tick)
    m = len(validated)
    weights, common = _priors(priors, n, m, tick)
    target = _state_set(event, n, 'the event', tick)
    truth = _state(state, n)
    tick(m * (n + 1))
    owners = [_owner(cells, n) for cells in validated]
    alive = tuple(range(1, n + 1))                      # the public set W, in increasing order
    history, last, quiet = [], [None] * m, 0
    bound = _announcement_bound(n, m)
    for turn in range(bound):
        tick(2 * len(alive) + 1)
        speaker = turn % m
        owner, prior = owners[speaker], weights[speaker]
        sums = {}                                       # current cell (by original cell index) -> (hit, total)
        for s in alive:
            hit, total = sums.get(owner[s], (0, 0))
            if s in target:
                hit += prior[s - 1]
            sums[owner[s]] = (hit, total + prior[s - 1])
        for key, (_, total) in sums.items():            # in order of each current cell's smallest state
            if not total:
                cell = [s for s in alive if owner[s] == key]
                raise KnowledgeError(f'at announcement {turn + 1}, agent {speaker + 1} gives zero prior weight to '
                                     f'its current cell {cell}, so its posterior there is undefined', kind='check')
        said_hit, said_total = sums[owner[truth]]
        same = {key: hit * said_total == said_hit * total for key, (hit, total) in sums.items()}
        value = S.norm_num(Fraction(said_hit, said_total))
        if len(history) < MAX_HISTORY:
            history.append(value)
        last[speaker] = value
        keep = tuple(s for s in alive if same[owner[s]])
        if len(keep) == len(alive):
            quiet += 1
            if quiet == m:                              # the stopping rule: m consecutive uninformative
                break
        else:
            quiet, alive = 0, keep
    else:
        raise _defect(f'no convergence within the proven bound of {bound} announcements')
    # Every agent spoke in the last m announcements with the final W, so its current posterior is its last
    # announcement; recompute it from W as an independent check.
    tick(m * (len(alive) + 1))
    posteriors = []
    for owner, prior in zip(owners, weights):
        cell = [s for s in alive if owner[s] == owner[truth]]
        total = sum(prior[s - 1] for s in cell)
        if not total:
            raise _defect('an agent ended with a cell of zero weight')
        posteriors.append(S.norm_num(Fraction(sum(prior[s - 1] for s in cell if s in target), total)))
    if posteriors != last:
        raise _defect('the final posteriors differ from the last announcements')
    posteriors = tuple(posteriors)
    return {'posteriors': posteriors, 'agreed': all(p == posteriors[0] for p in posteriors),
            'announcements': turn + 1, 'history': tuple(history), 'history_truncated': turn + 1 > MAX_HISTORY,
            'common_prior': common, 'converged': True}


def _knows_event(kernel, node, partition, event, state):
    return knows_event(partition, event, state, budget=kernel.budget, node=node)


def _common_partition(kernel, node, partitions):
    return common_partition(partitions, budget=kernel.budget, node=node)


def _common_knowledge(kernel, node, partitions, event, state):
    return common_knowledge(partitions, event, state, budget=kernel.budget, node=node)


def _posterior_given(kernel, node, prior, cell, event):
    return posterior_given(prior, cell, event, budget=kernel.budget, node=node)


def _agreement_process(kernel, node, priors, partitions, event, state):
    return agreement_process(priors, partitions, event, state, budget=kernel.budget, node=node)


FUNCTIONS = {'knows_event': _knows_event, 'common_partition': _common_partition,
             'common_knowledge': _common_knowledge, 'posterior_given': _posterior_given,
             'agreement_process': _agreement_process}
