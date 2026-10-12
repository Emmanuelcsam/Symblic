# Exact quantities and measurement intervals

`symblic/adapters/quantities.py` adds dimension-safe quantities to Symblic without changing
ordinary `Number` semantics. It is an additive, pure adapter. A quantity retains
its declared unit, exact rational bounds, measurement provenance, tolerance
declarations, and temporal validity. Its result is an enclosure conditional on
those declarations; it does not certify a sensor, discover units, estimate a
probability distribution, or convert agreement into knowledge.

The implementation is adapter version 1, schema
`symblic.quantity.v1`. It imports `symblic` and the existing bounded rational
arithmetic helper in `symblic.adapters.variational` but invokes no quadratic solver.
Import starts no worker, opens no store, reads no clock, and registers no global
function. The existing `symblic/lang/library/units.sym` remains supported without changes.

## Existing-language interface

All functions accept native Symblic values and return native records. The core
registers lazy wrappers in its fixed first-party adapter table, so ordinary
programs can call these functions directly in both legacy and verified profiles.
Host code can also call `register(kernel)` to attach them to one kernel. Kernel
identity and execution pins include this adapter and its rational arithmetic
dependency. This adapter is included in live RC2. Its contracts remain conditional on the caller's
declarations and the release checks do not establish measurement truth or model reliability.

| Function | Meaning |
| --- | --- |
| `quantity_exact(value, unit, metadata={})` | Declare an exact definition, with equal bounds |
| `quantity_interval(lower, upper, unit, metadata={})` | Declare a closed measured interval |
| `quantity_measure(value, tolerance, unit, metadata={})` | Declare the interval `value ± tolerance`, with absolute tolerance in that unit |
| `quantity_unit(symbol, dimensions, scale=1, offset=0, kind="linear", definition="...")` | Declare an exact positive-scale map into SI coordinates |
| `quantity_convert(q, unit)` | Convert the enclosure without rounding |
| `quantity_add(a, b)`, `quantity_sub(a, b)` | Dimension-checked interval addition/subtraction |
| `quantity_mul(a, b)`, `quantity_div(a, b)` | Compose dimensions and enclose products/quotients |
| `quantity_compare(a, b, relation="lt")` | Return `true`, `false`, or `indeterminate` under all enclosed value pairs |
| `quantity_status(q, evaluated_at, max_age_seconds=...)` | Evaluate declared validity and optional observation age using caller-supplied time |

```symblic
let measured_length = quantity_measure(1.2, 0.05, "m").
let centimeters = quantity_convert(measured_length, "cm").
assert centimeters.lower = 115 and centimeters.upper = 125.

let threshold = quantity_exact(1.2, "m").
let comparison = quantity_compare(measured_length, threshold, "lt").
assert comparison.outcome = "indeterminate".

let duration = quantity_exact(10, "s").
let speed = quantity_div(measured_length, duration).
assert speed.lower = 0.115 and speed.upper = 0.125.
```

These are ordinary record-valued builtins, not a second language or parser.
Exact literals are integers or canonical rational numbers; integral rational
literals are accepted for dimension exponents and age limits. Python floats,
Decimals, strings, booleans and numeric subclasses are refused as quantities,
unit scales, interval bounds or tolerances. Native metadata booleans are not
silently converted to numbers either.

This is an explicit quantity API. Existing bare `Number` arithmetic and
`units.sym` conversion helpers retain their existing meaning; the verified
profile does not silently guess units or turn bare values into measurements.

## Dimensions and unit definitions

