# symblic: the Python package

Everything that makes up Symblic lives in this package, one subpackage per concern. Importing `symblic` does
nothing by itself; each subpackage has a README that says what is in it, what it depends on, how it is run and
how to run its tests. The command line in front of all of it is [`tools/symblic`](../tools/) (`tools/symblic --help`).

All of it was written by AI agents (see [../docs/MADE-WITH-AI.md](../docs/MADE-WITH-AI.md)). "Tested" below
means the subpackage's own unit tests pass with fake models and temporary folders; it does not mean a human
reviewed it or that it was measured with real models.

## How the pieces fit

```
                         tools/symblic  (command line)
                                |
   english / spec / steps / authoring / lang      ways of writing a program
                                |
                         kernel  (parse, check, evaluate exactly, run, record, replay)
                         /      |        \
              providers      adapters      js + sandbox
   (an ask reaches a model)  (exact builtins) (model-written JavaScript, run against examples)

   delegate, graph, mica, autogen          hand bounded work to agents; every result is checked by code
   linear + constructor, intent, forge,    research prototypes around the kernel
   inquiry, memory, policy
   bench, experiments, distill, portable   measurement, research experiments, cross-machine checks
   os                                      a prototype command layer
```

The kernel needs only the Python standard library from outside this repository. Inside it, `kernel` also
imports a few siblings it runs programs with (`adapters`, `js`, `lang`, `constructor`, `providers`, `delegate`,
`english`), several of them only inside the function that needs them; everything else builds on the kernel. Nothing in `symblic/kernel` imports
[`../integration/host/`](../integration/host/README.md); a few other subpackages import a host module lazily, on
the code path of a host-only feature, and say so in their READMEs.

## The subpackages

| Subpackage | What it is | Status |
|---|---|---|
| [`kernel/`](kernel/README.md) | The language: parser, checker, exact evaluator, interpreter (`Run`), run folders, replay, locks, previews, process limits. Start here. | Tested; the core of the project |
| [`providers/`](providers/README.md) | How an `ask` reaches a model: Ollama over HTTP, a configured command line, or a fake for tests. | Tested with a fake Ollama server only |
| [`adapters/`](adapters/README.md) | Exact builtins: geometry, drawings, linear algebra, finite logic, proof checking, quantities. | Tested |
| [`js/`](js/README.md) | The test oracle for model-written JavaScript (bundles the Acorn parser). | Tested; needs Node.js and Linux Landlock |
| [`sandbox/`](sandbox/README.md) | A Linux Landlock and seccomp launcher for untrusted programs. | Tested on Linux |
| [`lang/`](lang/README.md) | Functions, routines, modules, in-language tests and the standard library (`library/*.sym`). | Tested |
| [`spec/`](spec/README.md) | Spec sheets: a file described as small units with contracts and examples, built unit by unit. | Tested; the measured use case (see [../docs/HONEST-ASSESSMENT.md](../docs/HONEST-ASSESSMENT.md)) |
| [`english/`](english/README.md) | Programs written as short English sentences, each compiled to a checked statement. | Experimental |
| [`steps/`](steps/README.md) | Step constructions: the model picks the number of the right expression for each step. | Experimental |
| [`authoring/`](authoring/README.md) | Writing aids: workcards, papers (`.symd`), statement tightening, editor diagnostics. | Tested; the model-measuring parts are experimental |
| [`delegate/`](delegate/README.md) | Hand one bounded task to a small agent and get a checked value back. | Tested with fakes |
| [`graph/`](graph/README.md) | Small agent workflows in which every node is a checked program. | Prototype |
| [`mica/`](mica/README.md) | Checked assembly of small JavaScript programs from function contracts. | Experimental |
| [`autogen/`](autogen/README.md) | Regenerate, split and hand off agent attempts until code accepts them. | Experimental |
| [`linear/`](linear/README.md), [`constructor/`](constructor/README.md) | A solver (Z3, optional) instead of a model for asks whose checks are linear arithmetic, and its durable journal. | Prototype |
| [`intent/`](intent/README.md), [`forge/`](forge/README.md) | Recording what was asked, and a requirements workbench, before any code is written. | Prototype |
| [`inquiry/`](inquiry/README.md), [`memory/`](memory/README.md), [`policy/`](policy/README.md) | Choosing the next check, keeping claims between runs, choosing a routing policy honestly. | Research prototypes |
| [`bench/`](bench/README.md) | The runners and scoring rules behind the recorded measurements. | Measurement machinery |
| [`experiments/`](experiments/README.md) | Finite research experiments with reproducible receipts. | No result claimed |
| [`distill/`](distill/README.md) | A fine-tuning pipeline (one tiny pilot). | No result claimed |
| [`portable/`](portable/README.md) | Run the pure interpreter on another machine and compare fingerprints. | Tested |
| [`os/`](os/README.md) | A prototype command layer driven by Symblic. Not an operating system. | Experimental prototype |

## Tests

Each subpackage has a matching folder under [`../tests/`](../tests/README.md):

    DASH_TEST=1 python3 -m unittest discover -s tests/kernel -t .

[`../tests/README.md`](../tests/README.md) explains the whole suite, its run time and what is skipped.
