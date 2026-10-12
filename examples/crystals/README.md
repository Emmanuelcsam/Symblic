# Crystals

A *crystal* freezes a routine's answers into a table the kernel can read. A panel of models answers the routine
for every input in a finite list; inputs on which the panel agreed (unanimously by default) are kept, and the
result is written as an ordinary program: a `let` table, a `function` that looks an input up and fails on any
input outside the table, and a `test` that the table answers its own inputs. After that, no model is called.

| file | what it is | run |
|---|---|---|
| `elements.sym` | the routine: `is_metal(element)` asked of a panel of two model families (`claude:haiku`, `codex`) | asks models; crystallising it needs those applicators |
| `is_metal.crystal.sym` | the crystal made from it on 2026-10-02: 20 of 20 elements kept (hydrogen to calcium) | **no model**: `tools/symblic test examples/crystals/is_metal.crystal.sym` |

A crystal records which models agreed, not that they were right: the table is only as good as the panel's
answers on those inputs, and it says nothing about inputs it does not contain. The measurement is described in
[../../docs/reference/RESULTS.md](../../docs/reference/RESULTS.md) (search for "Crystallisation"); the
steps of `crystallise` are in section 4b of [../../docs/reference/LANGUAGE-3.md](../../docs/reference/LANGUAGE-3.md).