The dimension vector has exactly seven bounded integer exponents, in this order:
length, mass, time, current, temperature, amount of substance, luminous intensity.
The entries correspond to metres, kilograms, seconds, amperes, kelvin differences,
moles and candelas. Dimensional equality is necessary, not sufficient, for physical
meaning: equal dimensions do not prove that two quantities describe the same
phenomenon. The SI base quantities and units are conventional definitions.
[BIPM SI base units](https://www.bipm.org/en/measurement-units/si-base-units)

The explicit unit record has exactly `symbol`, `dimensions`, `scale`, `offset`,
`kind` and `definition`. Conversion is `SI = scale * value + offset`, where scale
must be positive. Linear units have zero offset. Catalogue symbols cannot be
redefined with different dimensions, scale, offset or kind. Unknown strings are
refused; the adapter never guesses that `ton`, `c`, or an unrecognized spelling
meant a particular unit.

The finite catalogue contains `1`, `m`, `cm`, `mm`, `km`, `inch`, `ft`, `kg`, `g`,
`mg`, `lb`, `s`, `min`, `h`, `A`, `mol`, `cd`, `K`, `degC`, `degF`, `delta_K`,
`delta_degC` and `delta_degF`. Factors are exact definitions, including the
international inch and pound. Other units can be declared explicitly. Generated
product/quotient units use a canonical SI dimension vector, so no preferred
physical interpretation is invented. [NIST conversion factors](https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8)

## Absolute temperature and differences

`K`, `degC`, and `degF` describe temperature points. `delta_K`, `delta_degC`, and
`delta_degF` describe temperature differences. Celsius and kelvin points differ
by exactly 273.15; a Fahrenheit difference is exactly 5/9 of a kelvin difference.
[NIST exact temperature conversion](https://www.nist.gov/pml/owm/si-units-temperature)

Point minus point yields a difference. Point plus/minus difference yields a
point. Difference plus point also yields a point. Point plus point,
difference minus point, point/difference comparison or conversion, and products
or quotients containing a temperature point are refused. The last restriction
is deliberately explicit: this adapter does not silently make affine arithmetic
meaningful by treating a temperature point as an ordinary scalar. Domain models
that multiply thermodynamic temperatures need a separately defined operation.
Affine quantities other than temperature are unsupported. Physical validity,
including whether a temperature domain is appropriate, is not inferred.

## Bounds, dependence, and declared precision

Endpoints use exact rational arithmetic. Addition/subtraction and the four
endpoint products or quotients produce conservative closed enclosures. Division
is refused whenever the denominator interval includes zero, even if its
numerator interval is exactly zero. There is no hidden rounding, clipping,
infinite sentinel, or successful partial result.

An interval does not mean a standard deviation, confidence interval, Gaussian
distribution, or independent noise. Shared sources and revisions survive
composition. Even `quantity_sub(q, q)` conservatively returns `[-width, width]`
for a nonzero-width interval. Its mathematical value could be exactly zero if
the two occurrences denote the same underlying variable; this adapter does not
assume or solve those functional dependencies. Likewise `q/q` may conservatively
enclose more than the singleton one. A future affine/dependency arithmetic
adapter can tighten such bounds without changing this contract.

`quantity_measure` retains its original nominal value, absolute tolerance,
original unit, and source records in `declared_tolerances`. Converting the result
does not relabel the original declaration or imply more measurement precision.
Derived intervals retain all declarations, even when their dimensions differ
from the output dimensions. A zero-width measured input remains a measurement;
it does not become an exact definition through conversion or arithmetic.

Comparison returns a record with `outcome`, `relation`, parent identities,
`shared_sources`, `scope="declared_bounds"`, and
`independence="not_assumed"`. Supported relations are `lt`, `le`, `gt`, `ge`,
`eq`, `ne`. An overlapping threshold yields `indeterminate`, not an arbitrary
Boolean. Equality is established only for equal singleton intervals; disjoint
intervals refute equality. Source labels are retained declarations, not a
statistical model or authenticated source attestation.

## Sources, time, and recovery identities

Optional constructor metadata has only `sources`, `valid_from`, and
`valid_until`. Each source contains `id`, `version`, and optional `observed_at`.
Timestamps must use exact UTC `YYYY-MM-DDTHH:MM:SSZ`, at whole-second resolution.
No local time zone, offset, leap-second or missing-date interpretation is guessed.

Arithmetic intersects supplied validity windows and refuses an empty
intersection. Endpoints are inclusive. Missing validity limits mean no such limit
was supplied, not eternal freshness. Source IDs/revisions/times are retained,
including multiple revisions sharing a source ID.

`quantity_status` requires `evaluated_at` and never obtains current time itself.
It separately reports `validity` (`not_declared`, `within_declared_window`,
`not_yet_valid`, `expired`) and `freshness` (`not_assessed`, `unknown`,
`within_max_age`, `stale`, `not_yet_observed`). Freshness becomes `unknown` when an
age limit was supplied but observations are absent or incompletely dated. A
future observation is explicitly reported. Arithmetic does not automatically
consult this temporal policy; the program can assert its required status before
acting.

Every quantity carries the schema/version, origin kind, sources, validity,
tolerances and bounded operation provenance. Immediate parent identities are
full SHA-256 values over Symblic's canonical encoding. They support traceability
and are not signatures. Records are detached from caller containers. A caller
can still author a record containing false factual declarations; this module
validates arithmetic and schema, not authenticity or reality.

## Resource and integration contract

Dimensions have exponents in -32..32. Each result has at most 32 distinct source
records and 32 tolerance declarations; unions exceeding those limits fail.
Text fields are at most 256 Unicode characters and must encode as UTF-8.
Timestamps have the fixed shape above. Integers/rational components and
preflighted intermediates are limited to 4096 bits; each call defaults to at most
200,000 deterministic work units. Callers may lower these limits using `max_bits`
and `max_work`. The shared kernel budget is charged throughout. A representable
final value may still be refused if an intermediate exceeds the selected bound.

The isolated core includes `symblic.adapters.quantities` in the fixed `ADAPTERS` table
with key `quantities`, builtin help, and both execution-pin file registries.
The reused arithmetic module is pinned too. The wrapper imports the module on
use; an eager import would create a cycle because the adapter imports Symblic.
Pure quantity calls can participate in existing builtin-only anchored contracts;
they do not belong in effect or speculation deny lists. Existing
`symblic/lang/library/units.sym` remains unchanged. Server restart and deployment gating
remain separate from these source edits and isolated checks.

The isolated tests cover known conversions, signed endpoint arithmetic against
an independent rational reference, incompatible dimensions, affine points and
differences, threshold overlap, source dependence, validity boundaries,
malformed/extreme inputs, limits, inert import, shared kernel budget, and normal
Symblic expression evaluation. They contain no external calls or real data.
