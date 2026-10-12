/* Authored academy curriculum and public source map. Stable original level/bite positions. */
/* Remapped for the public repository on 2026-10-12: source and reference URLs are repository paths ("/docs/reference/OPERATORS.md"), documents that are not in the repository were removed, and tools/scripts/symblic_refresh_catalog.py refreshes the source metadata. */
window.SymblicAcademyContent = {
  "version": 2,
  "updated": "2026-10-12",
  "levels": [
    {
      "lvl": 0,
      "title": "Level 0: The Big Picture",
      "desc": "Zero assumptions. Understanding why Symblic exists and how it unifies calculators with AI.",
      "bites": [
        {
          "title": "Two Brains in Your Computer",
          "concept": "Symblic separates proposing an answer from deciding whether that answer meets an explicit contract. The model interprets language or proposes structured data. The kernel computes supported operations and checks types and predicates. This makes the boundary inspectable: you can see which answer was accepted and which rule was applied. It does not make the model a source of ground truth. If an invoice was misread, exact arithmetic can faithfully calculate the wrong total. A good program therefore separates source extraction, mathematical consistency and evidence that the extracted fields match the source.",
          "metaphor": "",
          "code": "",
          "question": "An invented invoice record satisfies quantity × price = total. What has the check established?",
          "options": [
            "That the record matches the invoice",
            "Internal arithmetic consistency only",
            "That the model understood the customer"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "The equation can hold for invented values. Add checks tied to source evidence and missing cases.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A source states three items at eight units each. The model proposes quantity 3 and price 8.",
              "The kernel computes 3 × 8 = 24 and checks any declared total.",
              "If the model instead invents 2 and 12, the same total passes; source-grounding checks are still needed."
            ],
            "takeaway": "Exact computation establishes the result of the encoded operation, not the correctness of every input or requirement."
          },
          "feedback": [
            "Matching the source requires evidence about the extracted fields.",
            "The equation can hold for invented values. Add checks tied to source evidence and missing cases.",
            "A satisfied equation does not evaluate human understanding."
          ],
          "reflection": {
            "prompt": "Which parts of an invoice task belong to interpretation and which to exact computation?",
            "model": "Reading labels and mapping text to fields involve interpretation. Multiplication, summation and declared bounds belong to computation. Matching fields to source spans provides a separate evidence link."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            }
          ]
        },
        {
          "title": "Exact fractions and measured uncertainty",
          "concept": "Binary floating-point stores many decimal fractions approximately. Symblic’s rational kernel can represent a decimal literal such as 0.1 as exactly 1/10, so 0.1 + 0.2 equals exactly 3/10. This is exactness of a representation and its supported operations. It does not turn an uncertain measured length into an exact physical length, and transcendental calculations may use documented approximations. Reproducibility also depends on the actual operation and kernel identity, not a slogan about every computer. Use rational arithmetic when exact ratios matter; keep uncertainty and rounding policy explicit at the boundary.",
          "metaphor": "",
          "code": "let tenth = 0.1 + 0.2.\nassert tenth = 0.3.\nlet third = 1 / 3.\nassert third * 3 = 1.",
          "question": "Which statement about storing a measured length as an exact fraction is correct?",
          "options": [
            "The physical length is now known without uncertainty",
            "The encoded number is exact, while measurement uncertainty remains",
            "Every irrational calculation becomes rational"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Keep numerical representation separate from empirical knowledge of the quantity.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Represent 0.1 as 1/10 and 0.2 as 2/10.",
              "Add numerators over the shared denominator: 3/10.",
              "Compare a measured 0.1 mm: the stored rational is exact, but the measurement may still have calibration and reading uncertainty."
            ],
            "takeaway": "Rational exactness removes this arithmetic rounding error; it does not remove measurement, specification or implementation errors."
          },
          "feedback": [
            "Encoding does not improve the measurement.",
            "Keep numerical representation separate from empirical knowledge of the quantity.",
            "Irrational and transcendental results need their own supported representation or approximation."
          ],
          "reflection": {
            "prompt": "Explain exact arithmetic to someone who thinks it guarantees an infallible program.",
            "model": "It guarantees specified rational operations within the implementation’s domain, assuming the implementation is correct. Wrong inputs, wrong formulas, omitted requirements and hardware/software defects are separate issues."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Execution Pins",
              "url": "/docs/reference/EXECUTION-PINS.md"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            }
          ]
        },
        {
          "title": "Starting Your Program (`program Name.`)",
          "concept": "A program name gives the work a readable identity. The language then distinguishes declarations, computations, asks and checks. English-looking syntax does not mean any English sentence is a verified computation. Inspect the parsed or previewed program when translating a goal, especially if it contains prose. A program called “SafeInvoice” has no safety property merely because of its name; the properties come from its inputs, operations and checks. A source file, its parsed structure and a run record answer different questions: what was written, what the parser understood and what actually happened.",
          "metaphor": "",
          "code": "program InvoicePractice.\nlet quantity = 3.\nlet price = 8.\nlet total = quantity * price.\nassert total = 24.\nshow total.",
          "question": "A program passes its static check. Which claim is still unestablished?",
          "options": [
            "The source met the checker’s rules",
            "The program can be inspected",
            "Every future model answer will satisfy the intended task"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Runtime replies, resources and specification adequacy still matter.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Write program InvoicePractice.",
              "Bind known input with given or let, then compute a total and assert the intended relation.",
              "Preview the program and identify where a model would be asked; a preview is not evidence that such a call succeeded."
            ],
            "takeaway": "Names organize a program; executable statements and their semantics determine behaviour."
          },
          "feedback": [
            "That is the bounded meaning of a successful static check.",
            "Inspection is possible independently of whether every run succeeds.",
            "Runtime replies, resources and specification adequacy still matter."
          ],
          "reflection": {
            "prompt": "Describe the difference between a program and a successful run of it.",
            "model": "The program states operations and contracts. A run records particular inputs, replies, checks and outcomes. The source alone cannot establish that external responses or effects occurred."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Reinforcements/Communication Review",
              "url": "/docs/reference/reinforcements/communication-review.md"
            }
          ]
        },
        {
          "title": "Storing Values with `let`",
          "concept": "A binding gives a computed value a name so later expressions can use it. Arithmetic precedence matters: multiplication and division occur before addition and subtraction unless parentheses say otherwise. Reading a program requires tracking dependencies, not merely reading lines as a story. If total depends on tax and tax depends on price, changing price affects both. Names should describe quantities precisely, including unit conventions where the type does not carry them. A value called temperature could mean Celsius or kelvin; the name alone cannot make an incorrect subtraction meaningful.",
          "metaphor": "",
          "code": "let price = 50.\nlet tax = price * (8 / 100).\nlet total = price + tax.\nassert total = 54.",
          "question": "What value does 10 + 5 * 2 produce?",
          "options": [
            "20",
            "30",
            "25"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Multiplication occurs first: 10 + 10 = 20.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "let price = 50. let tax = price * (8/100).",
              "Tax evaluates to 4, then let total = price + tax gives 54.",
              "In 10 + 5 * 2, multiplication gives 10 first; the final value is 20, whereas (10 + 5) * 2 gives 30."
            ],
            "takeaway": "Trace the expression tree and units before trusting a variable’s reassuring name."
          },
          "feedback": [
            "Multiplication occurs first: 10 + 10 = 20.",
            "That corresponds to (10 + 5) * 2.",
            "Neither the written precedence nor the parenthesized alternative gives 25."
          ],
          "reflection": {
            "prompt": "How would you make a unit-sensitive calculation easier to review?",
            "model": "Name quantities and units, convert at explicit boundaries, show the formula and one hand-computed case, and distinguish measured inputs from assumed constants."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Natural Language Bridge",
              "url": "/docs/reference/NATURAL-LANGUAGE-BRIDGE.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 1,
      "title": "Level 1: The Calculator (Variables, Math & Types)",
      "desc": "Mastering the deterministic Kernel: exact numbers, bounded integers, and assertion lie-detectors.",
      "bites": [
        {
          "title": "What an assertion really establishes",
          "concept": "An assertion evaluates a Boolean proposition over the program’s current values. If it fails, execution stops with a failure. If it passes, that proposition holds for those values under the kernel’s semantics. Calling it a truth detector is misleading: it cannot discover whether the proposition captured the right requirement. “The total is nonnegative” admits many wrong totals. Write assertions that target plausible mistakes and compare with independent evidence where the task requires it. A failed assertion may reveal bad data, a bad interpretation, a bad requirement or a defect; diagnose rather than assuming the model is always at fault.",
          "metaphor": "",
          "code": "",
          "question": "A result passes assert total >= 0. What may you conclude?",
          "options": [
            "The total matches the original document",
            "The encoded total is nonnegative",
            "The entire program is correct"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "This is exactly the predicate evaluated.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A total of 24 passes total >= 0.",
              "An incorrect total of 2 also passes.",
              "A stronger arithmetic check total = quantity * price excludes some errors, but still needs grounded quantity and price."
            ],
            "takeaway": "The strength of the conclusion is limited by the strength and relevance of the predicate."
          },
          "feedback": [
            "The assertion does not compare with the document.",
            "This is exactly the predicate evaluated.",
            "Other requirements and inputs remain unchecked."
          ],
          "reflection": {
            "prompt": "Write a counterexample to a weak assertion.",
            "model": "For a summary checked only by word count, an unrelated sentence of the required length passes. Add source-grounded content checks and test whether they actually reject irrelevant summaries."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            }
          ]
        },
        {
          "title": "Bounded Integers (`Int in min..max`)",
          "concept": "A bounded integer type constrains both kind and range. Int in 1..5 excludes fractions and values outside the interval, but every remaining integer may still be semantically wrong for a particular source. Types narrow the space of admissible replies and make downstream computation predictable. They do not decide which allowed value is true. Choose bounds from the task, not from a desire to force a preferred answer. Include a representation for missing or unresolved information when the source may not provide a number; forcing an answer can encourage fabricated precision.",
          "metaphor": "",
          "code": "",
          "question": "The source count is unknown, but a schema requires an integer 1..5. What is the design concern?",
          "options": [
            "The range guarantees a correct guess",
            "Smaller ranges remove missing data",
            "The schema may force a plausible but unsupported number"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Represent or explicitly handle missing evidence instead of making the output shape hide it.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "For a count in 1..5, the value 3 fits the type.",
              "The value 3.5 fails the integer requirement and 8 fails the upper bound.",
              "If the source says 4, a reply of 3 still passes the type and needs a semantic check."
            ],
            "takeaway": "Type validity is one layer of acceptance, not a source-fidelity guarantee."
          },
          "feedback": [
            "A bounded guess can still be false.",
            "Missingness is a property of the evidence, not the size of the answer space.",
            "Represent or explicitly handle missing evidence instead of making the output shape hide it."
          ],
          "reflection": {
            "prompt": "Distinguish a type error from a factual extraction error.",
            "model": "A fractional response for an integer count violates the type. A permitted integer that disagrees with the source is factually wrong even though type validation succeeds."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Language 3",
              "url": "/docs/reference/LANGUAGE-3.md"
            }
          ]
        },
        {
          "title": "Whole Number vs Exact Division (`//` vs `/`)",
          "concept": "Exact division preserves a ratio; integer division returns a whole-number quotient under the language’s rules. For positive quantities, 7/2 is 3.5 while 7//2 is 3. Choose by meaning: dividing seven objects into full pairs differs from sharing seven units equally between two recipients. An early integer division can silently discard information that later multiplication cannot recover. Keep an exact ratio through calculations unless the task explicitly requires a quotient or rounding. When negatives occur, consult the language’s integer-division convention rather than assuming every language truncates the same way.",
          "metaphor": "",
          "code": "let exact_average = (7 + 8) / 2.\nassert exact_average = 15 / 2.",
          "question": "You need the exact average of totals 7 and 8. Which calculation preserves it?",
          "options": [
            "(7 + 8) / 2",
            "(7 + 8) // 2",
            "7 + 8 / 2"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "The exact average is 15/2 = 7.5.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Seven objects make three complete pairs with one left over.",
              "Equal sharing gives each of two people 7/2 units, not 3.",
              "If you compute (7//2)*2 you get 6; (7/2)*2 returns 7."
            ],
            "takeaway": "The appropriate operation follows the quantity you intend to represent."
          },
          "feedback": [
            "The exact average is 15/2 = 7.5.",
            "Integer division loses the half unit.",
            "Precedence gives 11, not the average of both values."
          ],
          "reflection": {
            "prompt": "Give a case where integer division is the right operation.",
            "model": "Counting complete groups of a fixed positive size, provided the remainder is handled separately. It is not appropriate for a mean that can legitimately be fractional."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            }
          ]
        },
        {
          "title": "Why exact computations have resource limits",
          "concept": "Exact arithmetic can consume substantial resources because numerators and denominators grow. Symblic therefore bounds work and numeric sizes; adapters have their own documented domains. A refusal is preferable to silently returning a partial or rounded result while claiming exactness. A step count is not a universal runtime estimate: operand size and host conditions still matter. Check both the final answer and intermediate growth. Two algebraically equivalent expressions can have different resource behaviour if one creates a very large intermediate. Resource limits constrain a computation, not the truth of the mathematical claim it was attempting.",
          "metaphor": "",
          "code": "",
          "question": "A solver refuses a problem because an intermediate exceeds its bit limit. What follows?",
          "options": [
            "The mathematical problem has no solution",
            "This execution exceeded the supported resource domain",
            "The returned approximation is certified"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Report the actual refusal and the relevant bound.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "An expression multiplies enormous integers and later divides them back down.",
              "The final result may be small, but the intermediate can exceed a configured arithmetic bound.",
              "Rewrite within supported operations if justified, or report the refusal; do not describe it as proof that no mathematical solution exists."
            ],
            "takeaway": "Bounded exact computation has explicit refusal conditions."
          },
          "feedback": [
            "A resource limit is not a nonexistence proof.",
            "Report the actual refusal and the relevant bound.",
            "A refusing exact adapter has not supplied a certified approximate answer."
          ],
          "reflection": {
            "prompt": "Why should a benchmark report coefficient sizes as well as matrix dimension?",
            "model": "Rational intermediate growth can dominate cost. Two matrices of the same dimension can require very different integer sizes and work."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Variational",
              "url": "/docs/reference/VARIATIONAL.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 2,
      "title": "Level 2: Commanding the AI (The Model & Capsule)",
      "desc": "Controlling neural models: sterile capsules, exact output schemas, and effort dials.",
      "bites": [
        {
          "title": "The Shared Dictionary (`term`)",
          "concept": "A shared term gives a task-specific definition for a word whose everyday meanings differ. “Urgent,” “complete” and “safe” are not self-executing rules. Define observable criteria, boundary cases and exclusions. A term helps communicate that definition to a model; the kernel does not magically verify that the model internalized it. Pair the definition with examples and checks that reveal disagreement. Distinguish a stipulative definition for this task from a universal claim about language. Different communities may reasonably use a word differently, so make the local convention visible.",
          "metaphor": "",
          "code": "",
          "question": "Two models use “urgent” differently despite reading the same definition. What is most useful?",
          "options": [
            "Repeat the word in capitals",
            "Declare their disagreement impossible",
            "Test contrasting boundary examples and refine the operational criterion"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Contrasting cases show which feature drives the difference and make the definition testable.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Define urgent for a synthetic queue as an explicit deadline within 24 hours.",
              "A message saying “important sometime this month” is not urgent under that convention.",
              "A message with no deadline is unresolved unless the specification defines a fallback."
            ],
            "takeaway": "A shared dictionary reduces ambiguity only when its application is tested."
          },
          "feedback": [
            "Emphasis does not identify the semantic boundary.",
            "Shared text does not guarantee shared interpretation.",
            "Contrasting cases show which feature drives the difference and make the definition testable."
          ],
          "reflection": {
            "prompt": "Give a boundary example for a 24-hour urgency rule.",
            "model": "Compare an explicit deadline at 23 hours, exactly 24 hours and 25 hours, plus a missing deadline. Specify whether the boundary is inclusive."
          },
          "references": [
            {
              "title": "Natural Language Bridge",
              "url": "/docs/reference/NATURAL-LANGUAGE-BRIDGE.md"
            },
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            }
          ]
        },
        {
          "title": "Asking with Strict Output Types (`ask`)",
          "concept": "An ask requests a value of a declared type from an applicator. A closed enumeration limits permissible labels; a record organizes fields; a list constrains a collection. Providers differ in how they support structured output, so local acceptance checks remain essential even when a schema is sent. Valid JSON is merely syntax. A valid typed record can still omit a real-world distinction or contain an unsupported value. Design the answer space around the question and include meaningful refusal or uncertainty paths where needed. Then define which checks establish format, consistency and source fidelity.",
          "metaphor": "",
          "code": "",
          "question": "A reply is valid JSON and fits the schema. Which problem can remain?",
          "options": [
            "The extracted values do not match the source",
            "JSON syntax must still be invalid",
            "Every factual question is settled"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Shape and truth are separate. The source relation needs its own checks.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Ask for a record with quantity, unit price and source evidence.",
              "Validate the field types, compute quantity × unit price locally, and check the evidence against the input.",
              "If the source is ambiguous, retain that ambiguity instead of converting a confident-looking record into certainty."
            ],
            "takeaway": "A structured answer is easier to inspect; structure alone does not make it true."
          },
          "feedback": [
            "Shape and truth are separate. The source relation needs its own checks.",
            "The premise already says the JSON is valid.",
            "A schema defines admissible values, not their factual correctness."
          ],
          "reflection": {
            "prompt": "How would you test an extraction schema before relying on it?",
            "model": "Use clear, missing, conflicting and boundary examples. Track type failures separately from wrong accepted values and evaluate source fidelity on cases not used to tune the schema."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            },
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            }
          ]
        },
        {
          "title": "Capsules: explicit and sufficient context",
          "concept": "A capsule is the explicit context supplied for an ask. Controlling it makes the model’s task inspectable and avoids silently depending on an ever-growing conversation. But small context is not automatically sufficient context. A pronoun, unit, exception or prior decision may require a specific earlier fact. Design the capsule around dependencies: include what the task needs and preserve provenance, while excluding irrelevant material. A retry can legitimately include prior failure information, which also changes the evidence dependencies. Record what the model actually saw before calling two answers independent.",
          "metaphor": "",
          "code": "",
          "question": "A model cannot resolve “that sample” after earlier context was excluded. What should be repaired?",
          "options": [
            "Always increase model size",
            "Restore the needed referent or clarify it",
            "Force a sample ID from a closed list"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "The missing dependency belongs in the capsule or clarification workflow.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "The sentence “use that amount again” has no determinate quantity in isolation.",
              "Supply the relevant earlier amount and its unit, or ask for clarification.",
              "Compare the minimal sufficient capsule with a context that omits the referent; failure in the latter is a specification problem, not simply low model intelligence."
            ],
            "takeaway": "Isolation makes context explicit; it does not prove that the selected context is adequate."
          },
          "feedback": [
            "A larger model cannot reliably recover information never supplied.",
            "The missing dependency belongs in the capsule or clarification workflow.",
            "A forced choice hides the missing information."
          ],
          "reflection": {
            "prompt": "What belongs in a capsule dependency review?",
            "model": "Inputs, definitions, units, relevant prior decisions, source identity/version and any feedback or candidate information visible to the model."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            },
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            }
          ]
        },
        {
          "title": "The Effort Dial (`with effort=...`)",
          "concept": "Effort and routing options control how candidate answers are produced and evaluated, subject to the actual provider and runner contract. More calls can improve coverage of an answer space but also increase latency and cost. Multiple replies are not independent merely because they have different labels: they may share training data, prompts, source errors or feedback. Choose effort based on measured task performance, false acceptance, refusal and cost. A precise deterministic calculation should stay in the kernel. An ambiguous specification needs clarification before spending additional inference on the same unresolved question.",
          "metaphor": "",
          "code": "",
          "question": "All candidates fail the same boundary example. What should you inspect first?",
          "options": [
            "Only the number of models",
            "Whether the progress animation is smooth",
            "Specification and example consistency"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "A shared failure can expose a contradiction or ambiguity in the task.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Three models all extract the wrong date from the same misleading sentence.",
              "Their agreement is real, but its shared input error defeats the intended truth claim.",
              "Add a discriminating source check or clarify the date definition; another vote alone may reproduce the same error."
            ],
            "takeaway": "Compute budget and evidence quality are related through the task, not through a universal “more is better” rule."
          },
          "feedback": [
            "More candidates cannot satisfy an impossible or wrongly stated contract.",
            "Rendering has no bearing on the contract.",
            "A shared failure can expose a contradiction or ambiguity in the task."
          ],
          "reflection": {
            "prompt": "What metrics would justify a higher-effort setting?",
            "model": "Held-out task accuracy or source fidelity, wrong-acceptance and refusal rates, latency and total call cost under a matched protocol. Agreement alone is insufficient."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 3,
      "title": "Level 3: Checks, repair & recovery",
      "desc": "Self-healing programs: guardrails, transactional rollbacks, and bounded retries.",
      "bites": [
        {
          "title": "Repairing candidates with ensure",
          "concept": "An ensure check can request repair when a candidate fails an explicit condition. The feedback should identify the failed condition and useful evidence, rather than merely demanding a better answer. A successful retry means the new candidate passed the checks actually applied. It does not mean the original requirement was complete or that all hallucinations were eliminated. Some failures require revising the specification or obtaining missing information instead of retrying. Keep the distinction between a repair of the candidate and a repair of the contract: changing a check to accept an answer changes what has been established.",
          "metaphor": "",
          "code": "",
          "question": "A candidate repeatedly fails because two requirements contradict each other. What is appropriate?",
          "options": [
            "Diagnose and resolve the contradictory requirements",
            "Retry indefinitely",
            "Delete whichever requirement is harder without recording it"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "The specification must change explicitly before acceptance can have the intended meaning.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A candidate returns a total of 20 where grounded quantity 3 and price 8 imply 24.",
              "Feedback names the mismatch and the source-backed fields.",
              "A retry returning 24 passes that arithmetic check; an unrelated missing tax requirement remains untested."
            ],
            "takeaway": "Retries are bounded opportunities to satisfy a contract, not a universal guarantee of success."
          },
          "feedback": [
            "The specification must change explicitly before acceptance can have the intended meaning.",
            "No candidate can satisfy an inconsistent contract.",
            "Silent deletion damages intent fidelity."
          ],
          "reflection": {
            "prompt": "Write useful feedback for a source-grounded numerical mismatch.",
            "model": "State the failed relation, expected units, grounded input values and the relevant source location. Do not invite the model to invent new inputs merely to make the equation pass."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Interpreter",
              "url": "/docs/reference/INTERPRETER.md"
            },
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            }
          ]
        },
        {
          "title": "Rollback and the external-world boundary",
          "concept": "Transactional retry restores the relevant program state to an ask anchor before trying again. This prevents failed candidate-derived state from leaking into the repaired computation. It is a property of the runner’s state handling, not a time machine for the external world. An email already sent or a device already moved cannot be undone by restoring variables. External effects therefore require a separate durable intent/outcome contract and recovery handling. When inspecting a retry, ask which state was restored, which evidence was retained for diagnosis, and which actions may already have occurred.",
          "metaphor": "",
          "code": "",
          "question": "A request may have reached an external service before the reply was lost. Does resetting local variables prove the action did not occur?",
          "options": [
            "Yes",
            "No; the external outcome can remain unknown",
            "Yes, if the next candidate passes"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Durable receipts and reconciliation are needed before deciding whether a repeat is safe.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "An ask produces a candidate, then dependent variables and facts are derived before a check fails.",
              "The retry restores the anchor so those failed derivations do not accumulate.",
              "If a remote action had occurred, inspect its effect ledger and recovery state; do not infer that in-memory rollback reversed it."
            ],
            "takeaway": "Internal rollback and external recovery solve different problems."
          },
          "feedback": [
            "Local memory does not determine remote state.",
            "Durable receipts and reconciliation are needed before deciding whether a repeat is safe.",
            "Candidate validation says nothing about the earlier remote outcome."
          ],
          "reflection": {
            "prompt": "Why must failed candidate-derived facts be removed before retry?",
            "model": "Otherwise the repaired candidate can be judged using stale evidence or accumulated state from a rejected answer, breaking the intended transactional boundary."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Effects",
              "url": "/docs/reference/EFFECTS.md"
            }
          ]
        },
        {
          "title": "Bounded retries are not convergence",
          "concept": "A retry ceiling bounds the number of repair attempts. Combined with other resource limits, it prevents an unsuccessful task from consuming unlimited work. This is a termination policy, not a convergence theorem. A problem may be impossible, unsupported or simply beyond the applicator’s ability. Report exhausted, refused and completed states distinctly. The best limit depends on the task and measured benefit of additional attempts. A sequence of decreasing error counts is not proof that the remaining requirements will eventually be met, especially if the error metric omits the user’s real objective.",
          "metaphor": "",
          "code": "",
          "question": "A run reaches its retry ceiling with a failing candidate. What should its status communicate?",
          "options": [
            "Mastery achieved",
            "Approximate proof of correctness",
            "Failure or exhaustion with the actual diagnostics"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Preserve the failure and budget evidence so the next decision is informed.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Allow an initial candidate and a configured number of repairs according to the runner’s convention.",
              "If all permitted attempts fail, return the recorded failure and diagnostics.",
              "Do not label the final candidate successful merely because no calls remain."
            ],
            "takeaway": "Bounded work guarantees a stopping policy, not a correct answer."
          },
          "feedback": [
            "Stopping is not success.",
            "A failed predicate does not become approximately proved through repetition.",
            "Preserve the failure and budget evidence so the next decision is informed."
          ],
          "reflection": {
            "prompt": "What distinguishes convergence from a retry limit?",
            "model": "Convergence is a property of an update rule and assumptions that approaches a specified solution. A retry limit simply stops after bounded attempts regardless of whether such a solution was reached."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Variational",
              "url": "/docs/reference/VARIATIONAL.md"
            },
            {
              "title": "Intense Critique And Limitations",
              "url": "/docs/reference/INTENSE-CRITIQUE-AND-LIMITATIONS.md"
            }
          ]
        },
        {
          "title": "Reading syntax and recognizing proposals",
          "concept": "A visible syntax marker helps a reader identify the intended role of a statement, but its meaning comes from the parser and current language specification. Do not infer executable semantics from punctuation in an essay or a proposed future-language example. Symblic research documents contain conceptual syntax alongside actual language contracts. For any unfamiliar sigil or construct, check whether it is accepted, preview what it becomes, and distinguish that from a real run. This habit prevents a persuasive design sketch from being mistaken for an installed capability.",
          "metaphor": "",
          "code": "",
          "question": "A document contains attractive syntax for a quantum type. What establishes that you can use it today?",
          "options": [
            "A current language contract and verified supported execution path",
            "Its presence in a theoretical essay",
            "The sophistication of its name"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Support must be tied to actual parser/runtime behaviour and scope.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A research essay shows an illustrative “contract” block.",
              "Compare it with the current grammar and adapter documentation.",
              "If it is a proposal, discuss the intended invariant in plain language and write a supported equivalent only if the actual language can express it."
            ],
            "takeaway": "Notation is not evidence that an implementation exists."
          },
          "feedback": [
            "Support must be tied to actual parser/runtime behaviour and scope.",
            "Research prose can include proposals or pseudocode.",
            "A name does not implement semantics."
          ],
          "reflection": {
            "prompt": "How should a lesson label pseudocode?",
            "model": "Explicitly as conceptual or proposed, describe what it illustrates, and link separately to the actual executable syntax and tested capabilities."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Language 3",
              "url": "/docs/reference/LANGUAGE-3.md"
            },
            {
              "title": "Quantum Foundations Of Symblic",
              "url": "/docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 4,
      "title": "Level 4: Structured Data & Declarative Logic",
      "desc": "Tables, relations, facts, and logical deduction without hallucination.",
      "bites": [
        {
          "title": "Typed Tables",
          "concept": "A typed record gives named fields a defined shape; a collection of records organizes repeated observations. The schema should express which fields belong together and which distinctions must survive processing. Consistent structure makes calculation and comparison easier, but it can also hide information if a field collapses observation, interpretation and confidence into one value. Keep source identity and missingness where relevant. Validate relationships between fields separately from their individual types. Two valid dates can still appear in an impossible start/end order; two valid numbers can still use incompatible units.",
          "metaphor": "",
          "code": "",
          "question": "Every field in a record fits its type, but end precedes start. What is missing?",
          "options": [
            "More decorative field names",
            "A relation check between fields",
            "A larger text prompt alone"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Types may admit each date individually while a cross-field invariant rejects the combination.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Represent a synthetic measurement with value, unit, specimen ID and source location.",
              "Check each field’s type, then check that the unit and specimen are appropriate for the calculation.",
              "Preserve the original record when producing a transformed value so the interpretation remains traceable."
            ],
            "takeaway": "A schema is a model of what matters; omitted distinctions do not become unimportant."
          },
          "feedback": [
            "Naming helps reading but does not enforce the relationship.",
            "Types may admit each date individually while a cross-field invariant rejects the combination.",
            "The relationship should be stated and checked explicitly."
          ],
          "reflection": {
            "prompt": "Design fields that separate a claim from its provenance.",
            "model": "Use a claim value plus source ID/location, observation or inference status, relevant conditions and uncertainty. Do not treat a provenance label itself as proof of correctness."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            }
          ]
        },
        {
          "title": "Facts & Rules",
          "concept": "Facts state relations in a knowledge base; rules derive further relations. A rule is an implication under the encoded interpretation. It does not independently verify that an input fact is true. Recursive rules can compute reachability: direct links imply reachability, and a link followed by a reachable path implies a longer reachable path. The engine’s fixed point is the set of derivable facts under supported rules. Missing facts and negation need care: absence from a finite database need not mean absence in the world. Preserve the distinction between the closed encoded system and the open domain it models.",
          "metaphor": "",
          "code": "",
          "question": "A rule derives a conclusion from an incorrect input fact. Which description is accurate?",
          "options": [
            "The logical engine necessarily malfunctioned",
            "The derived conclusion verifies the premise",
            "The derivation can be valid while the premise is false"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Review both rule meaning and source evidence for facts.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Encode links A→B and B→C.",
              "A transitive reachability rule derives A→C.",
              "If the B→C input was erroneous, the deduction is still logically valid relative to the database but its real-world conclusion is unsupported."
            ],
            "takeaway": "Deductive validity and truth of premises are separate responsibilities."
          },
          "feedback": [
            "Correct deduction can faithfully propagate a bad premise.",
            "Deriving a consequence does not authenticate the inputs.",
            "Review both rule meaning and source evidence for facts."
          ],
          "reflection": {
            "prompt": "How would you audit a surprising graph result?",
            "model": "Trace the supporting path or derivation, inspect source facts and relation direction, then check whether the rule matches the intended relationship."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Language 3",
              "url": "/docs/reference/LANGUAGE-3.md"
            }
          ]
        },
        {
          "title": "Querying Knowledge with `?`",
          "concept": "A query asks for values satisfying a relation in the encoded knowledge base. Read variable positions carefully: asking who is an ancestor of Cleo differs from asking whom Cleo is an ancestor of. Query output is structured according to the number of variables and current language contract; do not assume an example from an older guide has the current result shape. The order of a displayed list may be a canonical presentation rather than a ranking. An empty answer means no matching derivation in the encoded data under the query, not a universal statement that the relation never exists.",
          "metaphor": "",
          "code": "",
          "question": "A query returns no affected customers in an incomplete supply-chain database. What follows?",
          "options": [
            "No affected customer was derived from the encoded facts and rules",
            "No real customer can be affected",
            "The database is complete"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "State the data-coverage limit and inspect missing links.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Given parent(Ada, Ben) and parent(Ben, Cleo), ancestor(Ada, Cleo) follows.",
              "Querying ancestor(Who, Cleo) seeks ancestors; querying ancestor(Cleo, Who) seeks descendants.",
              "Check a hand-sized graph and the documented output shape before building downstream code."
            ],
            "takeaway": "The direction and scope of a query determine its meaning."
          },
          "feedback": [
            "State the data-coverage limit and inspect missing links.",
            "Missing relationships can hide real downstream effects.",
            "Empty output cannot certify input completeness."
          ],
          "reflection": {
            "prompt": "What makes a good small test for a transitive query?",
            "model": "Include a direct link, a two-hop link, an unrelated node, and a reversed-direction case; compute expected results by hand and check the actual result shape."
          },
          "references": [
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            },
            {
              "title": "Reinforcements/Communication Review",
              "url": "/docs/reference/reinforcements/communication-review.md"
            }
          ]
        },
        {
          "title": "The Append-Only Ledger",
          "concept": "A ledger retains events so later state and explanations can be reconstructed. It is useful for tracing requests, accepted answers, checks and external outcomes. Append-only history preserves earlier records rather than rewriting them to fit the final story. But a ledger records claims and observations from particular components; it does not make every entry true or every external action reversible. Stable identities and receipts help distinguish a replay from a new action. When a reply is lost, record uncertainty rather than inventing a definite failure that invites duplicate execution.",
          "metaphor": "",
          "code": "",
          "question": "Why preserve a failed attempt after a later retry succeeds?",
          "options": [
            "It proves the final answer is wrong",
            "It explains the repair path, cost and evidence dependencies",
            "It should be deleted to improve the success rate"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "The earlier failure is part of how the result was obtained and may affect interpretation.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A request is recorded, dispatched and then loses its response.",
              "The ledger contains intent but no confirmed outcome.",
              "Reconciliation may recover a receipt; until then, an “unknown” state is more accurate than claiming either success or nonexecution."
            ],
            "takeaway": "Traceability supports investigation; it does not replace evidence about the external outcome."
          },
          "feedback": [
            "A successful repair can correct an earlier failure.",
            "The earlier failure is part of how the result was obtained and may affect interpretation.",
            "Deleting failures distorts both diagnosis and evaluation."
          ],
          "reflection": {
            "prompt": "What is the difference between replaying a recorded answer and reproducing a fresh model response?",
            "model": "Replay reuses a specific recorded result under a matching contract. A fresh call samples or computes again and may differ even with similar settings."
          },
          "references": [
            {
              "title": "Effects",
              "url": "/docs/reference/EFFECTS.md"
            },
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            },
            {
              "title": "Execution Pins",
              "url": "/docs/reference/EXECUTION-PINS.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 5,
      "title": "Level 5: Philosophy with clear boundaries",
      "desc": "Interpret philosophical and physical connections without extending their guarantees.",
      "bites": [
        {
          "title": "The Triangulation Metaphor (Donald Davidson)",
          "concept": "Davidson’s triangulation offers a philosophical way to think about shared meaning: interpreters coordinate with one another in relation to a common world. In Symblic, an engineering analogy is to compare the author’s intended rule and a model’s interpretation against the same explicit examples. A shared example makes disagreement discussable. This is an analogy and a design practice, not a theorem that two agreeing agents have captured reality. If both use the same faulty reference, their alignment can be precise and wrong. Include counterexamples and ask which observation could reveal their shared mistake.",
          "metaphor": "",
          "code": "",
          "question": "Two interpreters agree on an example generated by the same mistaken reference. What remains possible?",
          "options": [
            "Guaranteed independent validation",
            "Complete access to each other’s experience",
            "A shared error"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Agreement is conditional on the reference and may inherit its defect.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "An author means “gross amount before fees”; a model treats “amount” as net.",
              "Give a case with gross 100 and fees 5, and ask both to label gross and net.",
              "The disagreement becomes a precise 100-versus-95 distinction that can be repaired in the specification."
            ],
            "takeaway": "Common reference cases help coordinate interpretation while remaining open to correction."
          },
          "feedback": [
            "A common reference is not automatically an independent check.",
            "Public coordination does not reveal identical private experience.",
            "Agreement is conditional on the reference and may inherit its defect."
          ],
          "reflection": {
            "prompt": "Write a triangulation exercise for the word “complete.”",
            "model": "Provide one clearly complete case, one missing a required item, and a boundary case with an optional item absent. Ask the author and model to explain the same distinction."
          },
          "references": [
            {
              "title": "Intersubjectivity And Human Communication",
              "url": "/docs/reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md"
            },
            {
              "title": "Natural Language Bridge",
              "url": "/docs/reference/NATURAL-LANGUAGE-BRIDGE.md"
            }
          ]
        },
        {
          "title": "The Eloquence Trap (Jürgen Habermas)",
          "concept": "A fluent statement can be understandable without being factually correct, normatively acceptable or sincere. Habermas’s distinctions among validity claims are useful for separating these questions. In software, syntactic validity, factual grounding and authorization likewise require different evidence. A well-formed request to send a message may be unauthorized; a polite summary may misstate the source. In human conversation, a factual correction does not necessarily address the speaker’s concern or need. Use the distinction to ask better questions, not to classify someone’s emotions as machine-verified facts.",
          "metaphor": "",
          "code": "",
          "question": "A message is grammatically valid and factually accurate. Does that establish permission to send it?",
          "options": [
            "No; authorization is a separate question",
            "Yes",
            "Only if it is politely worded"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Check the relevant action authority independently.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Someone says “you never help” while describing an uneven workload.",
              "A counterexample may challenge “never” without settling whether the workload is fair or the person feels unsupported.",
              "Clarify the observable events, desired norm and requested change separately, allowing the person to correct your interpretation."
            ],
            "takeaway": "Separate kinds of claims before choosing a way to assess them."
          },
          "feedback": [
            "Check the relevant action authority independently.",
            "Truth and syntax do not determine whether the action is authorized.",
            "Politeness cannot supply missing authority."
          ],
          "reflection": {
            "prompt": "How does this distinction improve a Symblic contract?",
            "model": "Use separate checks for output shape, source fidelity, task constraints and action permissions. Do not let success on one stand in for all the others."
          },
          "references": [
            {
              "title": "Intersubjectivity And Human Communication",
              "url": "/docs/reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md"
            },
            {
              "title": "Effects",
              "url": "/docs/reference/EFFECTS.md"
            }
          ]
        },
        {
          "title": "Quantum collapse: analogy versus mechanism",
          "concept": "A model can produce several plausible candidate answers; a program selects or accepts one under explicit rules. Calling this “collapse” can be a memorable analogy to quantum language, but an LLM’s candidates are not established quantum superpositions and a Boolean check is not physical decoherence. The actual Symblic operator adapter computes a finite mathematical model of ordered projections on supplied rational vectors. That is a supported calculation with a defined domain. It does not read a model’s hidden state or prove that human thought follows quantum mechanics. Keeping analogy, mathematical model and physical mechanism separate makes the connection more useful.",
          "metaphor": "",
          "code": "",
          "question": "What does accepting a typed answer establish?",
          "options": [
            "Physical wavefunction collapse occurred",
            "The answer met the applied acceptance conditions",
            "Neural uncertainty has been eliminated forever"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "This is the supported software claim.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A candidate passes a type and a numerical constraint.",
              "Its accepted value becomes available to later program steps.",
              "That acceptance is ordinary program semantics; no physical measurement postulate is needed to explain it."
            ],
            "takeaway": "Quantum vocabulary should not expand the guarantee of a software check."
          },
          "feedback": [
            "No such physical process is measured by the acceptance mechanism.",
            "This is the supported software claim.",
            "Later interpretation and input uncertainty can remain."
          ],
          "reflection": {
            "prompt": "Name three distinct meanings that should not be conflated here.",
            "model": "A metaphor for choosing an answer, an exact projector probability model on supplied inputs, and a physical quantum measurement. They require different evidence."
          },
          "references": [
            {
              "title": "Quantum Foundations Of Symblic",
              "url": "/docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md"
            },
            {
              "title": "Operators",
              "url": "/docs/reference/OPERATORS.md"
            }
          ]
        },
        {
          "title": "Energy methods and their assumptions",
          "concept": "Energy methods can turn a differential equation or finite optimization problem into a statement about a scalar functional. Their conclusions require explicit assumptions: domain, coefficients, boundary conditions and the relevant function space. The implemented Symblic variational adapter solves a finite rational quadratic with a symmetric positive-definite matrix. It does not prove Navier–Stokes regularity or semantic convergence of retries. A metaphor comparing unstable reasoning with fluid turbulence can motivate a question, but does not transfer a PDE theorem to language. Study the finite energy identity because it provides a real, checkable example of how assumptions support uniqueness.",
          "metaphor": "",
          "code": "",
          "question": "Retry disagreement decreases. Does that establish convergence to the intended meaning?",
          "options": [
            "Yes, by the energy principle",
            "Yes, if the decrease is monotone",
            "No; agreement can increase around a shared wrong answer"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "The metric may omit fidelity or reward an incorrect consensus.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "For H(x) = x² − 4x, complete the square: H(x) = (x−2)² − 4.",
              "Every displacement from x = 2 adds a nonnegative square, so 2 is the unique minimum.",
              "For H(x) = −x², a stationary point at zero is instead a maximum; the sign assumption matters."
            ],
            "takeaway": "A scalar objective must be connected to the actual task before minimizing it can support a useful conclusion."
          },
          "feedback": [
            "No positive-definite semantic energy has been established by that observation.",
            "Monotonicity of a proxy does not make its optimum the intended answer.",
            "The metric may omit fidelity or reward an incorrect consensus."
          ],
          "reflection": {
            "prompt": "Explain the difference between a stationary point and a unique minimum.",
            "model": "Stationarity means first-order change vanishes. Positive curvature or another appropriate condition is needed to establish a minimum and uniqueness; −x² gives a counterexample."
          },
          "references": [
            {
              "title": "Variational",
              "url": "/docs/reference/VARIATIONAL.md"
            },
            {
              "title": "Physics And Advanced Mathematics",
              "url": "/docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md"
            },
            {
              "title": "Grand Unification And String Theory",
              "url": "/docs/reference/GRAND-UNIFICATION-AND-STRING-THEORY.md"
            }
          ]
        },
        {
          "title": "Representation, equivalence and information loss",
          "concept": "Two representations may agree under an observation without being identical in every respect. A silhouette discards depth, just as a summary discards source details. Mathematical equivalence requires naming the structures and the mapping that preserves the relevant operations or properties. Homotopy type theory studies equality and equivalence within a formal foundation; it does not make arbitrary matching program outputs prove complete semantic identity. Holographic duality in physics is a specific theoretical correspondence, not a guarantee that a few output checks reconstruct a model’s internal meaning. Use representation changes to ask what information is preserved and what is lost.",
          "metaphor": "",
          "code": "",
          "question": "Two programs return 4 for input 2. What follows?",
          "options": [
            "They agree on that tested input",
            "They are equivalent on all inputs",
            "They have identical implementations"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Their behaviour on untested inputs may differ.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Two different three-dimensional objects cast the same two-dimensional silhouette from one direction.",
              "That observation cannot distinguish their depth.",
              "Add a second view or a depth measurement if depth matters; likewise add discriminating tests when two programs pass the same small example set."
            ],
            "takeaway": "Equality under one observation is weaker than equality under every relevant observation."
          },
          "feedback": [
            "Their behaviour on untested inputs may differ.",
            "One point cannot establish universal behaviour.",
            "Different implementations can produce the same output."
          ],
          "reflection": {
            "prompt": "Construct two functions that pass one test but differ elsewhere.",
            "model": "f(x)=2x and g(x)=x+2 both return 4 at x=2, but at x=3 they return 6 and 5. The second test distinguishes them."
          },
          "references": [
            {
              "title": "Grand Unification And String Theory",
              "url": "/docs/reference/GRAND-UNIFICATION-AND-STRING-THEORY.md"
            },
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 6,
      "title": "Level 6: Production Capstones (Zero to Master)",
      "desc": "Connecting all concepts to build real-world autonomous systems.",
      "bites": [
        {
          "title": "Capstone 1: The Automated Invoice Auditor",
          "concept": "An invoice auditor is an evidence pipeline. First define fields and units, then extract them with source locations, compute arithmetic locally, and compare with the intended business rules. Separate taxes, fees, discounts and rounding rather than hiding them in one “total.” A repair must not fabricate fields to satisfy an equation. A disagreement can come from a source typo, an extraction mistake or a wrong rule. Include missing and ambiguous invoices in evaluation, and report wrong accepted answers as well as rejected ones. A successful synthetic example is a demonstration, not a measured general accuracy rate.",
          "metaphor": "",
          "code": "",
          "question": "The source total is correct but your formula double-counts a fee. What needs repair?",
          "options": [
            "The specification’s fee accounting",
            "The source text",
            "The model until it changes the correct total"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "A faithful extraction can expose a bad check.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A hypothetical invoice lists quantity 3, price 8 and a separate fee 2.",
              "The intended total is 26 if that fee is not already included in the line price.",
              "A specification adding the fee twice would reject the faithful total; inspect the rule rather than forcing the extraction to change."
            ],
            "takeaway": "Audit the specification with counterexamples before auditing real records."
          },
          "feedback": [
            "A faithful extraction can expose a bad check.",
            "The premise gives no reason to alter the source.",
            "Forcing an answer to satisfy the wrong formula damages fidelity."
          ],
          "reflection": {
            "prompt": "List four invoice cases for an independent test set.",
            "model": "A simple correct invoice, a separately charged fee, a discount or rounding boundary, and a missing/ambiguous field. Include both arithmetic inconsistency and a consistent but source-inaccurate record."
          },
          "references": [
            {
              "title": "Natural Language Bridge",
              "url": "/docs/reference/NATURAL-LANGUAGE-BRIDGE.md"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            },
            {
              "title": "Interpreter",
              "url": "/docs/reference/INTERPRETER.md"
            }
          ]
        },
        {
          "title": "Capstone 2: The Self-Healing Data Classifier",
          "concept": "A classifier maps inputs into declared categories. The hard part is often defining boundaries and handling cases that do not fit. Use operational criteria and contrasting examples before adding retries. A label can be valid but wrong, and repeated repair against the same examples can overfit them. Keep evaluation cases separate from development cases. Track coverage, refusal and class-specific errors: a classifier that rejects every difficult input can appear highly accurate on accepted cases while being unhelpful overall. Source context, label order and wording can affect model responses and deserve controlled tests.",
          "metaphor": "",
          "code": "",
          "question": "Accuracy among accepted cases rises after the system rejects half the inputs. What else must be reported?",
          "options": [
            "Only the new accuracy",
            "Coverage and refusal behaviour",
            "The number of animation frames"
          ],
          "ans": 1,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Higher conditional accuracy can conceal lower usefulness or systematic refusal on important cases.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Define a synthetic deadline classifier with within-24-hours, later and unresolved labels.",
              "Test 23-hour, 24-hour, 25-hour and missing-deadline cases.",
              "After improving the wording, evaluate on new paraphrases and dates rather than reusing only those four cases."
            ],
            "takeaway": "Repair success on the development examples is weaker than generalization to new cases."
          },
          "feedback": [
            "The denominator and selection process matter.",
            "Higher conditional accuracy can conceal lower usefulness or systematic refusal on important cases.",
            "UI smoothness is unrelated to classification performance."
          ],
          "reflection": {
            "prompt": "What is a good failure analysis for a classifier?",
            "model": "Separate parsing errors, ambiguous inputs, wrong accepted labels, class imbalance and inconsistent specifications. Examine boundary examples and evaluate repairs on held-out inputs."
          },
          "references": [
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            },
            {
              "title": "Ambiguity Bench",
              "url": "/docs/reference/AMBIGUITY-BENCH.md"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            }
          ]
        },
        {
          "title": "Capstone 3: The Resilient Web Agent",
          "concept": "An agent that reads and acts needs more than a checked answer. It must preserve provenance and authority, restrict what outside text can cause, record the intent before a consequential dispatch, and distinguish confirmed outcomes from lost replies. A deterministic decision rule cannot make a network response reliable. Stable keys and receipts support idempotence within their defined scope, but the exact external service contract still matters. Recovery should reconcile unknown outcomes before repeating actions that could duplicate an effect. A static preview should explain the plan without performing the effects.",
          "metaphor": "",
          "code": "",
          "question": "Why is creating a fresh action ID after every lost reply dangerous?",
          "options": [
            "It guarantees better traceability",
            "It proves the earlier attempt failed",
            "It may bypass duplicate detection and repeat an action that already happened"
          ],
          "ans": 2,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "Stable identity must survive recovery when the same intended action may already have executed.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "An agent prepares a notification, records its action identity and dispatches it.",
              "The response is lost, leaving an uncertain outcome.",
              "Recovery inspects the recorded receipt or external reconciliation path rather than creating a new identity and sending blindly again."
            ],
            "takeaway": "Robustness includes reconnect and uncertainty handling, not just the successful path."
          },
          "feedback": [
            "More IDs can obscure one action’s history.",
            "A lost reply is not evidence of nonexecution.",
            "Stable identity must survive recovery when the same intended action may already have executed."
          ],
          "reflection": {
            "prompt": "Describe three outcome states a resilient agent should distinguish.",
            "model": "Confirmed success, definite failure/non-admission, and unknown outcome. Each requires a different recovery decision and should retain the supporting evidence."
          },
          "references": [
            {
              "title": "Effects",
              "url": "/docs/reference/EFFECTS.md"
            },
            {
              "title": "Execution Pins",
              "url": "/docs/reference/EXECUTION-PINS.md"
            },
            {
              "title": "Development And Use Cases",
              "url": "/docs/reference/DEVELOPMENT-AND-USE-CASES.md"
            }
          ]
        },
        {
          "title": "Capstone 4: Full Neuro-Symbolic Mastery Exam",
          "concept": "Putting Symblic together means choosing the right assurance layer for each part of a task. Types constrain shape; exact computation checks mathematical relations; source evidence supports interpretation; tests probe behaviour; provenance records dependencies; effect contracts govern actions. No layer substitutes for all the others. Build a small complete task, then deliberately construct a candidate that passes a weak check while violating the goal. Strengthen the contract and test whether the stronger version rejects that counterexample without rejecting legitimate cases. This is a repeatable design habit rather than a claim of universal certainty.",
          "metaphor": "",
          "code": "",
          "question": "Which statement best describes a successful checked run?",
          "options": [
            "These inputs and replies passed these checks under this implementation and contract",
            "The task is universally solved",
            "No future test can find a problem"
          ],
          "ans": 0,
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "explanation": "This is a precise claim that can be inspected and extended by further evidence.",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Goal: summarize a source faithfully in a fixed space.",
              "A word-count check accepts an unrelated summary of the right length. Add checks tied to required source claims and evaluate omissions.",
              "Test on new sources and report both unsupported accepted claims and valid summaries incorrectly rejected."
            ],
            "takeaway": "Mastery is being able to explain the guarantee, its assumptions and a counterexample to an overclaim."
          },
          "feedback": [
            "This is a precise claim that can be inspected and extended by further evidence.",
            "One run does not establish universal performance.",
            "New inputs or better requirements can reveal defects."
          ],
          "reflection": {
            "prompt": "Choose a task and state what evidence would change your confidence in its contract.",
            "model": "Name a plausible wrong answer that currently passes, a valid answer currently rejected, a missing source condition, and an independent test or observation capable of revealing each."
          },
          "references": [
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            },
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            },
            {
              "title": "Review 2.3",
              "url": "/docs/reference/REVIEW-2.3.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 7,
      "title": "Level 7: Meaning, language & understanding",
      "desc": "Move from familiar words to explicit interpretations, examples and boundaries.",
      "bites": [
        {
          "title": "Syntax, semantics and pragmatics",
          "concept": "Syntax describes how expressions are formed. Semantics concerns their interpreted content; pragmatics concerns their use in a context. “Can you close the window?” has the form of a question about ability but often functions as a request. A parser can establish a syntactic structure without settling the speaker’s intention. Symblic deliberately combines formal expressions with natural-language asks, so track where each kind of interpretation happens. The formal expression 3+4 has defined computational semantics; a prompt asking whether a response is “appropriate” still needs context and an operational criterion. A richer grammar cannot by itself eliminate that semantic work.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Compare “close the window” in a room and in a browser-support conversation.",
              "The same words refer to different objects and actions.",
              "Supply the domain, referent and desired effect before turning the sentence into an executable action."
            ],
            "takeaway": "One parse is not the same as one universally shared meaning."
          },
          "question": "A request parses unambiguously but uses “it” without a referent. What remains unresolved?",
          "options": [
            "Arithmetic precedence",
            "The referent needed to determine the intended action",
            "Whether the characters are text"
          ],
          "ans": 1,
          "feedback": [
            "Precedence is irrelevant to this ambiguity.",
            "A valid syntactic structure can still depend on missing context.",
            "Recognizing text does not resolve what it refers to."
          ],
          "explanation": "A valid syntactic structure can still depend on missing context.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Why can formalization improve communication without replacing ordinary language?",
            "model": "It exposes selected commitments and relationships for checking, while context, interpretation and negotiation still establish which commitments should be formalized."
          },
          "references": [
            {
              "title": "Study Guide",
              "url": "/docs/reference/STUDY-GUIDE.md"
            },
            {
              "title": "Natural Language Bridge",
              "url": "/docs/reference/NATURAL-LANGUAGE-BRIDGE.md"
            },
            {
              "title": "Research Language",
              "url": "/docs/reference/RESEARCH-LANGUAGE.md"
            }
          ]
        },
        {
          "title": "Operational definitions and boundary cases",
          "concept": "An operational definition states how a concept is identified for a particular task. It turns a broad word into a reproducible decision rule, but can underrepresent the original concept. Defining “helpful” as “under 40 words” is precise yet inadequate. Build a definition with positive cases, negative cases and close boundary cases. Then ask whether those cases cover what matters to the user. When disagreement appears, preserve the examples and distinguish a genuine value disagreement from a different interpretation of the label. A closed answer space helps only if the categories carve the intended distinctions.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Define an on-time delivery using a timezone, deadline and inclusive boundary.",
              "Test a timestamp just before, exactly at and just after the deadline.",
              "Add missing timezone and delayed-recording cases to reveal whether the definition confuses event time with processing time."
            ],
            "takeaway": "Precision should serve the concept, not replace it with an easy-to-measure proxy."
          },
          "question": "A definition is perfectly reproducible but omits the user’s central requirement. Is it adequate?",
          "options": [
            "Yes; reproducibility is sufficient",
            "Yes; all omissions are harmless",
            "No; reproducibility and construct validity are different"
          ],
          "ans": 2,
          "feedback": [
            "Repeatedly computing the wrong construct remains a problem.",
            "An omitted requirement can reverse the task’s meaning.",
            "Check whether the operational rule actually captures the intended concept."
          ],
          "explanation": "Check whether the operational rule actually captures the intended concept.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Operationalize “a complete lab record” without equating it with file size.",
            "model": "Specify required specimen identity, method/version, acquisition conditions, raw data and deviations; include exceptions explicitly and test records missing each required component."
          },
          "references": [
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            },
            {
              "title": "Ambiguity Bench",
              "url": "/docs/reference/AMBIGUITY-BENCH.md"
            },
            {
              "title": "Epistemic Improvements",
              "url": "/docs/reference/EPISTEMIC-IMPROVEMENTS.md"
            }
          ]
        },
        {
          "title": "Ambiguity versus missing information",
          "concept": "Ambiguity permits multiple interpretations of available words. Underspecification leaves some decision unprovided. They can coexist. “Use the earlier sample” is ambiguous if two samples qualify; “choose a suitable threshold” is underspecified without a suitability criterion. A model may confidently fill either gap from its priors. A good clarification distinguishes the alternatives that change the result. Ask the smallest consequential question and preserve the answer as a requirement. Do not treat the model’s own assumption as a later user instruction. The intent interpreter’s retained requirements and assumptions are useful precisely because they keep these sources distinct.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A request says “make the summary shorter” after two summaries.",
              "First identify which summary; then determine the relevant length or intended use if needed.",
              "Record a stated 100-word maximum separately from an assistant-chosen default."
            ],
            "takeaway": "A clarification is valuable when different answers lead to materially different implementations."
          },
          "question": "Two interpretations produce the same output for your example. Does that resolve the ambiguity?",
          "options": [
            "No; find a case on which the interpretations differ",
            "Yes, forever",
            "Yes, if both models sound confident"
          ],
          "ans": 0,
          "feedback": [
            "A contrastive case exposes whether the ambiguity matters.",
            "Agreement on one case can hide different rules.",
            "Confidence is not evidence that interpretations coincide."
          ],
          "explanation": "A contrastive case exposes whether the ambiguity matters.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Write a discriminating question for “use the earlier sample.”",
            "model": "Identify the plausible referents and ask whether “earlier” means collection time, preparation time or the previous sample discussed, using the actual candidate IDs privately."
          },
          "references": [
            {
              "title": "Ambiguity Bench",
              "url": "/docs/reference/AMBIGUITY-BENCH.md"
            },
            {
              "title": "Interpreter",
              "url": "/docs/reference/INTERPRETER.md"
            },
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            }
          ]
        },
        {
          "title": "Compositional meaning and representation",
          "concept": "Compositional approaches explain a structured expression using its parts and how they combine. In arithmetic, the tree for (a+b)×c differs from a+(b×c). In language, grammatical structure similarly changes roles: “the dog chased the cat” differs from its reversal even though the words overlap. Categorical and tensor-based language models explore formal composition, but an algebraic representation must still be connected to evidence about language. A tensor contraction can be computed exactly for supplied numbers without proving that those numbers capture a sentence’s meaning. Separate the representation, composition rule and empirical evaluation.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Compare “all samples passed one test” with “one test was passed by all samples.”",
              "Ask whether the first allows a different test for each sample; make quantifier scope explicit.",
              "Construct two samples with different passing tests to expose the distinction."
            ],
            "takeaway": "Formal composition clarifies structure; choosing an adequate semantic representation remains substantive work."
          },
          "question": "Two sentence embeddings are close. What does that alone establish?",
          "options": [
            "Full logical equivalence",
            "Proximity under the chosen representation and metric",
            "Identical speaker intention"
          ],
          "ans": 1,
          "feedback": [
            "Metric proximity is not a universal logical equivalence relation.",
            "Interpret the distance according to how the representation was built and validated.",
            "Intention requires contextual evidence."
          ],
          "explanation": "Interpret the distance according to how the representation was built and validated.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Give a quantifier-scope counterexample.",
            "model": "Sample A passes test 1 and B passes test 2. Each passes some test, but there is no single test both pass. This separates “for each, there exists” from “there exists, for all.”"
          },
          "references": [
            {
              "title": "Research Language",
              "url": "/docs/reference/RESEARCH-LANGUAGE.md"
            },
            {
              "title": "Quantum Foundations Of Symblic",
              "url": "/docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md"
            },
            {
              "title": "Language 3",
              "url": "/docs/reference/LANGUAGE-3.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 8,
      "title": "Level 8: People, perspective & coordination",
      "desc": "Use formal distinctions to clarify understanding without claiming to measure another person’s inner life.",
      "bites": [
        {
          "title": "Perspective-taking is a revisable model",
          "concept": "Perspective-taking asks what another person may know, believe, value or be experiencing. Those are different questions, and your answer is a hypothesis open to correction. The intersubjectivity essay connects mentalizing, affective empathy and compassion, but its strongest claims about a mathematical solution to empathy exceed what a software type system establishes. Symblic can preserve attributed statements and distinguish reports from interpretations. It cannot certify sincerity or make one person’s experience identical to another’s. A practical learning habit is to state your interpretation tentatively, check it with the person, and preserve their correction rather than forcing them into the original category.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A collaborator misses a meeting. Your first explanation is disinterest.",
              "Alternative explanations include a scheduling conflict or a misunderstood time.",
              "Ask about the event before attributing a motive; record their account as an attributed report rather than pretending to inspect their mental state."
            ],
            "takeaway": "Respectful clarification improves a model of someone; it does not turn the model into the person."
          },
          "question": "Which statement most carefully separates observation from interpretation?",
          "options": [
            "They missed the meeting, therefore they do not care",
            "Their calendar proves their private intentions",
            "They missed the meeting; I do not yet know why"
          ],
          "ans": 2,
          "feedback": [
            "The motive does not follow uniquely from the event.",
            "A calendar records events or plans, not direct access to intention.",
            "This preserves the observation while keeping alternative explanations open."
          ],
          "explanation": "This preserves the observation while keeping alternative explanations open.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "How could a communication tool support empathy without claiming to automate it?",
            "model": "Retain each person’s own wording and corrections, separate facts from attributed feelings and needs, identify unresolved references, and help formulate respectful clarifying questions."
          },
          "references": [
            {
              "title": "Intersubjectivity And Human Communication",
              "url": "/docs/reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md"
            },
            {
              "title": "Epistemic Improvements",
              "url": "/docs/reference/EPISTEMIC-IMPROVEMENTS.md"
            }
          ]
        },
        {
          "title": "Naïve realism and frame mismatch",
          "concept": "Naïve realism, as discussed in the research essay, concerns treating one’s own interpretation as an unmediated view of events and explaining disagreement mainly as another person’s ignorance or bias. A frame is a way of organizing what matters in a situation. One person may discuss task completion while another discusses fairness or feeling heard. Distinguishing frames can explain why a technically correct reply fails to address the concern. It does not mean every claim is equally supported or that facts become subjective. Keep shared observations, differing interpretations and normative disagreements visible so each can be discussed on its own terms.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "“The report was submitted” answers a completion question.",
              "“My contribution was not acknowledged” raises a different issue even if submission is undisputed.",
              "A useful response verifies both the submission fact and the attribution concern instead of treating one as a refutation of the other."
            ],
            "takeaway": "Different frames can coexist with a shared factual record."
          },
          "question": "A factual correction does not resolve a collaborator’s fairness concern. What is a good next step?",
          "options": [
            "Clarify the norm or expectation being disputed",
            "Repeat the correction louder",
            "Conclude facts are irrelevant"
          ],
          "ans": 0,
          "feedback": [
            "Separate the empirical and normative issues so each gets relevant evidence or discussion.",
            "The response still addresses a different question.",
            "Facts remain relevant, but they may not settle the value disagreement."
          ],
          "explanation": "Separate the empirical and normative issues so each gets relevant evidence or discussion.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Translate this into a better requirements discussion.",
            "model": "Separate what the system currently does, what the user expected, and why that outcome matters. Confirm the requirement rather than treating a correct description of current behaviour as satisfaction of the request."
          },
          "references": [
            {
              "title": "Intersubjectivity And Human Communication",
              "url": "/docs/reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md"
            },
            {
              "title": "Epistemic Improvements",
              "url": "/docs/reference/EPISTEMIC-IMPROVEMENTS.md"
            }
          ]
        },
        {
          "title": "Knowing, everyone knowing, common knowledge",
          "concept": "In a finite partition model, an agent’s information groups states it cannot distinguish. The agent knows an event at a state when every state in its current information cell belongs to that event. Everyone knowing is not automatically common knowledge: common knowledge also requires knowing that others know, and further nested levels. Symblic’s knowledge adapter computes this model exactly on supplied finite partitions. The author must still justify which states and information cells represent a real situation. A receipt that a message was sent does not by itself establish that everyone read it, understood it or knows everyone else did.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Worlds are {1,2,3}. Alice’s cells are {1,2},{3}; Bob’s are {1},{2,3}. Event E is {1,2}. At state 1 both know E.",
              "Alice nevertheless considers state 2 possible, where Bob’s cell includes 3 and Bob does not know E.",
              "Thus E is not common knowledge at state 1; the linked common-information cell reaches all three states."
            ],
            "takeaway": "The finite model makes the nesting precise without proving that a real group meets its assumptions."
          },
          "question": "In the example, why is E not common knowledge?",
          "options": [
            "Because neither agent knows E",
            "Because possible chains of others’ information reach a state outside E",
            "Because probabilities must be irrational"
          ],
          "ans": 1,
          "feedback": [
            "At state 1 both individual cells are subsets of E.",
            "Higher-order uncertainty reaches state 3 through the overlapping partitions.",
            "This set-based knowledge calculation needs no irrational probabilities."
          ],
          "explanation": "Higher-order uncertainty reaches state 3 through the overlapping partitions.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Why is a read receipt weaker than common understanding?",
            "model": "It can establish a particular system event, but not necessarily comprehension, agreement, or nested knowledge about everyone else’s comprehension."
          },
          "references": [
            {
              "title": "Knowledge",
              "url": "/docs/reference/KNOWLEDGE.md"
            },
            {
              "title": "Intersubjectivity And Human Communication",
              "url": "/docs/reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md"
            }
          ]
        },
        {
          "title": "Agreement theorems have assumptions",
          "concept": "Aumann-style agreement results concern idealized agents with a common prior and common knowledge of relevant posterior probabilities. They do not say every real disagreement is irrational. People may have different priors, information, event definitions or reasoning limitations. Symblic’s finite announcement process illustrates how public posterior announcements can remove possible states until the process stabilizes. With a common prior under the model’s conditions, final posteriors agree; with different priors, stable disagreement can remain. Convergence of that finite process follows from its shrinking state space, unlike unconstrained model debate. The analogy becomes useful when it tells you which assumption to examine.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Two agents assign different probabilities to the same event.",
              "First check whether they mean the same event, use a common prior and know the relevant information about each other.",
              "If priors differ, a shared message can leave different posteriors without contradicting the theorem."
            ],
            "takeaway": "A theorem is a conditional statement; applying it requires evidence for its premises."
          },
          "question": "Two people disagree after a conversation. Does that refute the agreement theorem?",
          "options": [
            "Yes, any disagreement does",
            "No, because one must be dishonest",
            "No; the theorem’s idealized premises may not hold"
          ],
          "ans": 2,
          "feedback": [
            "The observation does not establish the required premises.",
            "Dishonesty is not the only explanation and cannot be inferred here.",
            "Examine prior, information and common-knowledge assumptions."
          ],
          "explanation": "Examine prior, information and common-knowledge assumptions.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Contrast a finite announcement process with three models debating freely.",
            "model": "The finite model has explicit states, partitions, priors and a monotone elimination rule. Free-form debate does not automatically implement those structures or inherit its convergence result."
          },
          "references": [
            {
              "title": "Knowledge",
              "url": "/docs/reference/KNOWLEDGE.md"
            },
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            },
            {
              "title": "Intersubjectivity And Human Communication",
              "url": "/docs/reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 9,
      "title": "Level 9: Evidence & philosophy of science",
      "desc": "Connect empirical adequacy and the design rationale of Symblic’s evidence records to concrete evidence practices, while distinguishing philosophical proposals from mathematical guarantees.",
      "bites": [
        {
          "title": "Empirical adequacy and the aim of inquiry",
          "concept": "Constructive empiricism, the view Bas van Fraassen defended in The Scientific Image (1980), distinguishes accepting a theory as empirically adequate (true in what it says about observable things and events) from believing every claim it makes about unobservable entities. Empirical adequacy covers all observable phenomena, past, present and future, not only those observed so far, so it works as an open-ended aim: a scientist’s achievement with presently available resources stays provisional. Symblic’s evidence records follow a related design rationale: expose a claim to observation routes that do not share a failure mode, and state what each route actually reaches. This is a philosophical argument about how inquiry should proceed, not a theorem that passing software assertions proves empirical adequacy.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A classifier works on one familiar phrasing.",
              "A new wording, independent source and boundary case expose different possible failures.",
              "Passing them increases the tested scope, but does not establish performance on every future input."
            ],
            "takeaway": "A finite achievement can be real and useful while remaining provisional."
          },
          "question": "How does testing a claim through new observation routes differ from protecting an already passing test set?",
          "options": [
            "It seeks relevant new ways the claim could fail",
            "It declares every new method independent",
            "It treats all evidence as equally strong"
          ],
          "ans": 0,
          "feedback": [
            "The point is to widen meaningful scrutiny rather than preserve a convenient appearance of success.",
            "Distinctness needs a failure-mode argument.",
            "Evidence quality and relevance still require assessment."
          ],
          "explanation": "The point is to widen meaningful scrutiny rather than preserve a convenient appearance of success.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Apply the aim-versus-achievement distinction to your academy progress.",
            "model": "Completing a lesson is a real practice achievement. The ongoing aim is transferable understanding, tested through new examples and applications rather than protected by repeating memorized questions."
          },
          "references": [
            {
              "title": "HPC Foundations",
              "url": "/docs/reference/HPC-FOUNDATIONS.md"
            },
            {
              "title": "Research Adoption",
              "url": "/docs/reference/RESEARCH-ADOPTION.md"
            },
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            },
            {
              "title": "van Fraassen (1980): The Scientific Image",
              "url": "https://doi.org/10.1093/0198244274.001.0001"
            },
            {
              "title": "Stanford Encyclopedia of Philosophy: Constructive Empiricism",
              "url": "https://plato.stanford.edu/entries/constructive-empiricism/"
            }
          ]
        },
        {
          "title": "Distinct frames versus repeated readings",
          "concept": "A distinct observational frame provides a different route by which a claim can be tested. A different instrument, method, sample or observer matters when it exposes failure modes not already covered. Merely renaming a method or running the same model again does not establish independence. Repetition can improve repeatability estimates and is valuable for that purpose. A new instrument may still share a calibration reference, preprocessing pipeline or theoretical assumption with the old one. Map those dependencies explicitly instead of treating diversity as a count of labels.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Ten readings with one biased scale agree closely.",
              "A second scale calibrated against the same faulty reference may share the bias.",
              "A check using a suitably independent reference challenges that common failure mode; document the remaining shared assumptions."
            ],
            "takeaway": "Ask what could fail in one frame while remaining undetected in the other."
          },
          "question": "Three model providers repeat a claim from the same incorrect source. What has their number established?",
          "options": [
            "Three independent sources of factual evidence",
            "Multiple agreeing outputs with a shared source dependency",
            "Truth by majority"
          ],
          "ans": 1,
          "feedback": [
            "Provider diversity does not remove the shared source error.",
            "The dependency is central to interpreting their agreement.",
            "Majority agreement can preserve correlated mistakes."
          ],
          "explanation": "The dependency is central to interpreting their agreement.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Design a second frame for a measurement claim read off a single set of photographs.",
            "model": "Choose a measurement with different preparation or imaging failure modes where feasible, compare definitions and calibration, and explain which artifact the second route could reveal rather than merely adding another image."
          },
          "references": [
            {
              "title": "HPC Foundations",
              "url": "/docs/reference/HPC-FOUNDATIONS.md"
            },
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            },
            {
              "title": "Epistemic Improvements",
              "url": "/docs/reference/EPISTEMIC-IMPROVEMENTS.md"
            },
            {
              "title": "Stegenga and Menon (2017): Robustness and Independent Evidence",
              "url": "https://doi.org/10.1086/692141"
            }
          ]
        },
        {
          "title": "Evidence strength and evidence security",
          "concept": "Evidence strength concerns how an observation supports a claim under a model. Evidential security asks how that support withstands failure of an auxiliary assumption. A result can be repeated precisely but depend heavily on one calibration or interpretation. Triangulation is informative when the new route challenges that dependency. It does not automatically increase confidence by a fixed amount: dependence, reliability and relevance matter. Symblic’s provenance tools can record methods and dependencies, but an author-declared method name is not an independently verified fact about how evidence was obtained. Inspect observed execution metadata separately from declared descriptions.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "An extraction passes a multiplication check.",
              "A source-span comparison challenges whether the numbers were actually read from the document.",
              "A human audit of a held-out sample can challenge systematic source-span or specification mistakes that both automated checks share."
            ],
            "takeaway": "More checks help when they close identifiable routes to error."
          },
          "question": "Which added check most directly challenges a fabricated but arithmetically consistent invoice?",
          "options": [
            "Repeat the multiplication ten times",
            "Count the output’s characters",
            "Compare each extracted field with the source evidence"
          ],
          "ans": 2,
          "feedback": [
            "This repeats the same consistency test.",
            "Character count does not address fabricated values.",
            "It tests the source relationship the arithmetic cannot establish."
          ],
          "explanation": "It tests the source relationship the arithmetic cannot establish.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "How would you document an evidence dependency honestly?",
            "model": "Name the shared source, calibration, model family, preprocessing, or feedback and state whether it was observed in execution or merely declared by the author."
          },
          "references": [
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            },
            {
              "title": "HPC Foundations",
              "url": "/docs/reference/HPC-FOUNDATIONS.md"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            },
            {
              "title": "Stegenga and Menon (2017): Robustness and Independent Evidence",
              "url": "https://doi.org/10.1086/692141"
            }
          ]
        },
        {
          "title": "Falsification, auxiliaries and charitable diagnosis",
          "concept": "A failed prediction challenges a package of assumptions: theory, measurement model, calibration, initial conditions and analysis. It rarely identifies one culprit by itself. The critique documents connect this to the problem of deciding whether an invariant failure came from a model answer or a defective specification. Charity in interpretation means looking for a coherent account worth testing; it does not mean accepting every answer or weakening constraints until they pass. Preserve the failed case, propose competing diagnoses and seek an observation that distinguishes them. This makes debugging an exercise in evidence rather than blame.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A faithful fee extraction fails a total check.",
              "Candidate diagnoses: wrong extracted value, fee already included, or faulty arithmetic implementation.",
              "Inspect the source definition and an independent hand calculation before selecting the repair."
            ],
            "takeaway": "Failure is information about a system of assumptions; diagnosis narrows which one to revise."
          },
          "question": "Which response to a failed invariant preserves the most learning?",
          "options": [
            "Retain the case and compare candidate, specification and source evidence",
            "Assume the model is always wrong",
            "Remove the check immediately"
          ],
          "ans": 0,
          "feedback": [
            "Competing explanations can be tested with discriminating evidence.",
            "The specification or input can be defective.",
            "Removing the check before diagnosis hides the problem."
          ],
          "explanation": "Competing explanations can be tested with discriminating evidence.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Write a three-hypothesis diagnosis for a simulation–measurement mismatch.",
            "model": "The material law is inappropriate; the boundary conditions differ from the experiment; the measurement calibration is biased. Propose a separate check for each instead of tuning parameters indiscriminately."
          },
          "references": [
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            },
            {
              "title": "Intense Critique And Limitations",
              "url": "/docs/reference/INTENSE-CRITIQUE-AND-LIMITATIONS.md"
            },
            {
              "title": "Interpreter",
              "url": "/docs/reference/INTERPRETER.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 10,
      "title": "Level 10: Exact mathematics with honest limits",
      "desc": "Work through real finite adapters, their assumptions and what their witnesses establish.",
      "bites": [
        {
          "title": "Positive-definite quadratics and uniqueness",
          "concept": "For H(x)=½xᵀAx−bᵀx with symmetric positive-definite A, the stationary equation is Ax=b. Positive definiteness means vᵀAv>0 for every nonzero displacement v. If x* solves Ax*=b, expanding H(x*+v) cancels the linear terms and leaves ½vᵀAv, which is positive. That establishes the unique global minimum of this encoded finite problem. Symblic’s adapter checks an exact rational factorization and residual within bounded dimensions and arithmetic. The witness does not establish that A and b correctly represent a physical system or a person’s intended meaning.",
          "code": "let A = [[4, 1], [1, 3]].\nlet b = [1, 2].\nlet receipt = quadratic_minimize(A, b).\nassert quadratic_verify(A, b, receipt).\nshow receipt.x.",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "For A=[[4,1],[1,3]] and b=[1,2], x*=[1/11,7/11].",
              "Check row one: 4/11+7/11=1. Row two: 1/11+21/11=2.",
              "Direct substitution gives H(x*)=−15/22; positive-definite curvature makes every nonzero displacement increase energy."
            ],
            "takeaway": "The theorem’s scope is the supplied finite quadratic."
          },
          "question": "Ax=b has a solution for A=[[-1]], b=[0]. Why does the positive-definite minimizer adapter refuse it?",
          "options": [
            "Zero cannot be represented exactly",
            "The stationary point is a maximum, not the supported unique minimum",
            "Every one-dimensional problem is unsupported"
          ],
          "ans": 1,
          "feedback": [
            "Zero is exact and supported.",
            "H(x)=−x²/2 has negative curvature; stationarity alone does not establish a minimum.",
            "The issue is the matrix condition, not dimension one."
          ],
          "explanation": "H(x)=−x²/2 has negative curvature; stationarity alone does not establish a minimum.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "What should an independent witness verifier recompute?",
            "model": "Input identity and dimensions, matrix symmetry, positive factorization pivots, exact reconstruction, Ax−b and the reported energy. It should not trust Boolean “passed” fields alone."
          },
          "references": [
            {
              "title": "Variational",
              "url": "/docs/reference/VARIATIONAL.md"
            },
            {
              "title": "Examples/Quadratic Witness.Sym",
              "url": "/examples/quadratic-witness.sym"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            }
          ]
        },
        {
          "title": "Projection repairs values; it does not reveal truth",
          "concept": "Affine reconciliation finds a vector satisfying linear constraints while minimizing a weighted squared distance from the original vector. Positive weights define how costly each adjustment is. With independent constraint rows, the finite problem has a unique solution under the adapter’s assumptions. The output is a repair: the original vector violated a constraint and was changed. Neither the constraint nor the weights become scientifically justified merely because the solve is exact. Keep original values, residuals and movement cost, and choose a task-specific acceptance bound. Large movement can indicate bad data or a bad constraint even when the optimization is mathematically valid.",
          "code": "let repair = reconcile([40, 35, 30], [[1, 1, 1]], [100]).\nassert repair.value = [115/3, 100/3, 85/3].\nassert repair.moved = 25/3.\nassert not repair.satisfied.",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Original values [40,35,30] sum to 105; require a total of 100 with equal weights.",
              "The minimum squared adjustment subtracts 5/3 from each, giving [115/3,100/3,85/3].",
              "The original residual is 5 and movement cost is 3×(5/3)²=25/3. The original was not already satisfied."
            ],
            "takeaway": "Do not silently replace measurements with reconciled values and call them observations."
          },
          "question": "A projection returns feasible values with a large movement cost. What follows?",
          "options": [
            "The original measurements were definitely wrong",
            "The new values are independently measured",
            "The encoded repair was computed; acceptance still needs a justified movement criterion"
          ],
          "ans": 2,
          "feedback": [
            "The constraint or weights might be wrong.",
            "The output is derived, not newly observed.",
            "Feasibility and optimization do not decide whether the repair is appropriate."
          ],
          "explanation": "Feasibility and optimization do not decide whether the repair is appropriate.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Why do weights require units and interpretation?",
            "model": "They define the objective and tradeoff among coordinate changes. Scaling coordinates or changing weights changes what “closest” means; weights are not automatically inverse measurement variances."
          },
          "references": [
            {
              "title": "Projection",
              "url": "/docs/reference/PROJECTION.md"
            },
            {
              "title": "Variational",
              "url": "/docs/reference/VARIATIONAL.md"
            }
          ]
        },
        {
          "title": "Optimal transport sees what a median loses",
          "concept": "A median summarizes location but discards spread. The finite one-dimensional Wasserstein-1 distance compares normalized numeric distributions by the effort needed to move probability mass along their common coordinate axis. In one dimension it is the integral of the absolute difference between cumulative distributions. Symblic’s exact adapter computes that finite sum for supplied rational coordinates and masses. It normalizes each distribution independently, so it compares shape and location, not total population size. The result has the coordinate’s unit. It does not automatically compare textual meaning or establish that one distribution is correct.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A has equal mass at 0,1,2 seconds; B has all mass at 1 second. Both medians are 1.",
              "Move one third of the mass from 0 to 1 and one third from 2 to 1.",
              "Total transport cost is 1/3+1/3=2/3 seconds."
            ],
            "takeaway": "An exact metric is meaningful only for a justified shared coordinate and normalization."
          },
          "question": "If every mass in A is multiplied by ten, what happens to this normalized W1 distance?",
          "options": [
            "It stays the same",
            "It becomes ten times larger",
            "Its units become mass"
          ],
          "ans": 0,
          "feedback": [
            "Relative mass distribution is unchanged.",
            "Independent normalization removes that overall scaling.",
            "The distance retains the coordinate unit."
          ],
          "explanation": "Relative mass distribution is unchanged.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Why should seconds and milliseconds be converted before comparison?",
            "model": "The algorithm sees numbers, not hidden unit intentions. Without conversion it compares different coordinate scales and returns a misleading distance."
          },
          "references": [
            {
              "title": "Transport",
              "url": "/docs/reference/TRANSPORT.md"
            },
            {
              "title": "Physics And Advanced Mathematics",
              "url": "/docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md"
            }
          ]
        },
        {
          "title": "Discrete optimization, ties and witnesses",
          "concept": "A finite optimization problem specifies candidates, an objective and constraints. A correct minimum can have several equally good witnesses. Uniqueness needs proof or an explicit deterministic tie rule; it does not follow from calling an objective an energy or Hamiltonian. Bounded exhaustive enumeration can certify a minimum for its finite domain, while a heuristic search may find only a candidate. A resource limit restricts the domain or work, not the mathematical existence of a solution. Separate a feasible witness, a proof of optimality and evidence that the encoded objective matches the real task.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "For x in {−1,+1}, minimize E(x)=0.",
              "Both candidates achieve the minimum, so the ground state is degenerate.",
              "A rule choosing −1 first makes the selected output deterministic without making the mathematical optimum unique."
            ],
            "takeaway": "Deterministic selection and unique optimization are different properties."
          },
          "question": "Two candidates tie for minimum cost. Which statement is accurate?",
          "options": [
            "The optimization is invalid",
            "A documented tie rule can choose reproducibly among multiple optima",
            "Physics guarantees one must secretly be better"
          ],
          "ans": 1,
          "feedback": [
            "Multiple optima are legitimate.",
            "The selection rule adds a deterministic convention without changing the objective.",
            "Degeneracy is possible; uniqueness must be established."
          ],
          "explanation": "The selection rule adds a deterministic convention without changing the objective.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "How would you assess an “optimal” scheduler result?",
            "model": "Inspect the candidate domain, constraints, objective, search method and optimality evidence; then check whether omitted real-world requirements make that objective inadequate."
          },
          "references": [
            {
              "title": "Discrete",
              "url": "/docs/reference/DISCRETE.md"
            },
            {
              "title": "Quantum Determinism Analysis",
              "url": "/docs/reference/QUANTUM-DETERMINISM-ANALYSIS.md"
            },
            {
              "title": "Spec",
              "url": "/docs/reference/SPEC.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 11,
      "title": "Level 11: Quantum probability without mystification",
      "desc": "Learn projections, order effects and the limits of quantum-inspired language.",
      "bites": [
        {
          "title": "Deterministic evolution and probabilistic outcomes",
          "concept": "In a specified quantum model, unitary evolution maps an initial state to a later state deterministically. Measurement probabilities are obtained from the state and measurement model. Computing those probabilities deterministically is different from claiming a particular observed outcome is determined by the computation. Classical software can calculate a quantum model without becoming quantum hardware. Symblic’s finite rational operator adapter is narrower still: it uses real vectors and orthogonal projectors, without general complex amplitudes or physical measurements. Claims in the exploratory Q-Symblic essays about eliminating all neural randomness should therefore be treated as proposals or overextensions, not installed guarantees.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A model assigns equal probability to two measurement outcomes.",
              "Recomputing the probabilities can return exactly 1/2 and 1/2 each time.",
              "That stable probability calculation does not predict which one outcome a particular physical trial will record."
            ],
            "takeaway": "Determinism of a calculation and certainty about an empirical outcome are separate."
          },
          "question": "An exact calculation returns P(A)=1/2. What does this mean?",
          "options": [
            "A will occur on exactly every second trial",
            "The model has proved the hardware is correct",
            "The supplied model assigns probability one half to A"
          ],
          "ans": 2,
          "feedback": [
            "Probability does not impose an alternating sequence.",
            "Physical validation requires evidence outside the calculation.",
            "Interpret the result conditionally on the state and measurement assumptions."
          ],
          "explanation": "Interpret the result conditionally on the state and measurement assumptions.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Why is a model’s hidden activation vector not automatically a quantum state?",
            "model": "A vector alone does not supply a validated quantum-state interpretation, normalization, measurement operators or physical mechanism. Those would require an explicit model and evidence."
          },
          "references": [
            {
              "title": "Quantum Foundations Of Symblic",
              "url": "/docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md"
            },
            {
              "title": "Quantum Determinism Analysis",
              "url": "/docs/reference/QUANTUM-DETERMINISM-ANALYSIS.md"
            },
            {
              "title": "Operators",
              "url": "/docs/reference/OPERATORS.md"
            }
          ]
        },
        {
          "title": "Noncommuting projections and question order",
          "concept": "Two operations commute when applying A then B has the same result as B then A. For matrices the commutator is AB−BA. In the projector model of question order, a yes answer projects a state onto a subspace and a no answer onto its orthogonal complement. Sequence probability is the squared length remaining after the ordered projections, divided by the original squared length. Noncommuting projectors can produce order effects for suitable states. This is an explicit mathematical model, not a claim that every observed wording effect is quantum. The actual adapter checks symmetry and idempotence of the supplied projectors.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Let A project onto the horizontal axis and B onto the line through (1,1); use state (2,1).",
              "A asked first gives yes probability 4/5.",
              "If B is asked first and both B outcomes are included, A-yes probability becomes 1/2. The question label A is held fixed while order changes."
            ],
            "takeaway": "Compare the same question across orders; unequal P(A|B) and P(B|A) alone is not an order effect."
          },
          "question": "P(A|B) differs from P(B|A). Does that alone demonstrate noncommuting question order?",
          "options": [
            "No; ordinary conditional probabilities have different denominators",
            "Yes",
            "Yes, if both are rational"
          ],
          "ans": 0,
          "feedback": [
            "Classical probabilities can have unequal conditionals with the same joint numerator.",
            "The comparison is not the same question under reversed order.",
            "Rationality has no bearing on that distinction."
          ],
          "explanation": "Classical probabilities can have unequal conditionals with the same joint numerator.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "How would you design an empirical order test?",
            "model": "Compare matched groups receiving A-then-B versus B-then-A, keep question wording and population comparable, and compare the same labeled outcomes with sampling uncertainty."
          },
          "references": [
            {
              "title": "Operators",
              "url": "/docs/reference/OPERATORS.md"
            },
            {
              "title": "Examples/14 Question Order.Sym",
              "url": "/examples/14-question-order.sym"
            },
            {
              "title": "Quantum Foundations Of Symblic",
              "url": "/docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md"
            }
          ]
        },
        {
          "title": "A prediction can test a quantum-cognition model",
          "concept": "A useful model makes predictions that could fail. For the particular two-question projector model documented in Symblic, the QQ equality says the total probability of different answers is the same across the two orders when outcomes are labeled consistently. The cited Wang and colleagues research examined this prediction in survey and experimental data. The result concerns a probability model of judgments, not evidence that the brain is literally a quantum computer. Passing the equality is not sufficient to establish the entire model; other models or special cases can also fit. A clear violation challenges the stated assumptions for those data.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Compute P(A yes,B no)+P(A no,B yes) in the A-first group.",
              "Compute the corresponding differently answered outcomes in the B-first group.",
              "Compare the totals with uncertainty and the model assumptions; do not compare mismatched question labels."
            ],
            "takeaway": "Distinguish model prediction, empirical fit and proposed physical explanation."
          },
          "question": "Data satisfy QQ equality. Which conclusion is warranted?",
          "options": [
            "Every aspect of human cognition is quantum",
            "The data are consistent with this prediction, with further model tests still needed",
            "Classical explanations are logically impossible"
          ],
          "ans": 1,
          "feedback": [
            "One prediction cannot establish that broad mechanism.",
            "Consistency is informative but weaker than unique confirmation.",
            "The comparison does not exclude every alternative explanation."
          ],
          "explanation": "Consistency is informative but weaker than unique confirmation.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "What would make this lesson an example of testing a claim through several distinct routes?",
            "model": "Compare predictions across different question pairs, populations and measurement procedures, identify shared assumptions, and seek outcomes that could distinguish the projector account from alternatives."
          },
          "references": [
            {
              "title": "Operators",
              "url": "/docs/reference/OPERATORS.md"
            },
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            },
            {
              "title": "Wang et al. (2014): original question-order study",
              "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4084470/"
            }
          ]
        },
        {
          "title": "ZX calculus, no-cloning and category mistakes",
          "concept": "ZX calculus is a diagrammatic language for quantum processes. Soundness says derived equalities preserve the intended interpretation; completeness says specified semantic equalities can be derived within a stated fragment. Neither word alone means every arbitrary rewrite strategy terminates at one unique diagram. The no-cloning theorem concerns arbitrary unknown quantum states. Linear resource types in programming are an independently specified way to restrict copying or reuse; invoking no-cloning does not automatically make a classical runtime race-free. The research essays make these connections as architectural inspiration, but actual guarantees require defined rules and evidence about the implemented system.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A graph-rewrite system has rules that can be applied in both directions.",
              "Even if it can derive every valid equality in a fragment, a naive strategy may loop.",
              "To claim a deterministic normalizer, specify a terminating strategy and prove or test its relevant properties separately."
            ],
            "takeaway": "A theorem does not transfer to a different system merely because the vocabulary is similar."
          },
          "question": "A calculus is complete for a fragment. Does this alone prove every rewrite order reaches the same normal form?",
          "options": [
            "Yes",
            "Yes, if the diagrams are colourful",
            "No; confluence and termination are separate properties"
          ],
          "ans": 2,
          "feedback": [
            "Completeness concerns derivability of equalities, not arbitrary algorithm behaviour.",
            "Visual notation supplies no proof.",
            "State the fragment and the normalization algorithm before making a canonical-form claim."
          ],
          "explanation": "State the fragment and the normalization algorithm before making a canonical-form claim.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "What would be required to claim a linear type prevents a specific double-use bug?",
            "model": "An implemented typing rule, a definition of resource consumption, coverage of aliasing and escape paths, and evidence that the runtime respects those rules. A physics analogy is insufficient."
          },
          "references": [
            {
              "title": "Quantum Determinism Analysis",
              "url": "/docs/reference/QUANTUM-DETERMINISM-ANALYSIS.md"
            },
            {
              "title": "Quantum Foundations Of Symblic",
              "url": "/docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md"
            },
            {
              "title": "Language 3",
              "url": "/docs/reference/LANGUAGE-3.md"
            },
            {
              "title": "Backens: completeness for stabilizer quantum mechanics",
              "url": "https://arxiv.org/abs/1307.7025"
            }
          ]
        }
      ]
    },
    {
      "lvl": 12,
      "title": "Level 12: Physics connections & mathematical scope",
      "desc": "Understand the motivating ideas and learn where an analogy stops supporting a claim.",
      "bites": [
        {
          "title": "From a weak form to a finite energy problem",
          "concept": "The energy method for the vorticity equation starts with a differential equation relating a potential to a source. Multiplying by a test function and integrating by parts moves a derivative and exposes boundary terms. Those terms vanish only under appropriate test-function and boundary conditions. The resulting energy argument motivates a finite quadratic after discretization. It does not automatically establish continuum existence and uniqueness for every domain or boundary choice. Coefficient positivity, coercivity and nullspaces matter. The current variational contract explicitly limits its guarantee to the supplied finite positive-definite matrix, avoiding a leap from algebra to an unproved physical interpretation.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "For ∇·(y∇φ)=Ω, integration by parts with vanishing boundary contribution gives ∫y∇v·∇φ=−∫vΩ.",
              "The source sign must be retained when assembling the discrete right-hand side.",
              "A pure Neumann problem can retain a constant nullspace; selecting a reference in a finite system does not by itself settle every continuum function-space issue."
            ],
            "takeaway": "The bridge from PDE to matrix is part of the scientific argument, not something the solver infers."
          },
          "question": "An exact solver verifies Ax=b. Which step still needs separate justification for a PDE application?",
          "options": [
            "The derivation of A and b from the equation, units and boundary conditions",
            "Whether exact fractions can represent integers",
            "Whether matrix rows can be displayed"
          ],
          "ans": 0,
          "feedback": [
            "The algebra verifies the encoded problem, not its physical assembly or discretization error.",
            "Integers are already representable.",
            "Display is unrelated to the model-to-equation connection."
          ],
          "explanation": "The algebra verifies the encoded problem, not its physical assembly or discretization error.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Why should the weak-form boundary term be shown in a derivation?",
            "model": "It records the conditions under which it vanishes or contributes a load. Silently dropping it can change the boundary-value problem and its solution."
          },
          "references": [
            {
              "title": "Variational",
              "url": "/docs/reference/VARIATIONAL.md"
            },
            {
              "title": "Physics And Advanced Mathematics",
              "url": "/docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md"
            },
            {
              "title": "Vorticity Construction",
              "url": "/docs/reference/VORTICITY-CONSTRUCTION.md"
            }
          ]
        },
        {
          "title": "Energy bounds do not settle every regularity question",
          "concept": "An energy estimate controls the quantity named by its norm under stated conditions. It may not control sharper quantities such as gradients or pointwise behaviour. Tao’s work on an averaged Navier–Stokes equation illustrates why energy structure alone is not enough to transfer a regularity conclusion to the original equation. Some local research prose overstates related claims as general fluid-computation or AI-convergence theorems. Read the original theorem’s equation and assumptions before borrowing its conclusion. In software, an analogous discipline is to ask exactly what a decreasing loss or bounded counter controls, rather than treating it as evidence about every desirable property.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A program’s total call count is bounded.",
              "That controls one resource but does not bound semantic error in an accepted answer.",
              "Likewise, a bound on one mathematical norm cannot be silently substituted for a bound on every other norm."
            ],
            "takeaway": "A bound is only as broad as its definition and the argument linking it to the desired outcome."
          },
          "question": "A scalar error score decreases while source fidelity worsens. What does that reveal?",
          "options": [
            "All decreasing scores are meaningless",
            "The score does not adequately capture the intended objective",
            "A fluid theorem guarantees eventual correction"
          ],
          "ans": 1,
          "feedback": [
            "A well-chosen score can still be useful within its scope.",
            "The metric can reward an irrelevant simplification or omit a required distinction.",
            "No theorem has been supplied connecting that score to source fidelity."
          ],
          "explanation": "The metric can reward an irrelevant simplification or omit a required distinction.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "How would you read a surprising mathematical claim in a research essay?",
            "model": "Locate the primary theorem, identify the exact equation or system, domain and hypotheses, then compare those with the essay’s application. Mark any unproved transfer as a proposal or analogy."
          },
          "references": [
            {
              "title": "Physics And Advanced Mathematics",
              "url": "/docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md"
            },
            {
              "title": "Grand Unification And String Theory",
              "url": "/docs/reference/GRAND-UNIFICATION-AND-STRING-THEORY.md"
            },
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            },
            {
              "title": "Tao: the averaged equation and scope of the result",
              "url": "https://terrytao.wordpress.com/2014/02/04/finite-time-blowup-for-an-averaged-three-dimensional-navier-stokes-equation/"
            }
          ]
        },
        {
          "title": "Symmetry and conservation are specific relationships",
          "concept": "Noether-type reasoning connects continuous symmetries of an action with conserved quantities under appropriate assumptions. Time-translation symmetry relates to energy conservation; spatial translation to momentum. In numerical mechanics, symplectic methods preserve a geometric structure and can have useful long-time behaviour, but do not generally preserve the exact energy at every finite step. These are precise mathematical properties. Naming a software requirement an “invariant” does not make it a Noether charge, and conserving a number does not prevent every form of specification gaming. A meaningful transfer would define the state, transformation, preserved structure and intended interpretation.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A bookkeeping program preserves a total of 100 while moving values between two accounts.",
              "That sum invariant does not establish that transfers were authorized or assigned to the correct owners.",
              "Add the relevant identity and authority checks; conservation is one condition among several."
            ],
            "takeaway": "A preserved quantity can be useful without being a complete account of correctness."
          },
          "question": "A workflow preserves total funds but transfers to the wrong recipient. What failed?",
          "options": [
            "Conservation necessarily failed",
            "Mathematics cannot describe sums",
            "A separate identity or authorization requirement"
          ],
          "ans": 2,
          "feedback": [
            "The total may be unchanged while the action is wrong.",
            "Arithmetic is not the missing piece here.",
            "The preserved sum does not encode the recipient requirement."
          ],
          "explanation": "The preserved sum does not encode the recipient requirement.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "What would make a proposed physical analogy testable?",
            "model": "Define the corresponding variables and operations, derive a prediction or invariant, state assumptions, and identify a case that could falsify the proposed correspondence."
          },
          "references": [
            {
              "title": "Physics And Advanced Mathematics",
              "url": "/docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md"
            },
            {
              "title": "Effects",
              "url": "/docs/reference/EFFECTS.md"
            }
          ]
        },
        {
          "title": "Coarse-graining, holography and what gets lost",
          "concept": "Coarse-graining replaces detailed information with a representation suited to a larger scale or a particular question. A useful summary preserves selected relations, not every detail. Renormalization in physics is a specific framework for relating descriptions across scales; holographic dualities are specific theoretical correspondences. The repository’s proposals borrow these ideas for context compression and representation. They do not establish an implemented exact semantic duality. To evaluate a summary, list the downstream questions it must answer, test preserved distinctions and retain a route to the original source. Compression can erase the exception that decides a later task.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A source says “all samples passed except B after heating.”",
              "A summary “the samples passed” loses the exception and condition.",
              "Test downstream questions about B and heating, not only whether the summary sounds fluent or is short."
            ],
            "takeaway": "A lossy representation must be judged against the questions it is intended to support."
          },
          "question": "Two summaries have the same length. Which is more adequate?",
          "options": [
            "The one preserving the task-relevant claims, exceptions and provenance",
            "The one using more advanced terminology",
            "They are necessarily equivalent"
          ],
          "ans": 0,
          "feedback": [
            "Length is a constraint; retained meaning is a separate objective.",
            "Vocabulary does not guarantee preserved information.",
            "Equal size says little about content."
          ],
          "explanation": "Length is a constraint; retained meaning is a separate objective.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "What evidence would support a context-compression method?",
            "model": "Held-out downstream tasks, tests for lost exceptions and references, comparisons with the full context, source-fidelity checks, and measured cost reductions under a stated protocol."
          },
          "references": [
            {
              "title": "Physics And Advanced Mathematics",
              "url": "/docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md"
            },
            {
              "title": "Grand Unification And String Theory",
              "url": "/docs/reference/GRAND-UNIFICATION-AND-STRING-THEORY.md"
            },
            {
              "title": "Research Language",
              "url": "/docs/reference/RESEARCH-LANGUAGE.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 13,
      "title": "Level 13: Reading research & testing claims",
      "desc": "Turn surveys, critiques and benchmark receipts into carefully bounded conclusions.",
      "bites": [
        {
          "title": "Agreement, correctness and shared mistakes",
          "concept": "Agreement measures how often answers coincide under a defined equivalence rule. Correctness compares them with an appropriate reference or criterion. They are different axes: everyone can agree on a wrong answer, and diverse wording can express the same correct result. Report the unit of analysis and the treatment of invalid or missing answers. Canonical values can remove irrelevant formatting differences but do not equate arbitrary paraphrases or verify truth. The agreement survey’s empirical numbers have different verification labels; treat unconfirmed summaries as leads, not established measurements. For your own evaluation, retain correct agreement, wrong agreement, disagreement and refusal separately.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Four models give the same wrong label on one item and four correct labels on another.",
              "Overall agreement is perfect, but correctness is only one half in this toy example.",
              "Separate the two outcomes so consensus cannot hide systematic error."
            ],
            "takeaway": "Consensus is an observable pattern, not a substitute for an external criterion."
          },
          "question": "Canonicalization raises exact-match agreement by removing formatting differences. What must still be checked?",
          "options": [
            "Nothing; truth follows from equal bytes",
            "Whether the agreed values are correct and the equivalence rule is appropriate",
            "Whether the answers use the same font"
          ],
          "ans": 1,
          "feedback": [
            "Equal bytes can encode the same wrong answer.",
            "Representation agreement can improve without any change in underlying factual accuracy.",
            "Font is irrelevant to semantic or factual validity."
          ],
          "explanation": "Representation agreement can improve without any change in underlying factual accuracy.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Design a small agreement report.",
            "model": "State cases, models and versions, equivalence rule, invalid/missing replies, correct and wrong agreement, per-case outcomes, and the independent criterion used to score correctness."
          },
          "references": [
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            },
            {
              "title": "Reinforcements/Benchmark Review",
              "url": "/docs/reference/reinforcements/benchmark-review.md"
            }
          ]
        },
        {
          "title": "The denominator and the unit of independence",
          "concept": "Evaluation conclusions depend on what counts as a trial. Pairwise comparisons from the same statement share that statement and are not automatically independent samples. Treating every pair as independent can understate uncertainty. A statement-level bootstrap or a model suited to the dependency structure can better reflect the sampling design. Similarly, choosing a favorable subset of models after viewing results changes the interpretation: report it as exploratory. The local results documents carefully distinguish finite conformance checks, development trials and model-performance evidence. Preserve those distinctions when reading headline percentages.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "With four model answers to one statement, there are six answer pairs.",
              "Those six comparisons all depend on the same statement and overlapping answers.",
              "Six matching pairs therefore do not equal six independently sampled tasks."
            ],
            "takeaway": "The statistical unit should match the way evidence was generated."
          },
          "question": "A report drops a weak model after seeing the results. How should the improved percentage be presented?",
          "options": [
            "As the preregistered overall result",
            "As proof that the excluded model never matters",
            "As a post-hoc subset result alongside the full set"
          ],
          "ans": 2,
          "feedback": [
            "That would misstate the selection process.",
            "The observation is specific to the evaluated cases.",
            "The subset can be informative if its exploratory status and denominator are visible."
          ],
          "explanation": "The subset can be informative if its exploratory status and denominator are visible.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Why separate fake-provider tests from live-model benchmarks?",
            "model": "Fake tests can validate deterministic control flow, recovery and contracts. They do not measure whether a real model understands unseen inputs or how long it takes."
          },
          "references": [
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            },
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            },
            {
              "title": "Ambiguity Bench",
              "url": "/docs/reference/AMBIGUITY-BENCH.md"
            }
          ]
        },
        {
          "title": "Counterexamples, vacuity and specification gaming",
          "concept": "A check is vacuous for an intended purpose when passing it fails to constrain what actually matters. Empty lists can satisfy universal conditions; fabricated matching numbers can satisfy arithmetic; unrelated text can satisfy a length bound. Actively search for such counterexamples. Then strengthen the contract and verify that legitimate cases are not excluded. Rewarding a model for passing the same weak checks can teach shortcuts rather than the intended task. The HPC research roadmap discusses verifiable rewards, but a deterministic reward is not automatically ungameable. Independent evaluation and source-grounding remain necessary.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Check: every extracted item has a positive price.",
              "An empty item list passes the universal statement.",
              "If the source contains items, add a justified completeness requirement and a source correspondence test; do not just require nonempty lists for sources that may truly be empty."
            ],
            "takeaway": "A useful counterexample tests both acceptance of bad answers and rejection of good ones."
          },
          "question": "How can a model maximize a perfectly deterministic reward while failing the task?",
          "options": [
            "Exploit omissions in the reward’s definition",
            "Determinism makes that impossible",
            "Only by changing the hardware"
          ],
          "ans": 0,
          "feedback": [
            "The reward can be computed correctly while measuring an inadequate proxy.",
            "Determinism concerns repeatable computation, not alignment with intent.",
            "A loophole can exist entirely within the stated rules."
          ],
          "explanation": "The reward can be computed correctly while measuring an inadequate proxy.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Give a non-vacuity test for a source-summary task.",
            "model": "Use an irrelevant summary of valid length, one omitting the central exception, and a faithful summary. Check that the first two fail for content reasons while the faithful one can pass."
          },
          "references": [
            {
              "title": "Critique And Limitations",
              "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md"
            },
            {
              "title": "Intense Critique And Limitations",
              "url": "/docs/reference/INTENSE-CRITIQUE-AND-LIMITATIONS.md"
            },
            {
              "title": "HPC Foundations",
              "url": "/docs/reference/HPC-FOUNDATIONS.md"
            }
          ]
        },
        {
          "title": "Novelty, prior art and measured contribution",
          "concept": "A research contribution can be a new theorem, an implementation, an integration, an evaluation or a design method. These require different evidence. Exact rational arithmetic, typed contracts, declarative logic and quadratic optimization have established histories. Combining them in Symblic may offer a useful workflow without making each ingredient novel mathematics. The prior-art and compendium documents contain broad comparisons and proposed breakthroughs; read them alongside the narrower results and adapter contracts. A convincing contribution states the baseline, the changed mechanism, the measured outcome and the limits. Future directions should remain separate from available capabilities.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Claim A: a new uniqueness theorem for all natural-language intent. Claim B: a bounded integration of an established quadratic solver with a separately checked witness.",
              "The implementation and tests support the scope of B.",
              "To support A would require a formal definition of intent, assumptions and a proof reaching that much broader conclusion."
            ],
            "takeaway": "A bounded, well-supported contribution is more informative than an expansive label."
          },
          "question": "Which evidence supports a claim of improved task performance?",
          "options": [
            "A list of impressive theoretical analogies",
            "A matched evaluation against relevant baselines with failures, costs and scope reported",
            "The number of source files"
          ],
          "ans": 1,
          "feedback": [
            "Analogies can motivate a design but do not measure its effect.",
            "The evaluation connects a concrete change to observed outcomes.",
            "File count does not establish performance or novelty."
          ],
          "explanation": "The evaluation connects a concrete change to observed outcomes.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Write a careful contribution statement for an adapter.",
            "model": "It integrates a specified established method into the kernel with explicit domain/resource limits, a documented interface and independent checks on selected cases. State what those checks do not establish."
          },
          "references": [
            {
              "title": "Prior Art",
              "url": "/docs/reference/PRIOR-ART.md"
            },
            {
              "title": "Symblic Breakthrough Compendium",
              "url": "/docs/reference/SYMBLIC-BREAKTHROUGH-COMPENDIUM.md"
            },
            {
              "title": "The Overall Breakthrough",
              "url": "/docs/reference/THE-OVERALL-BREAKTHROUGH.md"
            },
            {
              "title": "Research Adoption",
              "url": "/docs/reference/RESEARCH-ADOPTION.md"
            },
            {
              "title": "Review 2.3",
              "url": "/docs/reference/REVIEW-2.3.md"
            }
          ]
        }
      ]
    },
    {
      "lvl": 14,
      "title": "Level 14: Build, inspect & transfer",
      "desc": "Use current code-generation and recovery contracts in a final practical synthesis.",
      "bites": [
        {
          "title": "Small spec units and fresh context",
          "concept": "A spec sheet decomposes an output into units with explicit contracts, dependencies and examples. Each model sees the shared conventions and the already tested code it needs. The compiler generates the ask-and-check program deterministically; the model proposes each unit’s code. Tests include earlier pieces so name collisions or accidental redefinitions can be detected. This makes failure localization easier, but a unit can still pass the listed examples and fail elsewhere. Decomposition should follow meaningful interfaces and state transitions, not arbitrary word counts. Keep independent whole-system tests for behaviour spanning units.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A movement unit depends on a previously accepted collision checker.",
              "Show the actual checker interface and specify whether movement tests the old or new state.",
              "Test the assembled pieces, including a case that distinguishes those two interpretations."
            ],
            "takeaway": "Small context works when dependencies and conventions are complete."
          },
          "question": "Why test a new unit with all earlier code pieces rather than only its named dependencies?",
          "options": [
            "To prove every future input correct",
            "To make the model remember an entire chat",
            "To detect integration conflicts such as redefining an earlier function"
          ],
          "ans": 2,
          "feedback": [
            "Finite examples do not prove universal correctness.",
            "The method uses explicit fresh context rather than an unbounded conversation.",
            "The assembled file contains all pieces; hidden conflicts can arise outside the direct dependency list."
          ],
          "explanation": "The assembled file contains all pieces; hidden conflicts can arise outside the direct dependency list.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Write the essential parts of a small unit specification.",
            "model": "Function/interface, inputs and outputs, state conventions, exact dependencies, ordered steps where needed, allowed side effects, boundary examples and expected results."
          },
          "references": [
            {
              "title": "Spec Sheets",
              "url": "/docs/reference/SPEC-SHEETS.md"
            },
            {
              "title": "Js",
              "url": "/docs/reference/JS.md"
            },
            {
              "title": "Kits/Tetris/Sheets/Tetris.Sheet",
              "url": "/kits/tetris/sheets/tetris.sheet.md"
            }
          ]
        },
        {
          "title": "A sandboxed test is still a finite test",
          "concept": "The JavaScript adapter executes candidate code in isolated cases and compares returned JSON values with expected results. The operating-system sandbox is the security boundary; a language-level VM context alone is not. Deterministic time and disabled randomness help make cases reproducible, but resource limits can still cause a timeout. A pass says the listed calls returned the listed values under that engine and setup. It does not establish behaviour on untested calls, general safety of the algorithm, or the correctness of the reference examples. Test the reference against the specification, not only candidates against the reference.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "A function passes add(2,3)=5 and add(−1,1)=0.",
              "An implementation special-casing those inputs would pass too.",
              "Add property and boundary tests appropriate to the contract, and inspect whether the reference itself implements the intended operation."
            ],
            "takeaway": "The sandbox limits execution; test design determines what behaviour is checked."
          },
          "question": "A candidate times out on a case. How should the test treat it?",
          "options": [
            "As a failed case under the configured resource limit",
            "As a pass with a missing value",
            "As proof of mathematical impossibility"
          ],
          "ans": 0,
          "feedback": [
            "Report the timeout and conditions; near-limit runtime can depend on load.",
            "No expected result was obtained.",
            "A timeout is an execution observation, not a nonexistence theorem."
          ],
          "explanation": "Report the timeout and conditions; near-limit runtime can depend on load.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Why include the JavaScript engine version in identity?",
            "model": "Engine semantics and behaviour can affect results. Reproducibility needs the actual execution contract, not only the candidate source text."
          },
          "references": [
            {
              "title": "Js",
              "url": "/docs/reference/JS.md"
            },
            {
              "title": "Execution Pins",
              "url": "/docs/reference/EXECUTION-PINS.md"
            },
            {
              "title": "Spec Sheets",
              "url": "/docs/reference/SPEC-SHEETS.md"
            }
          ]
        },
        {
          "title": "Deterministic selection and preserving good work",
          "concept": "Parallel candidate search can select reproducibly from a fixed set of replies using a declared ranking rule. The current spec-sheet search prefers the passing candidate with the fewest attempts, then the lowest index, rather than the first network response. That removes arrival order from selection given those replies; it does not make fresh model generation identical. Incremental rebuilds can keep previously accepted units and retest them against the current sheet. If a retained unit fails changed tests, the build should stop rather than silently treating historical acceptance as current evidence. Track source, specification and execution identity together.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Candidate 0 passes after two attempts; candidate 1 passes after one.",
              "Candidate 1 wins even if candidate 0’s reply arrived first.",
              "If both pass after one attempt, the lower index wins under the documented rule."
            ],
            "takeaway": "Deterministic selection is conditional on the candidate replies and the ranking contract."
          },
          "question": "A kept unit passed an old spec but fails the new examples. What should happen?",
          "options": [
            "Reuse it because acceptance is permanent",
            "Stop or explicitly rebuild it under the new contract",
            "Ignore the new examples"
          ],
          "ans": 1,
          "feedback": [
            "Historical evidence does not establish current compatibility.",
            "Preserve the prior work and make the changed-contract failure visible.",
            "The new contract must not be silently bypassed."
          ],
          "explanation": "Preserve the prior work and make the changed-contract failure visible.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Distinguish a cached reply from a kept, retested unit.",
            "model": "A cached reply is reused when its request identity matches. A kept unit is explicit accepted code retained from an earlier build and checked against the current spec, independent of a fresh model response."
          },
          "references": [
            {
              "title": "Spec Sheets",
              "url": "/docs/reference/SPEC-SHEETS.md"
            },
            {
              "title": "Execution Pins",
              "url": "/docs/reference/EXECUTION-PINS.md"
            },
            {
              "title": "Results",
              "url": "/docs/reference/RESULTS.md"
            }
          ]
        },
        {
          "title": "Your research-to-program capstone",
          "concept": "Choose a claim from the research map and turn it into a small inspectable experiment. Start by labeling it as an implemented capability, an established mathematical result, an empirical observation or a proposal. Define inputs, output and a falsifiable criterion. Include a worked hand calculation or independent reference, a counterexample to an overclaim and a resource boundary. If a model participates, record source and feedback dependencies and use held-out cases. If an action occurs, include its recovery contract. Explain the result in ordinary language before discussing philosophical or physical analogies.",
          "code": "",
          "metaphor": "",
          "worked": {
            "title": "Follow the reasoning",
            "steps": [
              "Take the claim “multiple perspectives improve extraction.”",
              "Compare matched cases under one reader and a defined multi-reader method, scoring source fidelity, wrong acceptance, refusal, latency and calls.",
              "Record shared sources and training-family limitations; a higher agreement rate alone does not establish improved extraction."
            ],
            "takeaway": "A research idea becomes teachable when its mechanism, evidence and limits can all be explained."
          },
          "question": "Which capstone best demonstrates understanding?",
          "options": [
            "Repeat that Symblic unifies all physics and language",
            "List many technical terms without definitions",
            "Explain a bounded claim, work an example, test a counterexample and identify remaining uncertainty"
          ],
          "ans": 2,
          "feedback": [
            "That statement exceeds the supplied evidence and skips the mechanism.",
            "Terminology without usable distinctions does not demonstrate transfer.",
            "This connects concept, application, evidence and scope."
          ],
          "explanation": "This connects concept, application, evidence and scope.",
          "hint": "Follow the worked example, then compare the assumptions in each answer.",
          "reflection": {
            "prompt": "Create a one-page capstone plan using a topic from your own work or field.",
            "model": "State the claim and source, distinguish observation from inference, define units and assumptions, give a worked example, choose independent checks, identify a plausible passing-but-wrong answer, and specify how outcomes will be reported."
          },
          "references": [
            {
              "title": "Development And Use Cases",
              "url": "/docs/reference/DEVELOPMENT-AND-USE-CASES.md"
            },
            {
              "title": "Research Adoption",
              "url": "/docs/reference/RESEARCH-ADOPTION.md"
            },
            {
              "title": "Evidence",
              "url": "/docs/reference/EVIDENCE.md"
            },
            {
              "title": "Research Agreement",
              "url": "/docs/reference/RESEARCH-AGREEMENT.md"
            }
          ]
        }
      ]
    }
  ],
  "sources": [
    {
      "title": "Ambiguous-request benchmark",
      "url": "/docs/reference/AMBIGUITY-BENCH.md",
      "headings": [
        "Ambiguous-request benchmark",
        "Data and interpretation",
        "Conditions and endpoints",
        "Running",
        "Records and recovery"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 6,
          "bite": 1,
          "title": "Capstone 2: The Self-Healing Data Classifier"
        },
        {
          "level": 7,
          "bite": 1,
          "title": "Operational definitions and boundary cases"
        },
        {
          "level": 7,
          "bite": 2,
          "title": "Ambiguity versus missing information"
        },
        {
          "level": 13,
          "bite": 1,
          "title": "The denominator and the unit of independence"
        }
      ],
      "sha256": "8121ec0292857689d46abbf9d57c5e00305d7e857040b3a27e79ca7de147a497",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/AMBIGUITY-BENCH.md",
        "sha256": "8121ec0292857689d46abbf9d57c5e00305d7e857040b3a27e79ca7de147a497",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Critical review of Symblic's contracts and usefulness",
      "url": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md",
      "headings": [
        "Critical review of Symblic's contracts and usefulness",
        "1. A checked contract can be the wrong contract",
        "2. Exact processing can preserve a false premise",
        "3. Context isolation creates an information-selection problem",
        "4. Repeatability has several different meanings",
        "5. More formal capability needs a clear boundary",
        "6. Composition and learning can multiply cost and failure",
        "7. Usefulness must be demonstrated against realistic alternatives"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 0,
          "bite": 0,
          "title": "Two Brains in Your Computer"
        },
        {
          "level": 1,
          "bite": 0,
          "title": "What an assertion really establishes"
        },
        {
          "level": 2,
          "bite": 2,
          "title": "Capsules: explicit and sufficient context"
        },
        {
          "level": 3,
          "bite": 0,
          "title": "Repairing candidates with ensure"
        },
        {
          "level": 5,
          "bite": 4,
          "title": "Representation, equivalence and information loss"
        },
        {
          "level": 6,
          "bite": 3,
          "title": "Capstone 4: Full Neuro-Symbolic Mastery Exam"
        },
        {
          "level": 9,
          "bite": 3,
          "title": "Falsification, auxiliaries and charitable diagnosis"
        },
        {
          "level": 12,
          "bite": 1,
          "title": "Energy bounds do not settle every regularity question"
        },
        {
          "level": 13,
          "bite": 2,
          "title": "Counterexamples, vacuity and specification gaming"
        }
      ],
      "sha256": "88b5eb0890691c5c2c9f73733454c83c53242bbd49e3ed59669c40253ad98705",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/CRITIQUE-AND-LIMITATIONS.md",
        "sha256": "88b5eb0890691c5c2c9f73733454c83c53242bbd49e3ed59669c40253ad98705",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic development roadmap and application candidates",
      "url": "/docs/reference/DEVELOPMENT-AND-USE-CASES.md",
      "headings": [
        "Symblic development roadmap and application candidates",
        "Existing foundations and proposed extensions",
        "Application candidates",
        "Evidence needed to advance a candidate"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 6,
          "bite": 2,
          "title": "Capstone 3: The Resilient Web Agent"
        },
        {
          "level": 14,
          "bite": 3,
          "title": "Your research-to-program capstone"
        }
      ],
      "sha256": "5cccf0075102fa3cb6e3cbcff93f9ed7aff48f2d4888612a7ed49586da3c534f",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/DEVELOPMENT-AND-USE-CASES.md",
        "sha256": "5cccf0075102fa3cb6e3cbcff93f9ed7aff48f2d4888612a7ed49586da3c534f",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Exact ground states of a small Ising model",
      "url": "/docs/reference/DISCRETE.md",
      "headings": [
        "Exact ground states of a small Ising model",
        "Interface",
        "The result",
        "Domain, limits and refusals",
        "Method and cost",
        "What a result establishes and what it does not",
        "Example",
        "Verification"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 10,
          "bite": 3,
          "title": "Discrete optimization, ties and witnesses"
        }
      ],
      "sha256": "3341bcdabbace84fbe7d02c3bb1c348303363fc03eec16ff7d3a1a66c9ee03ae",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/DISCRETE.md",
        "sha256": "3341bcdabbace84fbe7d02c3bb1c348303363fc03eec16ff7d3a1a66c9ee03ae",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic effects — `observe` and `act`",
      "url": "/docs/reference/EFFECTS.md",
      "headings": [
        "Symblic effects — `observe` and `act`",
        "1. Why three statements",
        "2. Syntax",
        "3. Capabilities and typing",
        "4. Execution: the ledger",
        "5. Information flow",
        "6. Evidence",
        "7. Host interface",
        "8. Related work (each checked at its source on 2026-10-03)"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 3,
          "bite": 1,
          "title": "Rollback and the external-world boundary"
        },
        {
          "level": 4,
          "bite": 3,
          "title": "The Append-Only Ledger"
        },
        {
          "level": 5,
          "bite": 1,
          "title": "The Eloquence Trap (Jürgen Habermas)"
        },
        {
          "level": 6,
          "bite": 2,
          "title": "Capstone 3: The Resilient Web Agent"
        },
        {
          "level": 12,
          "bite": 2,
          "title": "Symmetry and conservation are specific relationships"
        }
      ],
      "sha256": "41f17202a32f3cdf6aa6eedda80f5a085b333956713f40f705695d831bdc277d",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/EFFECTS.md",
        "sha256": "41f17202a32f3cdf6aa6eedda80f5a085b333956713f40f705695d831bdc277d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Improving Symblic via Intersubjectivity: Epistemic Types, Multi-Frame Verification, and Theory of Mind in Language Design",
      "url": "/docs/reference/EPISTEMIC-IMPROVEMENTS.md",
      "headings": [
        "Improving Symblic via Intersubjectivity: Epistemic Types, Multi-Frame Verification, and Theory of Mind in Language Design",
        "1. The Core Critique, Checked Against the Code",
        "What the critique claimed, and what holds",
        "2. Six Proposed Upgrades, and What Became of Them",
        "Upgrade 1: First-Class Epistemic Modality Types",
        "Proposed syntax (not Symblic; not built)",
        "What it would add, and what exists",
        "Upgrade 2: Multi-Frame Concordance Contracts (proposed as a \"multi-frame engine\")",
        "Proposed syntax (not Symblic; not built)",
        "What the proposal claimed, corrected",
        "Upgrade 3: The Davidsonian Triangulation Pass (Pre-Flight Semantic Calibration)",
        "What was proposed (not built)",
        "What exists before a run",
        "What these features do",
        "Upgrade 4: The Principle of Charity & Epistemic Diagnostics (Smart Recovery)",
        "What happens when a check fails",
        "What was proposed and not built",
        "Upgrade 5: Non-Degeneracy Checks (proposed under a mechanism-design framing)",
        "The problem (correct as stated)",
        "The proposal, and what was built",
        "What this establishes",
        "Upgrade 6: Theory of Mind (ToM) & Aumann Knowledge Graph in Multi-Agent Symblic",
        "Proposed syntax (not Symblic; not built)",
        "What exists",
        "What the proposal claimed, corrected",
        "3. Summary of Proposed Changes to Symblic Core",
        "4. Conclusion: What Survives",
        "Sources"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 7,
          "bite": 1,
          "title": "Operational definitions and boundary cases"
        },
        {
          "level": 8,
          "bite": 0,
          "title": "Perspective-taking is a revisable model"
        },
        {
          "level": 8,
          "bite": 1,
          "title": "Naïve realism and frame mismatch"
        },
        {
          "level": 9,
          "bite": 1,
          "title": "Distinct frames versus repeated readings"
        }
      ],
      "sha256": "e1b6fed8d8accccc506910c862b33d3b44cb373568741056718a86128eb71923",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/EPISTEMIC-IMPROVEMENTS.md",
        "sha256": "e1b6fed8d8accccc506910c862b33d3b44cb373568741056718a86128eb71923",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic evidence and assurance",
      "url": "/docs/reference/EVIDENCE.md",
      "headings": [
        "Symblic evidence and assurance",
        "What a result establishes",
        "Observation declarations and recorded dependencies",
        "Predicate receipts and finite determination",
        "Checked escalation and budgets",
        "Test certificates and locks",
        "Observations, actions and extension boundaries",
        "Applying the multi-frame design rationale without overstating it",
        "Evaluation requirements"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 2,
          "bite": 1,
          "title": "Asking with Strict Output Types (`ask`)"
        },
        {
          "level": 2,
          "bite": 2,
          "title": "Capsules: explicit and sufficient context"
        },
        {
          "level": 4,
          "bite": 0,
          "title": "Typed Tables"
        },
        {
          "level": 4,
          "bite": 3,
          "title": "The Append-Only Ledger"
        },
        {
          "level": 6,
          "bite": 3,
          "title": "Capstone 4: Full Neuro-Symbolic Mastery Exam"
        },
        {
          "level": 9,
          "bite": 0,
          "title": "Empirical adequacy and the aim of inquiry"
        },
        {
          "level": 9,
          "bite": 1,
          "title": "Distinct frames versus repeated readings"
        },
        {
          "level": 9,
          "bite": 2,
          "title": "Evidence strength and evidence security"
        },
        {
          "level": 14,
          "bite": 3,
          "title": "Your research-to-program capstone"
        }
      ],
      "sha256": "f58f4859828a93876016430f5d05f299dd7f56d3ee8be354add109afb55effb3",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/EVIDENCE.md",
        "sha256": "f58f4859828a93876016430f5d05f299dd7f56d3ee8be354add109afb55effb3",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Execution pins (receipt version 2)",
      "url": "/docs/reference/EXECUTION-PINS.md",
      "headings": [
        "Execution pins (receipt version 2)",
        "Loaded source identity",
        "Libraries, capabilities and inputs"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 0,
          "bite": 1,
          "title": "Exact fractions and measured uncertainty"
        },
        {
          "level": 4,
          "bite": 3,
          "title": "The Append-Only Ledger"
        },
        {
          "level": 6,
          "bite": 2,
          "title": "Capstone 3: The Resilient Web Agent"
        },
        {
          "level": 14,
          "bite": 1,
          "title": "A sandboxed test is still a finite test"
        },
        {
          "level": 14,
          "bite": 2,
          "title": "Deterministic selection and preserving good work"
        }
      ],
      "sha256": "07e2ecb65b14c4b5bb8d922aeeec01c678e680b79c2534c7319f440dcfe1a9f0",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/EXECUTION-PINS.md",
        "sha256": "07e2ecb65b14c4b5bb8d922aeeec01c678e680b79c2534c7319f440dcfe1a9f0",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Mathematical research for Symblic: constructions, hypotheses and tests",
      "url": "/docs/reference/GRAND-UNIFICATION-AND-STRING-THEORY.md",
      "headings": [
        "Mathematical research for Symblic: constructions, hypotheses and tests",
        "The admission rule",
        "Preserve the finite mathematics already implemented",
        "Fluid computation, projection and stability",
        "Holography and Ryu–Takayanagi",
        "String worldsheets, conformal symmetry and prompt injection",
        "Mirror symmetry, T-duality and representation transport",
        "HoTT and schema equivalence",
        "Sheaves, topoi and consistent perspectives",
        "Broader research directions remain open",
        "A concrete path toward a stronger system"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 5,
          "bite": 3,
          "title": "Energy methods and their assumptions"
        },
        {
          "level": 5,
          "bite": 4,
          "title": "Representation, equivalence and information loss"
        },
        {
          "level": 12,
          "bite": 1,
          "title": "Energy bounds do not settle every regularity question"
        },
        {
          "level": 12,
          "bite": 3,
          "title": "Coarse-graining, holography and what gets lost"
        }
      ],
      "sha256": "e9de549daed599ccb5aed52fa7e218a3772e4b2b37affa67e896068d6fdb292f",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/GRAND-UNIFICATION-AND-STRING-THEORY.md",
        "sha256": "e9de549daed599ccb5aed52fa7e218a3772e4b2b37affa67e896068d6fdb292f",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic on High-Performance Computing (HPC): Proposals and Status",
      "url": "/docs/reference/HPC-FOUNDATIONS.md",
      "headings": [
        "Symblic on High-Performance Computing (HPC): Proposals and Status",
        "Executive Summary",
        "Part 1: Developing Symblic on an HPC System",
        "1.1 Path A: HPC Execution & Distributed Scaling",
        "1.2 Path B: HPC Training & Reinforcement Learning with Verifiable Rewards (RLVR)",
        "What Should (and Should Not) Be Trained",
        "Would Training Make Significant Improvements?",
        "1.3 Critical Failure Modes: Can Training Make Symblic Worse?",
        "Training Parameters & Dataset Composition (untested proposal)",
        "Part 2: Checking a claim through several routes",
        "Part 3: The Shippable Product Roadmap",
        "References"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 9,
          "bite": 0,
          "title": "Empirical adequacy and the aim of inquiry"
        },
        {
          "level": 9,
          "bite": 1,
          "title": "Distinct frames versus repeated readings"
        },
        {
          "level": 9,
          "bite": 2,
          "title": "Evidence strength and evidence security"
        },
        {
          "level": 13,
          "bite": 2,
          "title": "Counterexamples, vacuity and specification gaming"
        }
      ],
      "sha256": "ac993a3ef64fe4e036b485585d2e4404512b0eef44daacf2a5817bd6debe3477",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/HPC-FOUNDATIONS.md",
        "sha256": "ac993a3ef64fe4e036b485585d2e4404512b0eef44daacf2a5817bd6debe3477",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: critical review, counterexamples and unresolved limits",
      "url": "/docs/reference/INTENSE-CRITIQUE-AND-LIMITATIONS.md",
      "headings": [
        "Symblic: critical review, counterexamples and unresolved limits",
        "1. The semantic gap is not closed by a strict schema",
        "2. More precise steps can still accumulate errors",
        "3. “Moving the programming into the kernel” is a valid concern",
        "4. Proofs, predicates and tests require different language",
        "5. Assumptions must not be laundered into established knowledge",
        "6. Context packing can silently change the task",
        "7. The language needs explicit operational distinctions",
        "8. Agreement and optimization can reward the wrong target",
        "9. Agent networks need computational semantics",
        "10. Security and effects: preserve real protections, test remaining influence",
        "11. Numerical exactness is not empirical precision",
        "12. The existing evidence cannot support broad superiority claims",
        "13. Unsupported mathematical language damaged credibility",
        "Is Symblic useful?"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 3,
          "bite": 2,
          "title": "Bounded retries are not convergence"
        },
        {
          "level": 9,
          "bite": 3,
          "title": "Falsification, auxiliaries and charitable diagnosis"
        },
        {
          "level": 13,
          "bite": 2,
          "title": "Counterexamples, vacuity and specification gaming"
        }
      ],
      "sha256": "7fb1b4438e907b3cf70718e7227b84e8a8fa515a68a7437a0b938861de5046e7",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/INTENSE-CRITIQUE-AND-LIMITATIONS.md",
        "sha256": "7fb1b4438e907b3cf70718e7227b84e8a8fa515a68a7437a0b938861de5046e7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "From an idea to a checked program",
      "url": "/docs/reference/INTERPRETER.md",
      "headings": [
        "From an idea to a checked program",
        "What is recorded and checked",
        "Routing, budget and recovery",
        "Research basis and present limits",
        "Developer entry points",
        "Run recovery identity"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 3,
          "bite": 0,
          "title": "Repairing candidates with ensure"
        },
        {
          "level": 6,
          "bite": 0,
          "title": "Capstone 1: The Automated Invoice Auditor"
        },
        {
          "level": 7,
          "bite": 2,
          "title": "Ambiguity versus missing information"
        },
        {
          "level": 9,
          "bite": 3,
          "title": "Falsification, auxiliaries and charitable diagnosis"
        }
      ],
      "sha256": "101df49db21482c1aee80bb66f2f2f03b71f31d51d451a5f9fffa29fee775aab",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/INTERPRETER.md",
        "sha256": "101df49db21482c1aee80bb66f2f2f03b71f31d51d451a5f9fffa29fee775aab",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic and Human Intersubjectivity: Formalizing Empathy, Bridging Perceptual Chasms, and the Architecture of Unified Communication",
      "url": "/docs/reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md",
      "headings": [
        "Symblic and Human Intersubjectivity: Formalizing Empathy, Bridging Perceptual Chasms, and the Architecture of Unified Communication",
        "Executive Summary",
        "Table of Contents",
        "1. The Epistemic Barrier: Why Humans Misunderstand Each Other",
        "1.1 The Phenomenological Chasm (Nagel & Wittgenstein)",
        "1.2 The Triangulation Principle & Radical Interpretation (Davidson)",
        "1.3 Double Contingency: The Black Box Problem (Luhmann)",
        "1.4 Naïve Realism and the Epistemic Fallacy (Ross)",
        "2. The Science of Empathy: Is \"True Empathy\" Possible?",
        "2.1 The Biological Dual-Stream Model (Singer & Bloom)",
        "2.2 Predictive Processing & Coupled Active Inference (Friston & Clark)",
        "2.3 The Levinasian Horizon: Alterity vs. Assimilation",
        "2.4 Operational questions about empathy",
        "3. Sociological & Economic Mechanics of Coordination",
        "3.1 Habermas's Four Validity Claims",
        "3.2 Goffman's Frame Analysis & Garfinkel's Background Expectancies",
        "3.3 Aumann's Agreement Theorem & The Failure of Common Knowledge",
        "3.4 Crawford-Sobel Cheap Talk vs. Costly Signaling",
        "4. The Symblic Intersubjective Architecture (SIA)",
        "4.1 Proposed domain records",
        "5. Historical pseudocode: the proposed mediator",
        "6. Philosophical & Practical Implications",
        "6.1 From Cheap Talk to Intersubjective Proofs",
        "6.2 The Ethical Synthesis: Empathy as Epistemic Humility"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 5,
          "bite": 0,
          "title": "The Triangulation Metaphor (Donald Davidson)"
        },
        {
          "level": 5,
          "bite": 1,
          "title": "The Eloquence Trap (Jürgen Habermas)"
        },
        {
          "level": 8,
          "bite": 0,
          "title": "Perspective-taking is a revisable model"
        },
        {
          "level": 8,
          "bite": 1,
          "title": "Naïve realism and frame mismatch"
        },
        {
          "level": 8,
          "bite": 2,
          "title": "Knowing, everyone knowing, common knowledge"
        },
        {
          "level": 8,
          "bite": 3,
          "title": "Agreement theorems have assumptions"
        }
      ],
      "sha256": "a3eed69b56a9c8ce911cc8fdfb3303a4d8a294ab804c9d47658a8259ddc20039",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md",
        "sha256": "a3eed69b56a9c8ce911cc8fdfb3303a4d8a294ab804c9d47658a8259ddc20039",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "JavaScript checks (`js_test`, `js_run`)",
      "url": "/docs/reference/JS.md",
      "headings": [
        "JavaScript checks (`js_test`, `js_run`)",
        "What it computes",
        "Isolation",
        "Limits",
        "Determinism and identity",
        "What a pass does not establish",
        "CLI, preview and test process limits"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        },
        {
          "level": 14,
          "bite": 1,
          "title": "A sandboxed test is still a finite test"
        }
      ],
      "sha256": "788765aa053deb9b8eebd4599fc99d22d75e8904ae3d17d29e472e9176de962d",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/JS.md",
        "sha256": "788765aa053deb9b8eebd4599fc99d22d75e8904ae3d17d29e472e9176de962d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Knowledge on a finite set of states",
      "url": "/docs/reference/KNOWLEDGE.md",
      "headings": [
        "Knowledge on a finite set of states",
        "The model",
        "The builtins",
        "The announcement process",
        "Domain and limits",
        "What this does not establish",
        "Example",
        "Sources"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 8,
          "bite": 2,
          "title": "Knowing, everyone knowing, common knowledge"
        },
        {
          "level": 8,
          "bite": 3,
          "title": "Agreement theorems have assumptions"
        }
      ],
      "sha256": "9ec06d927363651edac2bf43dd51126147535ab7baf33bd77d9a506c879cb60b",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/KNOWLEDGE.md",
        "sha256": "9ec06d927363651edac2bf43dd51126147535ab7baf33bd77d9a506c879cb60b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: the abstraction layer (functions, routines, modules, tests, papers, locks)",
      "url": "/docs/reference/LANGUAGE-3.md",
      "headings": [
        "Symblic: the abstraction layer (functions, routines, modules, tests, papers, locks)",
        "0. Grammar of the new statements",
        "Execution profiles and formal statements",
        "1. Functions",
        "2. Routines: typed LLM functions with contracts",
        "3. Modules",
        "4. Tests and certification",
        "4b. Crystallisation: compiling a routine's answers into the kernel",
        "5. Papers (`.symd`): a technical paper that agents execute",
        "6. Locks",
        "7. Measured (2026-10-02, real agents on the worker nodes)",
        "8. What this layer does and does not claim"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 1,
          "bite": 1,
          "title": "Bounded Integers (`Int in min..max`)"
        },
        {
          "level": 3,
          "bite": 3,
          "title": "Reading syntax and recognizing proposals"
        },
        {
          "level": 4,
          "bite": 1,
          "title": "Facts & Rules"
        },
        {
          "level": 7,
          "bite": 3,
          "title": "Compositional meaning and representation"
        },
        {
          "level": 11,
          "bite": 3,
          "title": "ZX calculus, no-cloning and category mistakes"
        }
      ],
      "sha256": "704c8229f0b2856a30ee6da4c421a15d877b0f4b2dbba97c8e89a4cb6ac549e1",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/LANGUAGE-3.md",
        "sha256": "704c8229f0b2856a30ee6da4c421a15d877b0f4b2dbba97c8e89a4cb6ac549e1",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "From human statements to checked Symblic programs",
      "url": "/docs/reference/NATURAL-LANGUAGE-BRIDGE.md",
      "headings": [
        "From human statements to checked Symblic programs",
        "Choose the right execution lane",
        "Start with the statement and its failure cases",
        "Exact computation remains available",
        "Human statements can be formal propositions",
        "Let a model construct the derivation",
        "Types constrain representation; witnesses constrain more",
        "Compose evidence as well as values",
        "Queries, obligations and effects are different operations",
        "From a pipeline to an agent network"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 0,
          "bite": 3,
          "title": "Storing Values with `let`"
        },
        {
          "level": 2,
          "bite": 0,
          "title": "The Shared Dictionary (`term`)"
        },
        {
          "level": 5,
          "bite": 0,
          "title": "The Triangulation Metaphor (Donald Davidson)"
        },
        {
          "level": 6,
          "bite": 0,
          "title": "Capstone 1: The Automated Invoice Auditor"
        },
        {
          "level": 7,
          "bite": 0,
          "title": "Syntax, semantics and pragmatics"
        }
      ],
      "sha256": "5339ffe7b415bc17c0bb01fb8e94da1ae656183247029d254b718872c4816336",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/NATURAL-LANGUAGE-BRIDGE.md",
        "sha256": "5339ffe7b415bc17c0bb01fb8e94da1ae656183247029d254b718872c4816336",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: prompts, discoveries and answers (2026-10-02 → 2026-10-03)",
      "url": "/docs/reference/NOTES-2026-10-02.md",
      "headings": [
        "Symblic: prompts, discoveries and answers (2026-10-02 → 2026-10-03)",
        "1. The prompts",
        "1.1 The first request (2026-10-02, afternoon)",
        "1.2 The instruction during the first night",
        "1.3 \"is everything done?\"",
        "1.4 \"so far does symblic prove determinism with llms can i say i made a deterministic coding lanuage using llms as the the basis\"",
        "1.5 The second request (2026-10-02, night)",
        "1.6 The questions after the work (2026-10-03, morning)",
        "2. What Symblic is, in one paragraph",
        "3. What was built",
        "First night",
        "Second phase (this session)",
        "4. What was discovered",
        "4.1 First-night measurements",
        "4.2 Second-phase measurements",
        "4.3 What the research found",
        "4.4 Lessons about writing statements that converge",
        "4.5 Defects found and fixed along the way",
        "4.6 Operational lessons",
        "5. Answers to the questions of 2026-10-03",
        "A correction first: what the qwen result showed",
        "Can light models replace proprietary ones in a CLI?",
        "How to make it more deterministic",
        "Strict, logical natural language",
        "Rewriting the backend in Rust or C",
        "One agent with memory wipes vs a group",
        "Does it improve small models?",
        "Uses",
        "Why it matters",
        "Does something like it exist?",
        "What would heavily improve accuracy",
        "6. What can be claimed now",
        "7. Open items",
        "8. Where things are"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "f5d9aecd7690d14e6ef7200a45122882514f3bfda306f83ee82b54732b53e780",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/NOTES-2026-10-02.md",
        "sha256": "f5d9aecd7690d14e6ef7200a45122882514f3bfda306f83ee82b54732b53e780",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Exact finite operators and question order",
      "url": "/docs/reference/OPERATORS.md",
      "headings": [
        "Exact finite operators and question order",
        "What is computed",
        "Domain and refusals",
        "Limits and budget",
        "What the model predicts",
        "What it does not establish",
        "Example (kernel only)",
        "Integration",
        "Focused verification",
        "References"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 5,
          "bite": 2,
          "title": "Quantum collapse: analogy versus mechanism"
        },
        {
          "level": 11,
          "bite": 0,
          "title": "Deterministic evolution and probabilistic outcomes"
        },
        {
          "level": 11,
          "bite": 1,
          "title": "Noncommuting projections and question order"
        },
        {
          "level": 11,
          "bite": 2,
          "title": "A prediction can test a quantum-cognition model"
        }
      ],
      "sha256": "a421fde2618b6c1c331a8c6053aed9d1041d554b10947ce587241862e9200ca9",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/OPERATORS.md",
        "sha256": "a421fde2618b6c1c331a8c6053aed9d1041d554b10947ce587241862e9200ca9",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Modern Mathematical Physics and Symblic: The 2026 Navier-Stokes Announcement and Five Proposed Borrowings",
      "url": "/docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md",
      "headings": [
        "Modern Mathematical Physics and Symblic: The 2026 Navier-Stokes Announcement and Five Proposed Borrowings",
        "Executive summary",
        "Table of contents",
        "1. The 2026 Navier-Stokes announcement",
        "1.1 What was announced",
        "1.2 The \"specification gaming\" reading, and why it does not hold",
        "1.3 The lesson for Symblic: a check certifies its predicate",
        "2. Sobolev spaces and the mathematics of regularity",
        "2.1 The Navier-Stokes Cauchy problem",
        "2.2 The Beale-Kato-Majda (BKM) criterion",
        "2.3 \"Cognitive blow-up\": an analogy, and what Symblic actually bounds",
        "3. Symplectic geometry and Noether's theorem",
        "3.1 The symplectic 2-form and Liouville's theorem",
        "3.2 Noether's theorem (1918)",
        "3.3 Conservation checks in Symblic",
        "4. Wilsonian renormalization and context",
        "4.1 Wilson's renormalization group (1971)",
        "4.2 Relevant, marginal and irrelevant couplings, and the analogy to text",
        "4.3 The proposed RG context engine (not built)",
        "5. Information geometry: the Fisher-Rao metric",
        "5.1 The statistical manifold $\\mathcal{M}$",
        "5.2 Symblic's quadratic solver and the natural gradient",
        "6. Optimal transport and Wasserstein barycenters",
        "6.1 The Wasserstein metric and Kantorovich-Rubinstein duality",
        "6.2 Multi-agent consensus: what Symblic computes and what was built",
        "7. The proposed physics-informed specification, and its real counterparts",
        "8. Summary",
        "Sources",
        "Where this document is recorded"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 5,
          "bite": 3,
          "title": "Energy methods and their assumptions"
        },
        {
          "level": 10,
          "bite": 2,
          "title": "Optimal transport sees what a median loses"
        },
        {
          "level": 12,
          "bite": 0,
          "title": "From a weak form to a finite energy problem"
        },
        {
          "level": 12,
          "bite": 1,
          "title": "Energy bounds do not settle every regularity question"
        },
        {
          "level": 12,
          "bite": 2,
          "title": "Symmetry and conservation are specific relationships"
        },
        {
          "level": 12,
          "bite": 3,
          "title": "Coarse-graining, holography and what gets lost"
        }
      ],
      "sha256": "247034e52335dfb7adfa03ddf474fbc7cd2641866bd6cb8681e20f2f4ce2e77e",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md",
        "sha256": "247034e52335dfb7adfa03ddf474fbc7cd2641866bd6cb8681e20f2f4ce2e77e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: prior-art survey and research scope",
      "url": "/docs/reference/PRIOR-ART.md",
      "headings": [
        "Symblic: prior-art survey and research scope",
        "1. Relationship to existing work",
        "1.1 Primary comparators revisited for version 2.1",
        "2. Comparison table",
        "3. Area 1: LM programming and prompt languages",
        "4. Area 2: Controlled natural languages",
        "5. Area 3: Neurosymbolic reasoning — the LLM translates, a solver decides",
        "6. Area 4: Decomposition with fresh or limited context",
        "7. Area 5: Small models collectively vs. large models",
        "8. Area 6: Determinism, constrained decoding, cross-model agreement",
        "9. Area 8: Searching for the exact combination",
        "10. Area 7: Formal specification to an identical generative artifact",
        "11. What the evidence says about small-model councils",
        "12. Design lessons for Symblic",
        "13. Defensible claims vs. overclaims (summary)",
        "14. References",
        "LM programming and prompt languages",
        "Controlled natural languages",
        "Neurosymbolic reasoning and formal proof",
        "Decomposition and context",
        "Small models, ensembles, test-time compute",
        "Determinism, structured outputs, agreement",
        "Formal specification to artifact",
        "Not verified in this survey"
      ],
      "status": "Research survey / verify original references and evidence labels",
      "lessons": [
        {
          "level": 13,
          "bite": 3,
          "title": "Novelty, prior art and measured contribution"
        }
      ],
      "sha256": "abb17c8e18c7b994e419bf4fe937d33844112937ab7390bff5e66f0f397ca2ab",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PRIOR-ART.md",
        "sha256": "abb17c8e18c7b994e419bf4fe937d33844112937ab7390bff5e66f0f397ca2ab",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Exact adjustment to affine constraints",
      "url": "/docs/reference/PROJECTION.md",
      "headings": [
        "Exact adjustment to affine constraints",
        "Inputs and result",
        "Computation and checks",
        "Bounds and integration"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 10,
          "bite": 1,
          "title": "Projection repairs values; it does not reveal truth"
        }
      ],
      "sha256": "f082aa04203759f8573d1677989b394276e13a4c8b807ab8aa4b540dbc9bfb00",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROJECTION.md",
        "sha256": "f082aa04203759f8573d1677989b394276e13a4c8b807ab8aa4b540dbc9bfb00",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Quantum Mechanics and Computational Determinism: Does Quantum Mathematics Weaken or Strengthen Symblic's Invariants?",
      "url": "/docs/reference/QUANTUM-DETERMINISM-ANALYSIS.md",
      "headings": [
        "Quantum Mechanics and Computational Determinism: Does Quantum Mathematics Weaken or Strengthen Symblic's Invariants?",
        "Executive Summary",
        "Table of Contents",
        "1. Schrödinger vs. Born: The Two Equations of Quantum Mechanics",
        "2. Where Symblic Is Deterministic, and Where It Is Not",
        "The Three Sources of Non-Determinism, as They Stand",
        "3. What Quantum Mathematics Can and Cannot Remove",
        "3.1 Non-Commuting Projectors and Prompt Order",
        "3.2 ZX-Calculus: Complete, Not Confluent, and Not in Symblic",
        "3.3 Ising Ground States: Exact up to 16 Spins, Not Always Unique, NP-hard in General",
        "4. The No-Cloning Theorem and Concurrency",
        "5. Where Non-Determinism Enters, and What Symblic Does About It",
        "Guard 1: Never Sample (proposed; rejected)",
        "Guard 2: Exact Arithmetic with Cyclotomic Fields (proposed; rejected)",
        "Guard 3: Seeded Annealing (proposed; rejected)",
        "6. Summary: The Proposal Against Symblic 2.4",
        "Conclusion",
        "References"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 10,
          "bite": 3,
          "title": "Discrete optimization, ties and witnesses"
        },
        {
          "level": 11,
          "bite": 0,
          "title": "Deterministic evolution and probabilistic outcomes"
        },
        {
          "level": 11,
          "bite": 3,
          "title": "ZX calculus, no-cloning and category mistakes"
        }
      ],
      "sha256": "74a61f50e0e9053b02213878cf53704400dc8d8e09f76568a8ef93429bd67c28",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/QUANTUM-DETERMINISM-ANALYSIS.md",
        "sha256": "74a61f50e0e9053b02213878cf53704400dc8d8e09f76568a8ef93429bd67c28",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Quantum Mathematical Foundations for Neuro-Symbolic Computation: Applying Quantum Mechanics to Symblic",
      "url": "/docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md",
      "headings": [
        "Quantum Mathematical Foundations for Neuro-Symbolic Computation: Applying Quantum Mechanics to Symblic",
        "Executive Summary",
        "Table of Contents",
        "1. Quantum Logic vs. Classical Boolean Lattices",
        "1.1 Distributivity: Boolean Lattices and Subspace Lattices",
        "1.2 Closed Subspaces and Projection Operators",
        "1.3 Non-Commuting Projectors and Order Effects",
        "2. Quantum Cognition: Interference and Decision Geometry",
        "2.1 The Conjunction Fallacy and Probability Amplitudes",
        "2.2 Question Order and Sequential Asks",
        "3. Categorical Quantum Mechanics: DisCoCat and Tensor Networks",
        "3.1 Compact Closed Monoidal Categories (Abramsky & Coecke; Coecke, Sadrzadeh & Clark)",
        "3.2 ZX-Calculus and Tensor Networks",
        "4. Measurement and Decoherence: What an Ask Does",
        "4.1 Model State: Hidden Vectors, Softmax and Density Matrices",
        "4.2 POVMs, and What `ensure` Does",
        "4.3 Decoherence and Einselection (Zurek 2003)",
        "5. Hamiltonian Variational Optimization: SPD Quadratics and Ising Spin Glasses",
        "5.1 Mapping Symblic Constraints to Quadratic Unconstrained Binary Optimization (QUBO)",
        "5.2 The Rayleigh-Ritz Variational Principle",
        "6. Linear Logic and the Quantum No-Cloning Theorem",
        "6.1 The No-Cloning Theorem (Wootters & Zurek 1982)",
        "6.2 Girard's Linear Logic and the Proposed Linear Capabilities",
        "7. The Q-Symblic Concrete Syntax: What Was Proposed and What Exists",
        "8. Summary: What the Quantum Proposals Changed in Symblic",
        "Where This Document Came From",
        "References"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 3,
          "bite": 3,
          "title": "Reading syntax and recognizing proposals"
        },
        {
          "level": 5,
          "bite": 2,
          "title": "Quantum collapse: analogy versus mechanism"
        },
        {
          "level": 7,
          "bite": 3,
          "title": "Compositional meaning and representation"
        },
        {
          "level": 11,
          "bite": 0,
          "title": "Deterministic evolution and probabilistic outcomes"
        },
        {
          "level": 11,
          "bite": 1,
          "title": "Noncommuting projections and question order"
        },
        {
          "level": 11,
          "bite": 3,
          "title": "ZX calculus, no-cloning and category mistakes"
        }
      ],
      "sha256": "a02796874a9a91142f6ea681ec044b98519a9156f6149f3b7982666e5ad069db",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md",
        "sha256": "a02796874a9a91142f6ea681ec044b98519a9156f6149f3b7982666e5ad069db",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Research adoption for Symblic",
      "url": "/docs/reference/RESEARCH-ADOPTION.md",
      "headings": [
        "Research adoption for Symblic",
        "Implementation status on 5 October 2026",
        "6 October continuation",
        "Earlier deployment records",
        "What we already have",
        "Highest-value additions beyond that plan",
        "Language, philosophy and human coordination",
        "Logic, types, security and distributed execution",
        "Quantum mathematics and semantic models",
        "Geometry, optimization and physics",
        "HPC, training, deployment and evaluation",
        "Falsification examples and admission into the language"
      ],
      "status": "Research survey / verify original references and evidence labels",
      "lessons": [
        {
          "level": 9,
          "bite": 0,
          "title": "Empirical adequacy and the aim of inquiry"
        },
        {
          "level": 13,
          "bite": 3,
          "title": "Novelty, prior art and measured contribution"
        },
        {
          "level": 14,
          "bite": 3,
          "title": "Your research-to-program capstone"
        }
      ],
      "sha256": "fb5f10de5b2cb7ec3e484f7ae3d9d4d25f739341709e47e7b42da193351614f1",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/RESEARCH-ADOPTION.md",
        "sha256": "fb5f10de5b2cb7ec3e484f7ae3d9d4d25f739341709e47e7b42da193351614f1",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: getting different LLMs to give the same answer",
      "url": "/docs/reference/RESEARCH-AGREEMENT.md",
      "headings": [
        "Symblic: getting different LLMs to give the same answer",
        "0. Findings and scope",
        "1. Prompt sensitivity and paraphrase consistency",
        "Evidence",
        "Verdict",
        "Implication for Symblic",
        "2. Ambiguity, underspecification and disagreement as a detector",
        "Evidence",
        "Verdict",
        "Implication for Symblic",
        "3. Techniques that increase cross-model agreement",
        "Evidence",
        "Verdict",
        "Implication for Symblic",
        "4. Convergence and conventions in LLM populations",
        "Evidence",
        "Verdict",
        "Implication for Symblic",
        "5. Spec-to-artifact reproducibility (CAD, 3D, code)",
        "Evidence: CAD",
        "Evidence: code equivalence",
        "Verdict",
        "Implication for Symblic",
        "6. Measuring agreement properly",
        "Evidence",
        "Verdict",
        "7. Engineering rules for Symblic (ranked by expected effect on cross-model agreement)",
        "8. Metrics to report",
        "8.1 Per statement (shown in Trace / Compare)",
        "8.2 Corpus level: Krippendorff's α (nominal, missing data allowed)",
        "8.3 Fleiss κ (complete data, the same k for every statement; closed suites only)",
        "8.4 Agreement vs correctness (when ground truth g_u exists)",
        "8.5 Stability metrics (statement fragility)",
        "8.6 Uncertainty: cluster bootstrap over statements",
        "8.7 Minimal report table (per suite × condition)",
        "9. What Symblic can measure next with the existing bench (no new infrastructure)",
        "10. References"
      ],
      "status": "Research survey / verify original references and evidence labels",
      "lessons": [
        {
          "level": 2,
          "bite": 0,
          "title": "The Shared Dictionary (`term`)"
        },
        {
          "level": 2,
          "bite": 1,
          "title": "Asking with Strict Output Types (`ask`)"
        },
        {
          "level": 2,
          "bite": 3,
          "title": "The Effort Dial (`with effort=...`)"
        },
        {
          "level": 6,
          "bite": 1,
          "title": "Capstone 2: The Self-Healing Data Classifier"
        },
        {
          "level": 7,
          "bite": 1,
          "title": "Operational definitions and boundary cases"
        },
        {
          "level": 7,
          "bite": 2,
          "title": "Ambiguity versus missing information"
        },
        {
          "level": 8,
          "bite": 3,
          "title": "Agreement theorems have assumptions"
        },
        {
          "level": 11,
          "bite": 2,
          "title": "A prediction can test a quantum-cognition model"
        },
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        },
        {
          "level": 13,
          "bite": 1,
          "title": "The denominator and the unit of independence"
        },
        {
          "level": 14,
          "bite": 3,
          "title": "Your research-to-program capstone"
        }
      ],
      "sha256": "7a139334767e9e7c6560399784b3ce0e33dc6d2d11233eb8c8bf0dfc9b25a4bb",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/RESEARCH-AGREEMENT.md",
        "sha256": "7a139334767e9e7c6560399784b3ce0e33dc6d2d11233eb8c8bf0dfc9b25a4bb",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: can a formal description force the same result from any reader?",
      "url": "/docs/reference/RESEARCH-LANGUAGE.md",
      "headings": [
        "Symblic: can a formal description force the same result from any reader?",
        "1. What the evidence supports",
        "2. Q1 — Can a description fix its object uniquely? (logic and philosophy of language)",
        "2.1 Model theory: what a finite text can and cannot pin down",
        "2.2 Why no finite text forces its own interpretation",
        "2.3 How formal semantics removes ambiguity",
        "2.4 The cube, worked through",
        "2.5 Verdict on Q1",
        "3. Q2 — What human communication research says about describing objects for reproduction",
        "3.1 Referential communication: descriptions shrink, and the shrunk forms are private",
        "3.2 Grounding and monitoring: interaction is what makes human instruction reliable",
        "3.3 Egocentrism and the curse of knowledge: writers overrate their own clarity",
        "3.4 Pragmatics: what readers add to the literal text",
        "3.5 Instruction design research",
        "3.6 LLM-specific communication findings",
        "3.7 Verdict on Q2",
        "4. Q3 — Controlled languages and engineering practice",
        "4.1 ASD-STE100 Simplified Technical English",
        "4.2 Logic-backed controlled languages",
        "4.3 Requirements engineering",
        "4.4 Operational practice",
        "4.5 Laboratory protocols",
        "4.6 Formal specification",
        "4.7 Geometry and generative description",
        "4.8 Verdict on Q3",
        "5. Q4 — How much must be said to fix an object?",
        "6. Design rules for Symblic",
        "7. Experiment designs",
        "E1. The cube ladder: does formality buy identity, and where does it stop?",
        "E2. Tangram conventions across agent populations",
        "E3. One-way build instructions: free prose vs STE vs Symblic, with and without feedback",
        "E4. Ambiguity audit: interpretation entropy and the effect of deterministic rules",
        "E5. Curse of knowledge and the cold-reader loop",
        "8. What this means for Symblic now (mapping to [SPEC.md](SPEC.md))",
        "9. References",
        "Logic and philosophy of language",
        "Human communication and instructions",
        "Controlled languages and engineering practice",
        "Description length and reference",
        "Not verified in this survey"
      ],
      "status": "Research survey / verify original references and evidence labels",
      "lessons": [
        {
          "level": 7,
          "bite": 0,
          "title": "Syntax, semantics and pragmatics"
        },
        {
          "level": 7,
          "bite": 3,
          "title": "Compositional meaning and representation"
        },
        {
          "level": 12,
          "bite": 3,
          "title": "Coarse-graining, holography and what gets lost"
        }
      ],
      "sha256": "26c923c4396ec1a8663ce654ed05b61cd15fa5446f444a8c7566fdbdda2fac9e",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/RESEARCH-LANGUAGE.md",
        "sha256": "26c923c4396ec1a8663ce654ed05b61cd15fa5446f444a8c7566fdbdda2fac9e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic — measured results and their scope",
      "url": "/docs/reference/RESULTS.md",
      "headings": [
        "Symblic — measured results and their scope",
        "Version 2.4: spec-sheet builds by local models (2026-10-04)",
        "Version 2.2 / canonical 3: finite witnesses and intent interpretation",
        "Version 2.1 / canonical 3: 2026-10-03",
        "Fixed-corpus conformance",
        "Six-case communication diagnostic: llama3.2:1b",
        "Same-case follow-up: qwen3:4b",
        "Historical experiments: 2026-10-02, version 2.0",
        "1. Historical kernel conformance cases",
        "2. Do different agents give the same answer? (16 questions, 7 applicators)",
        "3. Multi-hop logic: translate, then let the kernel reason (15 generated family trees)",
        "4. \"The same flower from an essay\" (6 essays)",
        "5. Arithmetic word problems and small-model councils (24 generated problems, GSM-Symbolic style)",
        "6. What this does and does not show",
        "7. Phase 2: making agents converge (2026-10-02, night)",
        "7.1 The cube hypothesis, measured (4 solids, 4 description styles, up to 9 applicators, 2 repetitions)",
        "7.2 Tightening: turning measured disagreement into a clearer statement",
        "7.3 Papers that fresh groups of agents execute (`.symd`, built with peer session c2)",
        "7.4 The determinism ladder (what can be claimed, rung by rung)",
        "8. Historical resumption recipe"
      ],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 0,
          "bite": 0,
          "title": "Two Brains in Your Computer"
        },
        {
          "level": 0,
          "bite": 1,
          "title": "Exact fractions and measured uncertainty"
        },
        {
          "level": 2,
          "bite": 3,
          "title": "The Effort Dial (`with effort=...`)"
        },
        {
          "level": 6,
          "bite": 0,
          "title": "Capstone 1: The Automated Invoice Auditor"
        },
        {
          "level": 6,
          "bite": 1,
          "title": "Capstone 2: The Self-Healing Data Classifier"
        },
        {
          "level": 9,
          "bite": 2,
          "title": "Evidence strength and evidence security"
        },
        {
          "level": 10,
          "bite": 0,
          "title": "Positive-definite quadratics and uniqueness"
        },
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        },
        {
          "level": 13,
          "bite": 1,
          "title": "The denominator and the unit of independence"
        },
        {
          "level": 14,
          "bite": 2,
          "title": "Deterministic selection and preserving good work"
        }
      ],
      "sha256": "eafe1a3789929351f3cfb99994bf02232b36f6b0bca997556e5a8257bd4c077a",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/RESULTS.md",
        "sha256": "eafe1a3789929351f3cfb99994bf02232b36f6b0bca997556e5a8257bd4c077a",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "What the review documents proposed, and what Symblic 2.3 does with it",
      "url": "/docs/reference/REVIEW-2.3.md",
      "headings": [
        "What the review documents proposed, and what Symblic 2.3 does with it",
        "Outcome",
        "What 2.3 adds",
        "Recurring errors about Symblic",
        "Recurring errors about the mathematics and the physics",
        "Per document",
        "EPISTEMIC-IMPROVEMENTS.md",
        "CRITIQUE-AND-LIMITATIONS.md",
        "INTENSE-CRITIQUE-AND-LIMITATIONS.md",
        "INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md",
        "HPC-FOUNDATIONS.md",
        "QUANTUM-FOUNDATIONS-OF-SYMBLIC.md",
        "QUANTUM-DETERMINISM-ANALYSIS.md",
        "PHYSICS-AND-ADVANCED-MATHEMATICS.md",
        "GRAND-UNIFICATION-AND-STRING-THEORY.md",
        "Defects found while building 2.3, not changed by it"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 6,
          "bite": 3,
          "title": "Capstone 4: Full Neuro-Symbolic Mastery Exam"
        },
        {
          "level": 13,
          "bite": 3,
          "title": "Novelty, prior art and measured contribution"
        }
      ],
      "sha256": "b88f05969e9e90a5a633b170f402a7231e9cb5bc939d941efe076b2c315e36d7",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/REVIEW-2.3.md",
        "sha256": "b88f05969e9e90a5a633b170f402a7231e9cb5bc939d941efe076b2c315e36d7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Spec sheets: building a file from small checked units",
      "url": "/docs/reference/SPEC-SHEETS.md",
      "headings": [
        "Spec sheets: building a file from small checked units",
        "The format",
        "What the compiled program does",
        "Incremental rebuilds: keep what already passed",
        "When a unit stalls: diagnose the sheet, not the models",
        "Writing for small models",
        "The Tetris record (2026-10-04)",
        "What a passing build establishes, and what it does not",
        "Small local models (2026-10-10, the Atomic study)"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        },
        {
          "level": 14,
          "bite": 1,
          "title": "A sandboxed test is still a finite test"
        },
        {
          "level": 14,
          "bite": 2,
          "title": "Deterministic selection and preserving good work"
        }
      ],
      "sha256": "03801e47cb7a84177340302fc6819b5fc675db36f442a886b38aaf9b3e45c62b",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SPEC-SHEETS.md",
        "sha256": "03801e47cb7a84177340302fc6819b5fc675db36f442a886b38aaf9b3e45c62b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic 2.5 — specification",
      "url": "/docs/reference/SPEC.md",
      "headings": [
        "Symblic 2.5 — specification",
        "Current 2.5 contracts",
        "Declared raw JSON Code answers",
        "Preserved 2.4 code-generation contracts",
        "1. Lexical structure",
        "2. Statements",
        "3. Types and values",
        "4. Asks",
        "5. Checks and retries",
        "6. Applicators and placement",
        "7. Kernel",
        "8. Runs, records and replay",
        "9. API (`/api/automation/symblic/`, operator-only)",
        "10. Automation Studio nodes",
        "11. Building programs from parts (docs/reference/LANGUAGE-3.md)",
        "12. Predictability: measuring and raising agreement"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 0,
          "bite": 0,
          "title": "Two Brains in Your Computer"
        },
        {
          "level": 0,
          "bite": 1,
          "title": "Exact fractions and measured uncertainty"
        },
        {
          "level": 0,
          "bite": 2,
          "title": "Starting Your Program (`program Name.`)"
        },
        {
          "level": 0,
          "bite": 3,
          "title": "Storing Values with `let`"
        },
        {
          "level": 1,
          "bite": 0,
          "title": "What an assertion really establishes"
        },
        {
          "level": 1,
          "bite": 1,
          "title": "Bounded Integers (`Int in min..max`)"
        },
        {
          "level": 1,
          "bite": 2,
          "title": "Whole Number vs Exact Division (`//` vs `/`)"
        },
        {
          "level": 1,
          "bite": 3,
          "title": "Why exact computations have resource limits"
        },
        {
          "level": 2,
          "bite": 1,
          "title": "Asking with Strict Output Types (`ask`)"
        },
        {
          "level": 2,
          "bite": 2,
          "title": "Capsules: explicit and sufficient context"
        },
        {
          "level": 2,
          "bite": 3,
          "title": "The Effort Dial (`with effort=...`)"
        },
        {
          "level": 3,
          "bite": 0,
          "title": "Repairing candidates with ensure"
        },
        {
          "level": 3,
          "bite": 1,
          "title": "Rollback and the external-world boundary"
        },
        {
          "level": 3,
          "bite": 2,
          "title": "Bounded retries are not convergence"
        },
        {
          "level": 3,
          "bite": 3,
          "title": "Reading syntax and recognizing proposals"
        },
        {
          "level": 4,
          "bite": 0,
          "title": "Typed Tables"
        },
        {
          "level": 4,
          "bite": 1,
          "title": "Facts & Rules"
        },
        {
          "level": 4,
          "bite": 2,
          "title": "Querying Knowledge with `?`"
        },
        {
          "level": 10,
          "bite": 3,
          "title": "Discrete optimization, ties and witnesses"
        }
      ],
      "sha256": "f32d31d86e70987a242a4375cb7083ff2cfb424db3eede52da1a609ee976c6e8",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SPEC.md",
        "sha256": "f32d31d86e70987a242a4375cb7083ff2cfb424db3eede52da1a609ee976c6e8",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic study guide and executable tutorial",
      "url": "/docs/reference/STUDY-GUIDE.md",
      "headings": [
        "Symblic study guide and executable tutorial",
        "1. What Symblic does",
        "2. The bridge from human statements to checked execution",
        "3. Language Syntax & Reference",
        "3.1 Basic Declarations",
        "3.2 Types",
        "3.3 The Model Bridge: `ask`",
        "3.4 Verification & Self-Correction: `ensure` and `assert`",
        "3.5 Knowledge & Relational Reasoning: Datalog",
        "3.6 Functions and Routines",
        "3.7 Modules & Standard Library",
        "3.8 External Actions & Observations (`symblic/kernel/effects.py`)",
        "4. Comprehensive Hands-On Tutorial",
        "Lesson 1: Your First Script (Math & Model Working Together)",
        "Lesson 2: Typed extraction and its limits",
        "Lesson 3: Check a declared access model with Datalog",
        "Lesson 4: A human-authored proof",
        "5. Where to evaluate Symblic",
        "6. How to Run, Test, and Build Symblic Programs"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 7,
          "bite": 0,
          "title": "Syntax, semantics and pragmatics"
        }
      ],
      "sha256": "577df44ccceed86b90be64098119590d9feed6252567986f61f64e4b737429e8",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/STUDY-GUIDE.md",
        "sha256": "577df44ccceed86b90be64098119590d9feed6252567986f61f64e4b737429e8",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: Architectural Compendium",
      "url": "/docs/reference/SYMBLIC-BREAKTHROUGH-COMPENDIUM.md",
      "headings": [
        "Symblic: Architectural Compendium",
        "Table of Contents",
        "1. The Core Architecture & Separation of Concerns",
        "2. Formal Symbolic Logic Foundation & Its Scope",
        "The Formal Logic Pillars & Their Strict Boundaries:",
        "3. Controlled Natural Language & Bounded Contexts",
        "The Controlled Natural Language (CNL) Architecture",
        "The 4-Step Translation Method",
        "The Rosetta Stone",
        "4. File Types, Compilation & Runtime Pipeline",
        "File Types:",
        "Compilation & Execution Pipeline:",
        "5. Language Reference & Syntax",
        "Exact Rational Arithmetic",
        "The Type System",
        "The Model Bridge (`ask`)",
        "Datalog Horn Clauses",
        "Functions vs. Routines",
        "Tutorial Verification Examples",
        "Spider Study (Math + Bounded Fact)",
        "Invoice Extraction",
        "6. Architectural Comparison: Symblic vs. Python & Other Languages",
        "7. Empirical Cluster Receipts: Local Model Capabilities & Limits",
        "1. Multi-Hop Relational Logic (Family Trees, 15-Task Evaluation)",
        "2. Multi-Model Local Councils & Consensus Limits",
        "3. Checked Escalation (`route=escalate`)",
        "4. Spec-Sheet Builds by Local Models (Symblic 2.4, 2026-10-04)",
        "8. Backend Architecture: Python Runtime & Native Kernel Tradeoffs",
        "9. Large Contexts & Codebases: Relational Fact Extraction (Proposal)",
        "The Problem:",
        "The Proposed Approach: Codebase-as-a-Datalog-Database",
        "10. Finite Quadratic Minimization & Symblic 2.2 Integration",
        "1. Implemented Capabilities",
        "2. What the Energy Analogy Does NOT Prove",
        "11. High-Performance Computing (HPC) Execution & Distributed Scaling (Proposals)",
        "Path A: HPC Execution Runtime",
        "12. HPC Training & Reinforcement Learning with Verifiable Rewards (RLVR) (Proposals)",
        "What Should (and Should Not) Be Trained",
        "Would Training Make Significant Improvements?",
        "Could Training Cause Symblic to be WORSE? (Critical Failure Modes)",
        "Parameters & Data to Train On (proposal; none of this exists)",
        "13. Multi-frame checking: background",
        "Operational evidence, rather than a new score",
        "14. The Shippable Product Roadmap (Proposals)",
        "15. Strategic Roadmap for Future Verification Extensions",
        "1. Refinement Types (Proposal; not built)",
        "2. Calibrated Uncertainty (Proposal; not built)",
        "3. Linear Temporal Logic for Trajectories (Proposal; not built)",
        "4. Native SMT Solver Integration (Z3) (deferred)",
        "5. Formal Proof Export (Lean 4) (not built)",
        "16. Possible Applications & Assurance Boundaries",
        "17. How to Explain Symblic (Conceptual & Developer Summary)",
        "18. Focused Minimalist Visual Identity",
        "Brand Assets (`docs/reference/`; present in the working tree, not committed to git as of 2026-10-04):",
        "19. CLI Command Reference",
        "20. Symblic and Human Intersubjectivity: Background and Proposals",
        "20.1 The Epistemic Chasm: Why Humans Misunderstand Each Other",
        "20.2 Is \"True Empathy\" Possible?",
        "20.3 Four Proposals and Their Outcomes",
        "21. Expanded Minimalist Formal Logic Icon Suite",
        "22. Intersubjective & Epistemic Proposals for the Core: Outcomes",
        "22.1 The Draft's Five Claimed Deficiencies, Checked",
        "22.2 The Six Proposed Upgrades and What Happened",
        "23. Theoretical and Systems Critique of Symblic, Checked Against the Code",
        "23.1 The Seven Claimed Defects",
        "23.2 Proposed Remedies and Their Outcomes",
        "24. Adversarial Critique: Proof Theory, Information Flow and Effects, Checked Against the Code",
        "24.1 The Seven Claimed Contradictions",
        "24.2 Risk Matrix, Corrected",
        "25. Quantum Mathematics and Symblic (Q-Symblic): Proposals and What Was Built",
        "25.1 The Six Proposed Quantum Mappings",
        "26. Quantum Mechanics and Computational Determinism: What Is Deterministic in Symblic",
        "26.1 Physics and Simulation",
        "26.2 What Is and Is Not Deterministic in Symblic",
        "26.3 Proposed \"Quantum\" Remedies and Their Outcomes",
        "27. Mathematical Physics: The September 2026 Navier-Stokes Announcement and Physics Proposals",
        "27.1 The Navier-Stokes Announcement",
        "27.2 Physics Proposals and Their Outcomes",
        "28. Analogies from Higher Physics and Mathematics: Proposals and Outcomes",
        "28.1 The Six Proposals",
        "29. The \"Universal Epistemic Operating System\" Proposal: Status",
        "29.1 The Five Proposed Layers",
        "29.2 An Analogy: Continuous and Discrete Computation",
        "29.3 Constructive operating layer: installed foundation and construction interfaces",
        "References"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 13,
          "bite": 3,
          "title": "Novelty, prior art and measured contribution"
        }
      ],
      "sha256": "6e8ec609fc8eadf94a3401a6cddba2d4d20b1e0832958b892d70fffd602ae442",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SYMBLIC-BREAKTHROUGH-COMPENDIUM.md",
        "sha256": "6e8ec609fc8eadf94a3401a6cddba2d4d20b1e0832958b892d70fffd602ae442",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic's architectural thesis and the evidence it needs",
      "url": "/docs/reference/THE-OVERALL-BREAKTHROUGH.md",
      "headings": [
        "Symblic's architectural thesis and the evidence it needs",
        "The concrete architectural claim",
        "Four different promises",
        "The reform's core components",
        "What “a network of agents” means",
        "“Universal epistemic operating system” as a research objective",
        "Claims this revision withdraws",
        "Prior systems define the comparison, not the conclusion",
        "Experiments that could establish value"
      ],
      "status": "Exploratory research / proposals and analogies; see lesson limits",
      "lessons": [
        {
          "level": 13,
          "bite": 3,
          "title": "Novelty, prior art and measured contribution"
        }
      ],
      "sha256": "0f2711339ac5775ec231cb03719b1fc111368d95ab3544ce0887a196c35e002c",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/THE-OVERALL-BREAKTHROUGH.md",
        "sha256": "0f2711339ac5775ec231cb03719b1fc111368d95ab3544ce0887a196c35e002c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Exact finite one-dimensional transport",
      "url": "/docs/reference/TRANSPORT.md",
      "headings": [
        "Exact finite one-dimensional transport",
        "Input and result",
        "Bounds and refusals",
        "Kernel attachment",
        "What the checks establish"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 10,
          "bite": 2,
          "title": "Optimal transport sees what a median loses"
        }
      ],
      "sha256": "7dceb0178e9976088fbe0bf0be76bc730aeb8f38a0e720b0e0eb5266fed3239e",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/TRANSPORT.md",
        "sha256": "7dceb0178e9976088fbe0bf0be76bc730aeb8f38a0e720b0e0eb5266fed3239e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Exact finite quadratic minimization",
      "url": "/docs/reference/VARIATIONAL.md",
      "headings": [
        "Exact finite quadratic minimization",
        "Interface and current integration",
        "What the witness establishes",
        "Deterministic resource limits",
        "What the energy analogy does not prove",
        "Focused verification"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 1,
          "bite": 3,
          "title": "Why exact computations have resource limits"
        },
        {
          "level": 3,
          "bite": 2,
          "title": "Bounded retries are not convergence"
        },
        {
          "level": 5,
          "bite": 3,
          "title": "Energy methods and their assumptions"
        },
        {
          "level": 10,
          "bite": 0,
          "title": "Positive-definite quadratics and uniqueness"
        },
        {
          "level": 10,
          "bite": 1,
          "title": "Projection repairs values; it does not reveal truth"
        },
        {
          "level": 12,
          "bite": 0,
          "title": "From a weak form to a finite energy problem"
        }
      ],
      "sha256": "314b4fc38e64eefe25f1dadf9b202814e84770d8ca16e1cf17bb0c39a6308127",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/VARIATIONAL.md",
        "sha256": "314b4fc38e64eefe25f1dadf9b202814e84770d8ca16e1cf17bb0c39a6308127",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Finite owner-intent dataset, version 1",
      "url": "/symblic/bench/data/ambiguity-v1.md",
      "headings": [
        "Finite owner-intent dataset, version 1",
        "What the pairs establish",
        "Case contract",
        "Clarification protocol",
        "Families and split boundary",
        "Conditions and assessment boundaries",
        "Integrity and reporting"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "2f685c721fc2525577033e561ff84883f4d698e6df401725649b87bcf46f3e11",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/symblic/bench/data/ambiguity-v1.md",
        "sha256": "2f685c721fc2525577033e561ff84883f4d698e6df401725649b87bcf46f3e11",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "ambiguity v1",
      "url": "/symblic/bench/data/ambiguity-v1.json",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "3ac497db466b31f854ea45ca98e783ac4020220fcb26c5b998971f5afe400b67",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/symblic/bench/data/ambiguity-v1.json",
        "sha256": "3ac497db466b31f854ea45ca98e783ac4020220fcb26c5b998971f5afe400b67",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Elements",
      "url": "/examples/crystals/elements.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "f58fa3ae327ce757f6d6a56514ace5e60d2d4a5331f958956dff1901e785e6d6",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/crystals/elements.sym",
        "sha256": "f58fa3ae327ce757f6d6a56514ace5e60d2d4a5331f958956dff1901e785e6d6",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "is_metal crystal",
      "url": "/examples/crystals/is_metal.crystal.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "ce127197915b4b564096cbbf08e16dc3e67fbf43d508bc8f6c8355d7671a7586",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/crystals/is_metal.crystal.sym",
        "sha256": "ce127197915b4b564096cbbf08e16dc3e67fbf43d508bc8f6c8355d7671a7586",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 03 conformance v3",
      "url": "/docs/reference/evidence/2026-10-03-conformance-v3.json",
      "headings": [],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "eba104418d860e07b7ae59cc914a355330530b3e1b019f9c2c894380076a3acc",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-03-conformance-v3.json",
        "sha256": "eba104418d860e07b7ae59cc914a355330530b3e1b019f9c2c894380076a3acc",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 03 contract pilot llama1b",
      "url": "/docs/reference/evidence/2026-10-03-contract-pilot-llama1b.json",
      "headings": [],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "d59e942978d4fd6963c53c02b3202ad533850274edd3ecc4461d52cf9bb64f5c",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-03-contract-pilot-llama1b.json",
        "sha256": "d59e942978d4fd6963c53c02b3202ad533850274edd3ecc4461d52cf9bb64f5c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 03 contract pilot qwen4b",
      "url": "/docs/reference/evidence/2026-10-03-contract-pilot-qwen4b.json",
      "headings": [],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "6fda1425d157f1e2f0313887a75f5570d0411d05b45eba567b6ae62ccce946c9",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-03-contract-pilot-qwen4b.json",
        "sha256": "6fda1425d157f1e2f0313887a75f5570d0411d05b45eba567b6ae62ccce946c9",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Four plus four",
      "url": "/examples/01-four-plus-four.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "7a59b5f59d5a43baaab5b838f62adecc9dcc3efd41193c1f629c22f873019b69",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/01-four-plus-four.sym",
        "sha256": "7a59b5f59d5a43baaab5b838f62adecc9dcc3efd41193c1f629c22f873019b69",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Formal flower",
      "url": "/examples/02-flower-formal.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "553501c4868cdaa142b4b04e41b323ab7a33d45e3e7d6ea900b6c84049ff34e4",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/02-flower-formal.sym",
        "sha256": "553501c4868cdaa142b4b04e41b323ab7a33d45e3e7d6ea900b6c84049ff34e4",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Flower from an essay",
      "url": "/examples/03-flower-from-essay.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "aecf9dec24899da1cc65dddcbab407679986c0073388fedd5df5363b49809efd",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/03-flower-from-essay.sym",
        "sha256": "aecf9dec24899da1cc65dddcbab407679986c0073388fedd5df5363b49809efd",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Family logic",
      "url": "/examples/04-family-logic.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "72666ec1689a8e0cd4d244bca71086695ad098e8689094696c5b9cf67f21d2a7",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/04-family-logic.sym",
        "sha256": "72666ec1689a8e0cd4d244bca71086695ad098e8689094696c5b9cf67f21d2a7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Word problem, translated then computed",
      "url": "/symblic/bench/data/local_beta/fixtures/native/word-problem.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "cbab492d59899e97a69d50899a13313bd71f400ce9d69e217b68af590032891b",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/symblic/bench/data/local_beta/fixtures/native/word-problem.sym",
        "sha256": "cbab492d59899e97a69d50899a13313bd71f400ce9d69e217b68af590032891b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Small-model council",
      "url": "/examples/06-small-model-council.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "3185edf2a718ed85e55ed87f819d84c76f5f902b34ab521338a54fa9c0bc6ba2",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/06-small-model-council.sym",
        "sha256": "3185edf2a718ed85e55ed87f819d84c76f5f902b34ab521338a54fa9c0bc6ba2",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Local-model decisions",
      "url": "/examples/07-local-model-decisions.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "7dd21f3abb72d54ba0462a58f05d655341dfbd6b0639e6effd91150eb3c7b48a",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/07-local-model-decisions.sym",
        "sha256": "7dd21f3abb72d54ba0462a58f05d655341dfbd6b0639e6effd91150eb3c7b48a",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "08 v1 prose",
      "url": "/examples/08-v1-prose.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "1223e1e831eea87289705b11a70869e28035c87539b7abdf76ef73e5269b2e01",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/08-v1-prose.sym",
        "sha256": "1223e1e831eea87289705b11a70869e28035c87539b7abdf76ef73e5269b2e01",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Council then Triad",
      "url": "/examples/09-council-and-triad.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "9f9e300fe37e60d5deedddd015e9d49f1eb0d772492734fecc891c7aee5c2aaa",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/09-council-and-triad.sym",
        "sha256": "9f9e300fe37e60d5deedddd015e9d49f1eb0d772492734fecc891c7aee5c2aaa",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Kernel identity",
      "url": "/examples/10-kernel-identity.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "3541f4617611d916ec2483957489d5b2ae96b18de2d782feda6b24e208a76e0a",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/10-kernel-identity.sym",
        "sha256": "3541f4617611d916ec2483957489d5b2ae96b18de2d782feda6b24e208a76e0a",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Checked routing and kernel solving",
      "url": "/examples/11-checked-routing.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "f348cba4c979227390c47b7b74bcc087e03cb8760e5c19443c3cea55386306a2",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/11-checked-routing.sym",
        "sha256": "f348cba4c979227390c47b7b74bcc087e03cb8760e5c19443c3cea55386306a2",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Finite ambiguity has witnesses",
      "url": "/examples/12-finite-ambiguity.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "aa614553fa1e052ac0e83d59f9b8318ca4cedf5762869285023c23ca4bf33d15",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/12-finite-ambiguity.sym",
        "sha256": "aa614553fa1e052ac0e83d59f9b8318ca4cedf5762869285023c23ca4bf33d15",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Two accounts of one event",
      "url": "/tests/kernel/fixtures/13-two-accounts.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "e81853551f7ce4c30fb41eced57d9fa68e383ed31afae51e7d8544033c2bc4f4",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/tests/kernel/fixtures/13-two-accounts.sym",
        "sha256": "e81853551f7ce4c30fb41eced57d9fa68e383ed31afae51e7d8544033c2bc4f4",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Two yes/no questions",
      "url": "/examples/14-question-order.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 11,
          "bite": 1,
          "title": "Noncommuting projections and question order"
        }
      ],
      "sha256": "245d4083629e9b5fad4dfaef8e978bacef554e440e0be858e381615e3b36bdf5",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/14-question-order.sym",
        "sha256": "245d4083629e9b5fad4dfaef8e978bacef554e440e0be858e381615e3b36bdf5",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Exact quadratic witness",
      "url": "/examples/quadratic-witness.sym",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 10,
          "bite": 0,
          "title": "Positive-definite quadratics and uniqueness"
        }
      ],
      "sha256": "9455d8ef6112f905ad24ccded143f3e01c8ef6aa5d52b214b2c60920487e853d",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/quadratic-witness.sym",
        "sha256": "9455d8ef6112f905ad24ccded143f3e01c8ef6aa5d52b214b2c60920487e853d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "tetris.html",
      "url": "/kits/tetris/sheets/tetris.sheet.md",
      "headings": [
        "tetris.html",
        "Shared",
        "Unit `SHAPES, COLORS`",
        "Unit `KICKS_JLSTZ, KICKS_I`",
        "Unit `mulberry32(seed)`",
        "Unit `cellsOf(type, rot)`",
        "Unit `emptyBoard()`",
        "Unit `fits(board, type, rot, row, col)`",
        "Unit `levelOf(lines), gravityMs(level)`",
        "Unit `refill(g)`",
        "Unit `spawn(g, type)`",
        "Unit `newGame(seed)`",
        "Unit `resting(g), afterMove(g, wasResting)`",
        "Unit `moveSide(g, dc), softDrop(g)`",
        "Unit `rotate(g, dir)`",
        "Unit `lockPiece(g)`",
        "Unit `hardDrop(g)`",
        "Unit `holdPiece(g)`",
        "Unit `step(g), tick(g, ms)`",
        "Unit `input(g, action)`",
        "Unit `snapshot(g)`",
        "Unit `keyAction(e)`",
        "Unit `drawCell(ctx, r, c, color)`",
        "Unit `drawBoard(g, board)`",
        "Unit `drawSide(g, side)`",
        "Unit `draw(g, board, side)`",
        "Unit `startGame()`",
        "Assemble `tetris.html`"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "960916e271ece6f79d0ac4daba59e0228af3b7c858c91a16be85c0b682da6f78",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/tetris/sheets/tetris.sheet.md",
        "sha256": "960916e271ece6f79d0ac4daba59e0228af3b7c858c91a16be85c0b682da6f78",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "kernel identity",
      "url": "/docs/reference/kernel-identity.json",
      "headings": [],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "040eb2f19ea482a837fe6613431b448de60829b43ea0a048d460516a80ed6ccd",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/kernel-identity.json",
        "sha256": "040eb2f19ea482a837fe6613431b448de60829b43ea0a048d460516a80ed6ccd",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Writing a paper that reproduces",
      "url": "/docs/reference/papers/README.md",
      "headings": [
        "Writing a paper that reproduces",
        "The loop",
        "Rules that made the furnace paper reproduce",
        "Examples here",
        "Note for this repository"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "5341338899fcfe0acc8ac87976cd6ab4150830004b5f0d95fad2516f5e2e56b8",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/papers/README.md",
        "sha256": "5341338899fcfe0acc8ac87976cd6ab4150830004b5f0d95fad2516f5e2e56b8",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Constructing a cube from its description",
      "url": "/docs/reference/papers/constructing-a-cube.symd",
      "headings": [
        "effort: medium",
        "Constructing a cube from its description",
        "Definitions",
        "The object",
        "Construction",
        "End state",
        "Result"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "4ed57fe4fd9b08a4bb83752ee20e07efadf3da24c02c7bd539fc2d74954caa39",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/papers/constructing-a-cube.symd",
        "sha256": "4ed57fe4fd9b08a4bb83752ee20e07efadf3da24c02c7bd539fc2d74954caa39",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "A furnace schedule (contract)",
      "url": "/docs/reference/papers/furnace-schedule-contract.symd",
      "headings": [
        "effort: high",
        "A furnace schedule (contract)",
        "Definitions",
        "The protocol",
        "Reading the steps",
        "Duration"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "886709322584268d0b0a5f1d5a350cd1bc2d4fbae548b7c5f5241421f8d73de1",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/papers/furnace-schedule-contract.symd",
        "sha256": "886709322584268d0b0a5f1d5a350cd1bc2d4fbae548b7c5f5241421f8d73de1",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "A furnace schedule (draft)",
      "url": "/docs/reference/papers/furnace-schedule-draft.symd",
      "headings": [
        "effort: high",
        "A furnace schedule (draft)",
        "The protocol",
        "Reading the steps",
        "Duration"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "650fc2703b07e7d242979bd6aebdf647174981fe6a3c69915fbc7f2483f0e971",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/papers/furnace-schedule-draft.symd",
        "sha256": "650fc2703b07e7d242979bd6aebdf647174981fe6a3c69915fbc7f2483f0e971",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "A furnace schedule",
      "url": "/docs/reference/papers/furnace-schedule.symd",
      "headings": [
        "effort: high",
        "A furnace schedule",
        "Definitions",
        "The protocol",
        "Reading the steps",
        "Duration"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "3be60a91a2602be52b7bb059a72d34618b98e16a1e47b847e48d032205f1edde",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/papers/furnace-schedule.symd",
        "sha256": "3be60a91a2602be52b7bb059a72d34618b98e16a1e47b847e48d032205f1edde",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Scaling a recipe",
      "url": "/docs/reference/papers/scaling-a-recipe.symd",
      "headings": [
        "effort: high",
        "Scaling a recipe",
        "Definitions",
        "The recipe",
        "Reading the quantities",
        "Scaling"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "71c8c525d0d19e9d92090448ffed8395ba375df8135124d0d1d287abb30bb2dc",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/papers/scaling-a-recipe.symd",
        "sha256": "71c8c525d0d19e9d92090448ffed8395ba375df8135124d0d1d287abb30bb2dc",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Preparing a ceramic slurry (draft)",
      "url": "/docs/reference/papers/slurry-draft.symd",
      "headings": [
        "effort: high",
        "Preparing a ceramic slurry (draft)",
        "The recipe",
        "Weighing"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "f476bcf16e5ca93e60b938719dd38cda4055168fcc065b2eee8c01c2978ae16c",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/papers/slurry-draft.symd",
        "sha256": "f476bcf16e5ca93e60b938719dd38cda4055168fcc065b2eee8c01c2978ae16c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Preparing a ceramic slurry",
      "url": "/docs/reference/papers/slurry.symd",
      "headings": [
        "effort: high",
        "Preparing a ceramic slurry",
        "Definitions",
        "The recipe",
        "Reading the recipe",
        "Weighing"
      ],
      "status": "Language contract / inspect current version",
      "lessons": [
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "sha256": "17dd8ba304188345e0b8fc28033baabab0372c6acbc9eb179bf943d65970c075",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/papers/slurry.symd",
        "sha256": "17dd8ba304188345e0b8fc28033baabab0372c6acbc9eb179bf943d65970c075",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Benchmark statistics reinforcement: bounded first pass",
      "url": "/docs/reference/reinforcements/benchmark-review.md",
      "headings": [
        "Benchmark statistics reinforcement: bounded first pass",
        "Source findings and concrete adoption priorities",
        "Manifest and CLI contract",
        "Output and interpretation",
        "Coordinator adoption checklist and validation"
      ],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "16e4c5cb4406b018791944a0b51a536d2e18917a569d3da0836d94dc3b21d791",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/reinforcements/benchmark-review.md",
        "sha256": "16e4c5cb4406b018791944a0b51a536d2e18917a569d3da0836d94dc3b21d791",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic spec self-sufficiency replication",
      "url": "/docs/reference/reinforcements/communication-review.md",
      "headings": [
        "Symblic spec self-sufficiency replication",
        "Protocol and exposure",
        "Initial versus corrected outcomes",
        "1. Exact arithmetic — initial and final `01-arithmetic.sym`",
        "2. Typed record — initial `02-record.sym`",
        "3. Transitive family — initial and final `03-family.sym`",
        "4. Flower and polygon — initial and final `04-drawings.sym`",
        "5. Cube representation — initial `05-cube.sym`",
        "Precise spec changes for the coordinator",
        "Reproduction and verification"
      ],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 0,
          "bite": 2,
          "title": "Starting Your Program (`program Name.`)"
        },
        {
          "level": 4,
          "bite": 2,
          "title": "Querying Knowledge with `?`"
        }
      ],
      "sha256": "992d623a85a9be3ba1b27472996678b2b6a54383051e3c79cd23e30bd2c5a802",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/reinforcements/communication-review.md",
        "sha256": "992d623a85a9be3ba1b27472996678b2b6a54383051e3c79cd23e30bd2c5a802",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic contract audit: bounded offline reinforcement",
      "url": "/docs/reference/reinforcements/contract-audit.md",
      "headings": [
        "Symblic contract audit: bounded offline reinforcement",
        "Existing coverage and the added checks",
        "Confirmed baseline defects: reproductions for the coordinator",
        "R1 — ensure retry budget can be spent replaying the rejected answer",
        "C1 — canonical type tags collide with ordinary records",
        "C2 — conflicting record aliases are order-dependent when no exact key exists",
        "Policy and documentation gaps, not confirmed implementation defects",
        "Verification and integration handoff",
        "Coordinator verification after integration"
      ],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "a45e50b474d683043e8342fa2474a7cb3c7ecaa0dee9426087f599e2f5cef780",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/reinforcements/contract-audit.md",
        "sha256": "a45e50b474d683043e8342fa2474a7cb3c7ecaa0dee9426087f599e2f5cef780",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Cube reconstruction protocol: exact shape, placement, and agreement",
      "url": "/docs/reference/reinforcements/cube-protocol.md",
      "headings": [
        "Cube reconstruction protocol: exact shape, placement, and agreement",
        "Question and falsifiable claims",
        "Target and equivalence contract",
        "Independent oracle and proof obligation",
        "Compact current-language examples",
        "Minimal falsifying regression for the core operator",
        "Executable offline reference and adversarial fixtures",
        "Proposed experiment, held-out descriptions, and independence",
        "Analysis and reporting plan",
        "Basis and validation status",
        "Coordinator verification of the newer geometry kernel"
      ],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "ebd32d22487221ce20b6acdabc4c698943bd287349836b5dc7150ca56d60ab0e",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/reinforcements/cube-protocol.md",
        "sha256": "ebd32d22487221ce20b6acdabc4c698943bd287349836b5dc7150ca56d60ab0e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic semantics review: compiler-design pass",
      "url": "/docs/reference/reinforcements/semantics-review.md",
      "headings": [
        "Symblic semantics review: compiler-design pass",
        "1. Findings",
        "2. Guarantee map",
        "3. Grammar draft (EBNF, derived from the parser)",
        "Grammar ambiguities found",
        "4. Five highest-priority confirmed reproductions",
        "R1. Formal-looking lines become model calls [measured]",
        "R2. `ensure … else retry` is not transactional and ignores KB data flow [measured]",
        "R3. `ask … for each` builds capsules from shared instance state [measured]",
        "R4. Kernel results depend on the environment [measured]",
        "R5. `check()` accepts programs that fail for static reasons [measured]",
        "5. Other findings",
        "5.1 Confirmed at the baseline, lower priority",
        "5.2 Resolved in the coordinator's current snapshot",
        "6. Architecture proposal: kernel rules for the unresolved behaviours",
        "7. Five prioritized recommendations (implementable now)",
        "1. Make retry transactional and data-flow anchored (K4)",
        "2. Pass capsule inputs per item (prompt determinism under `for each`)",
        "3. Add a kernel purity gate and record KERNEL_ID (K2, K8)",
        "4. Make the formal/prose boundary explicit (K1)",
        "5. Make the static check sound (K5)",
        "Next, after the five",
        "8. Claim wording these results support",
        "9. Sources",
        "Appendix A. Reproduction script and output",
        "Appendix B. Scope and checks",
        "Coordinator verification after integration"
      ],
      "status": "Dated evidence or review / scope tied to its snapshot",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        }
      ],
      "sha256": "38d61c836c61bf53fbb8e4d325636fe5b11193fcbfe326a3816f3dfb458a5471",
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/reinforcements/semantics-review.md",
        "sha256": "38d61c836c61bf53fbb8e4d325636fe5b11193fcbfe326a3816f3dfb458a5471",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Explicit finite-domain logic, version 1",
      "headings": [
        "Explicit finite-domain logic, version 1",
        "API and authority",
        "Source JSON AST",
        "Controlled human syntax",
        "Exact lowering and namespaces",
        "Bounds and receipts",
        "Verification and integration boundary"
      ],
      "sha256": "7bb509f60d3e6b7c5b672daf4ae8a3aa1966e765b69fa52cf5a2e0f2dc6ca848",
      "url": "/docs/reference/FINITE-LOGIC.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Finite-domain expansion and proof-checking boundaries; inspect explicit domains, assumptions and resource limits.",
      "lessons": [
        {
          "level": 1,
          "bite": 0,
          "title": "What an assertion really establishes"
        },
        {
          "level": 4,
          "bite": 1,
          "title": "Facts & Rules"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/FINITE-LOGIC.md",
        "sha256": "7bb509f60d3e6b7c5b672daf4ae8a3aa1966e765b69fa52cf5a2e0f2dc6ca848",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Matched evaluation protocol",
      "headings": [
        "Matched evaluation protocol",
        "Freeze, run, resume and report",
        "Exact task exposure",
        "Declaration and boundaries",
        "Arm order",
        "Cells, outcomes and unresolved pairs",
        "Held-out integrity and durable evidence",
        "Known and unknown cost",
        "Versions and version 1 reports",
        "Paired obligation feasibility, 5 October 2026",
        "Focus versus task-card feasibility, 5 October 2026"
      ],
      "sha256": "09339bdd1e5b89b06c75ca1ae778cd3d333021064490df34e52bfa80281f04f7",
      "url": "/docs/reference/MATCHED-EVALUATION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Frozen comparison protocol, strict scoring and all-assigned accounting; documentation is not a measured performance result.",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        },
        {
          "level": 13,
          "bite": 1,
          "title": "The denominator and the unit of independence"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/MATCHED-EVALUATION.md",
        "sha256": "09339bdd1e5b89b06c75ca1ae778cd3d333021064490df34e52bfa80281f04f7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Bounded finite-candidate policy selection, version 1",
      "headings": [
        "Bounded finite-candidate policy selection, version 1",
        "Authority and workflow",
        "Public APIs",
        "Exact input schemas",
        "Exact objective, denominators and uncertainty",
        "Heldout schema and result",
        "Graph-runtime integration boundary",
        "Bounded CLI and verification"
      ],
      "sha256": "e3665c8255b05ad40fc9c8873679edc81d1aff3ce97478a2981c11b0d0e6252c",
      "url": "/docs/reference/POLICY-LEARNING.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Bounded candidate-policy selection and held-out evaluation contracts; source metadata does not show measured improvement.",
      "lessons": [
        {
          "level": 13,
          "bite": 1,
          "title": "The denominator and the unit of independence"
        },
        {
          "level": 14,
          "bite": 2,
          "title": "Deterministic selection and preserving good work"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/POLICY-LEARNING.md",
        "sha256": "e3665c8255b05ad40fc9c8873679edc81d1aff3ce97478a2981c11b0d0e6252c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Proof terms, version 1 — integrated 2.5 interface",
      "headings": [
        "Proof terms, version 1 — integrated 2.5 interface",
        "Caller API and trust boundary",
        "Exact term grammar",
        "Receipts and limits",
        "Human-readable formulas",
        "Existing Symblic 2.5 integration"
      ],
      "sha256": "e11ab252af55be5460cf7bde3bb3dd55b2f4db6ae2cfc5f9d76b4a1659b74e29",
      "url": "/docs/reference/PROOF-TERMS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Propositional proof-term grammar and checking contract; checked derivations remain conditional on premises.",
      "lessons": [
        {
          "level": 1,
          "bite": 0,
          "title": "What an assertion really establishes"
        },
        {
          "level": 13,
          "bite": 2,
          "title": "Counterexamples, vacuity and specification gaming"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROOF-TERMS.md",
        "sha256": "e11ab252af55be5460cf7bde3bb3dd55b2f4db6ae2cfc5f9d76b4a1659b74e29",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Exact quantities and measurement intervals",
      "headings": [
        "Exact quantities and measurement intervals",
        "Existing-language interface",
        "Dimensions and unit definitions",
        "Absolute temperature and differences",
        "Bounds, dependence, and declared precision",
        "Sources, time, and recovery identities",
        "Resource and integration contract"
      ],
      "sha256": "da51ca36033768d811379bf3f35b389457e1a0655c1b378cafafadca92fb2441",
      "url": "/docs/reference/QUANTITIES.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Explicit dimensions, intervals and quantity provenance; inspect the supported operations and uncertainty assumptions.",
      "lessons": [
        {
          "level": 0,
          "bite": 1,
          "title": "Exact fractions and measured uncertainty"
        },
        {
          "level": 7,
          "bite": 1,
          "title": "Operational definitions and boundary cases"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/QUANTITIES.md",
        "sha256": "da51ca36033768d811379bf3f35b389457e1a0655c1b378cafafadca92fb2441",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic reform: executable statements, conditional evidence and agent networks",
      "headings": [
        "Symblic reform: executable statements, conditional evidence and agent networks",
        "Objective and revised foundation",
        "Component evidence snapshot",
        "Full critique-to-remedy register",
        "Integration contracts",
        "Model construction stays separate from authority",
        "Evidence must be operational",
        "Context is a declared input contract",
        "Networks use existing execution and fleet boundaries",
        "Learning changes a candidate, then earns adoption",
        "Evaluation needed before stronger claims",
        "Local-model observations",
        "Completed matched integration pilot — 5 October 2026 UTC",
        "Exact-command menu diagnostic — 5 October 2026 UTC",
        "Model-first construction and exact agent handoffs — 5 October 2026 UTC",
        "Exact intermediate obligations — 5 October 2026 UTC",
        "Focused agent handoffs and count diagnostics — 5 October 2026 UTC",
        "Remaining work and completion evidence",
        "Installed recovery guard",
        "Historical worker-audit scope",
        "Bounded construction analysis and bookkeeping — 5 October 2026 UTC",
        "Paired obligation pilot — 5 October 2026 UTC",
        "Agent proof task cards — 5 October 2026 UTC",
        "Real task-card pilot — 5 October 2026 UTC"
      ],
      "sha256": "341772ced3dafb91a9dfdf964fa4141f13128d2b7bbad5299b33cde534dc13a4",
      "url": "/docs/reference/REFORM-3.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Design and integration record; read its dated component evidence and deployment qualifications.",
      "lessons": [
        {
          "level": 0,
          "bite": 0,
          "title": "Two Brains in Your Computer"
        },
        {
          "level": 14,
          "bite": 3,
          "title": "Your research-to-program capstone"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/REFORM-3.md",
        "sha256": "341772ced3dafb91a9dfdf964fa4141f13128d2b7bbad5299b33cde534dc13a4",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Source witnesses in ordinary Symblic",
      "headings": [
        "Source witnesses in ordinary Symblic",
        "Caller-held contracts",
        "Summary and enumeration coverage",
        "Model construction in the existing text library"
      ],
      "sha256": "a975093e9a56db912c25c44a1c2e74d733ed4c1aec851d0d69207e373849a05d",
      "url": "/docs/reference/SOURCE-WITNESSES.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Source revision, span and coverage contracts; a source match does not establish external truth.",
      "lessons": [
        {
          "level": 6,
          "bite": 0,
          "title": "Capstone 1: The Automated Invoice Auditor"
        },
        {
          "level": 9,
          "bite": 2,
          "title": "Evidence strength and evidence security"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SOURCE-WITNESSES.md",
        "sha256": "a975093e9a56db912c25c44a1c2e74d733ed4c1aec851d0d69207e373849a05d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "matched example v1",
      "headings": [],
      "sha256": "9ecedca84969d2538a99b3a84b2fb7f9e0c56b3eb1067bca02d28780c4644b9b",
      "url": "/symblic/bench/data/matched-example-v1.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Synthetic evaluation manifest with placeholder applicators; not model-run evidence or a capability claim.",
      "lessons": [
        {
          "level": 13,
          "bite": 1,
          "title": "The denominator and the unit of independence"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/symblic/bench/data/matched-example-v1.json",
        "sha256": "9ecedca84969d2538a99b3a84b2fb7f9e0c56b3eb1067bca02d28780c4644b9b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "claims",
      "headings": [],
      "sha256": "4a120309edeaa96ace8b459d8aea207835a3fd06d57bf6ecc59ea389e6778d12",
      "url": "/docs/reference/claims.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public claim registry; indexing preserves the file without independently verifying its entries.",
      "lessons": [
        {
          "level": 9,
          "bite": 2,
          "title": "Evidence strength and evidence security"
        },
        {
          "level": 13,
          "bite": 3,
          "title": "Novelty, prior art and measured contribution"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/claims.json",
        "sha256": "4a120309edeaa96ace8b459d8aea207835a3fd06d57bf6ecc59ea389e6778d12",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Contracted agent graphs: planner, durable runtime and operator interface",
      "headings": [
        "Contracted agent graphs: planner, durable runtime and operator interface",
        "APIs and node contract",
        "Results: contract support is not factual truth",
        "Durability and recovery",
        "Routing and effects support matrix",
        "Operator API and Graphs interface",
        "Reusing groups of nodes",
        "Limits and routing evidence",
        "Symblic 2.5 integration"
      ],
      "sha256": "f4c2c336c6626fbb6e46dfe8a61bf8e2e0e59c5141308d27077013560ce23be0",
      "url": "/docs/reference/AGENT-GRAPHS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        },
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/AGENT-GRAPHS.md",
        "sha256": "f4c2c336c6626fbb6e46dfe8a61bf8e2e0e59c5141308d27077013560ce23be0",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Durable finite policy experiments",
      "headings": [
        "Durable finite policy experiments",
        "Freeze before execution",
        "Host API",
        "Recovery",
        "Executable graph route selection",
        "Implementation and host identity",
        "Operator API, interface and current evidence"
      ],
      "sha256": "702407bb375391e6fcd882ddcd6a08577fc1cabca51bd5da139ea7d352d7fdc3",
      "url": "/docs/reference/POLICY-EXPERIMENTS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/POLICY-EXPERIMENTS.md",
        "sha256": "702407bb375391e6fcd882ddcd6a08577fc1cabca51bd5da139ea7d352d7fdc3",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Flat natural-deduction proof certificates",
      "headings": [
        "Flat natural-deduction proof certificates",
        "Public contract",
        "Rules",
        "Bounds and receipts",
        "Native language and compiler integration"
      ],
      "sha256": "472d9cd34a2851c2bc94f01f63ca4aa17cae79d2b81963e98d2f3c95a6243ecb",
      "url": "/docs/reference/PROOF-STEPS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROOF-STEPS.md",
        "sha256": "472d9cd34a2851c2bc94f01f63ca4aa17cae79d2b81963e98d2f3c95a6243ecb",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Full Symblic record — 6 October 2026",
      "headings": [
        "Full Symblic record — 6 October 2026",
        "Contents",
        "1. The practical starting point",
        "2. Four ways to give an instruction",
        "3. The terminal workspace and its controls",
        "4. Fresh contexts, explicit dependencies and persistent files",
        "5. Agents, three Qwen seats and execution machines",
        "6. Projects, files, normal shells and remote checkouts",
        "7. Durable task records, recovery and cancellation",
        "8. The bounded OS command language",
        "9. Native Symblic language and exact execution",
        "10. Model asks, checks, context and routing",
        "11. Checked English and generated displays",
        "12. Workcards, steps, task cards and spec sheets",
        "13. Proofs, finite mathematics and research adapters",
        "14. Graphs, delegation, effects, memory and supervisors",
        "15. Claude Cloud as a practical CLI",
        "16. Local source tools and pinned upstream repositories",
        "17. Command reference",
        "Native language and authoring",
        "Construction, graphs, memory and research",
        "Distillation",
        "18. HTTP and source architecture reference",
        "19. How Symblic developed and what it has built",
        "Recorded constructions and what their evidence means",
        "20. Practical recipes and diagnosis",
        "21. Verification record and live sign-off",
        "22. Operational boundaries and future work",
        "23. Complete documentation catalogue",
        "24. Addendum — 7 October 2026: Forge",
        "24.1 The new workflow and its boundaries",
        "24.2 Forge: from original intention to accepted decisions",
        "24.3 Engineering structure, quantities and controlled model assistance",
        "24.4 Forge exports, commands and recovery",
        "24.5 Forge verification and actual use",
        "24.6 to 24.8 (removed)",
        "24.9 How this extends the original Symblic work",
        "25. Configurable teams and focused authoring — 2026-10-07 follow-up",
        "25.1 One English editor and retained tools",
        "25.2 Exact team contract",
        "25.3 Checked statements, fresh contexts and recovery",
        "25.4 Project teams and devices",
        "25.5 Forge teams and critique",
        "25.6 Creative lenses and atomic instruction teaching",
        "25.7 Verification record for this follow-up",
        "25.8 Selected-device browser proposals"
      ],
      "sha256": "de3d1b7b4a8bda8c92ce7011473d899f6dac5c4630f2270becbd3680b57d6753",
      "url": "/docs/reference/2026-10-06-full-symblic.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/2026-10-06-full-symblic.md",
        "sha256": "de3d1b7b4a8bda8c92ce7011473d899f6dac5c4630f2270becbd3680b57d6753",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 07 forge integrations evidence",
      "headings": [],
      "sha256": "67ec38dbe883ef40b3cde82f0c1bab3c4986d9bf858d7d57d27c9c7ea7aa6656",
      "url": "/docs/reference/2026-10-07-forge-integrations-evidence.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/2026-10-07-forge-integrations-evidence.json",
        "sha256": "67ec38dbe883ef40b3cde82f0c1bab3c4986d9bf858d7d57d27c9c7ea7aa6656",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Use Symblic from another agent",
      "headings": [
        "Use Symblic from another agent",
        "Copyable parent-to-child handoff"
      ],
      "sha256": "ccb24ef8e44ece234ce2e479a8d015c312229169d441e16186b4034aaa151e35",
      "url": "/docs/reference/AGENT-CARD.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/AGENT-CARD.md",
        "sha256": "ccb24ef8e44ece234ce2e479a8d015c312229169d441e16186b4034aaa151e35",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Reusable delegation contracts",
      "headings": [
        "Reusable delegation contracts",
        "Contract interface",
        "Preparing and accounting for a route",
        "Typed transformation",
        "Micro choices and exact source witnesses",
        "Checked proof construction",
        "Exact arithmetic convenience",
        "Machine output and handoff",
        "Target-first numbered proof cards"
      ],
      "sha256": "98ae0cca2447a74c2caf215dabf7af7581ed8ddfc61528fc94d0780a6ec2147c",
      "url": "/docs/reference/AGENT-DELEGATION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/AGENT-DELEGATION.md",
        "sha256": "98ae0cca2447a74c2caf215dabf7af7581ed8ddfc61528fc94d0780a6ec2147c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Write Symblic with the installed parser contract",
      "headings": [
        "Write Symblic with the installed parser contract",
        "Select the correct parser",
        "Three text syntaxes, three boundaries",
        "Optional finite command-menu schema",
        "Read the machine result and bounds"
      ],
      "sha256": "6c48868cab2356f03103378e97dfe3f9e39c25995971853d1ecebc5d8ed86bff",
      "url": "/docs/reference/AUTHORING-GRAMMAR.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/AUTHORING-GRAMMAR.md",
        "sha256": "6c48868cab2356f03103378e97dfe3f9e39c25995971853d1ecebc5d8ed86bff",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "ChatGPT and Gemini as typed browser providers",
      "headings": [
        "ChatGPT and Gemini as typed browser providers",
        "Readiness and identity",
        "Exact request and fresh context",
        "Reconnect, cancellation and accounting",
        "Verification scope"
      ],
      "sha256": "b541c22fffac923f796914cd679cb3101f21c695c03b5d13ec33e6df075223d8",
      "url": "/docs/reference/BROWSER-PROVIDERS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/BROWSER-PROVIDERS.md",
        "sha256": "b541c22fffac923f796914cd679cb3101f21c695c03b5d13ec33e6df075223d8",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Optional compact capsule annotations",
      "headings": [
        "Optional compact capsule annotations",
        "Retained information and identity",
        "Budgets and recovery",
        "Evidence and measurement scope"
      ],
      "sha256": "e30fd3cafda53bf1d8bf73f6d38d69285665cfad4dfe0b1ecb68d178f38fe1a7",
      "url": "/docs/reference/COMPACT-CAPSULES.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/COMPACT-CAPSULES.md",
        "sha256": "e30fd3cafda53bf1d8bf73f6d38d69285665cfad4dfe0b1ecb68d178f38fe1a7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Optional constructor from the native CLI",
      "headings": [
        "Optional constructor from the native CLI",
        "Parent-to-child native handoff",
        "Recovery inspection after lost context"
      ],
      "sha256": "3fb6b75a38dc013f43d3d0c54f3d003e3d2f6040f2421b5f9a254dfa21f66ac2",
      "url": "/docs/reference/CONSTRUCTOR-CLI.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/CONSTRUCTOR-CLI.md",
        "sha256": "3fb6b75a38dc013f43d3d0c54f3d003e3d2f6040f2421b5f9a254dfa21f66ac2",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Constructor records and portable locks",
      "headings": [
        "Constructor records and portable locks",
        "Shared configuration API"
      ],
      "sha256": "75a3e377a655f386a33cad8ab6bb6a59977d9503361dd0aa366fabd0e5c09990",
      "url": "/docs/reference/CONSTRUCTOR-LOCKS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/CONSTRUCTOR-LOCKS.md",
        "sha256": "75a3e377a655f386a33cad8ab6bb6a59977d9503361dd0aa366fabd0e5c09990",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Provision the optional linear constructor",
      "headings": [
        "Provision the optional linear constructor",
        "Separate, deliberate installation",
        "Review, inventory, then publish"
      ],
      "sha256": "397d1a0f425504b616f9d677f656aad8822525746b355c13d1b2e79d6c7281fb",
      "url": "/docs/reference/CONSTRUCTOR-PROVISIONING.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/CONSTRUCTOR-PROVISIONING.md",
        "sha256": "397d1a0f425504b616f9d677f656aad8822525746b355c13d1b2e79d6c7281fb",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Optional checked constructors",
      "headings": [
        "Optional checked constructors"
      ],
      "sha256": "09f206729e898bc3b65c00b5818d856f8012cc39a4c2dce8d4c3e179add6b3e1",
      "url": "/docs/reference/CONSTRUCTORS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/CONSTRUCTORS.md",
        "sha256": "09f206729e898bc3b65c00b5818d856f8012cc39a4c2dce8d4c3e179add6b3e1",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Source-linked context experiments",
      "headings": [
        "Source-linked context experiments",
        "Extractive compression",
        "Scoped hash sidecar"
      ],
      "sha256": "5a808bbf29f5972b7aa9cdef9996f068aab0e6dc71e97e70305505f5b5b47522",
      "url": "/docs/reference/CONTEXT-EXPERIMENTS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/CONTEXT-EXPERIMENTS.md",
        "sha256": "5a808bbf29f5972b7aa9cdef9996f068aab0e6dc71e97e70305505f5b5b47522",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Differential questions for code specifications",
      "headings": [
        "Differential questions for code specifications",
        "Three distinct comparisons",
        "API and executable example",
        "Recorded evidence",
        "Bounds and execution"
      ],
      "sha256": "02a6cf320285651018ba01085b6736962b3e7d346b0021589436712ad845bdca",
      "url": "/docs/reference/DIFFERENTIAL-SPECS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/DIFFERENTIAL-SPECS.md",
        "sha256": "02a6cf320285651018ba01085b6736962b3e7d346b0021589436712ad845bdca",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic distillation (SFT/LoRA), version 1",
      "headings": [
        "Symblic distillation (SFT/LoRA), version 1",
        "1. Environment (root provisions; verified 2026-10-06)",
        "2. Input: accepted Symblic ask records (exact schema, version 1)",
        "3. Commands (CLI: `tools/symblic-distill`; every `--out` must not exist; JSON on stdout; refusals exit 2)",
        "4. Splits, leakage and exposure",
        "5. Worker, state and recovery",
        "6. Comparison (pure, `compare`)",
        "6a. Native checker registration (root; trusted code only)",
        "7. Verifiable reward / GRPO: unsupported",
        "8. Integration status and remaining work",
        "9. Repeatable admitted CPU run recipe (example paths)",
        "10. Local accepted-run exporter and actual pilot",
        "11. Fixed native scalar checker and durable trusted contracts"
      ],
      "sha256": "d9b5e18b750bf776a39c95571492200f7d9f6462c1700e18c81b256b9d9561d1",
      "url": "/docs/reference/DISTILLATION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/DISTILLATION.md",
        "sha256": "d9b5e18b750bf776a39c95571492200f7d9f6462c1700e18c81b256b9d9561d1",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Documentation conformance inventory",
      "headings": [
        "Documentation conformance inventory"
      ],
      "sha256": "b195c7a2dc70b40df089ce73577a8250a241ccac4bf0184e6376307ed8ae2223",
      "url": "/docs/reference/DOCUMENTATION-CONFORMANCE.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/DOCUMENTATION-CONFORMANCE.md",
        "sha256": "b195c7a2dc70b40df089ce73577a8250a241ccac4bf0184e6376307ed8ae2223",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Underlines and your instruction circuit",
      "headings": [
        "Underlines and your instruction circuit",
        "Find and fix a problem",
        "Read the English circuit",
        "What checking establishes",
        "Accept lines and retry feedback",
        "Design references"
      ],
      "sha256": "815943c782b72e740304784501e6e99cee384180397c02f4232b96bcface68e5",
      "url": "/docs/reference/EDITOR.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/EDITOR.md",
        "sha256": "815943c782b72e740304784501e6e99cee384180397c02f4232b96bcface68e5",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "English statements (`symblic.english.compiler`, version `symblic-english/1`)",
      "headings": [
        "English statements (`symblic.english.compiler`, version `symblic-english/1`)",
        "Use it",
        "Statements",
        "The direct-step contract",
        "Determinism",
        "API",
        "How the metaphor maps to the runtime",
        "Examples",
        "Construct an animation from English"
      ],
      "sha256": "f854783fd11d823b90ba6971f0f01c3c1a6e6184be85a9d864af65d3191b5f8c",
      "url": "/docs/reference/ENGLISH-STATEMENTS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/ENGLISH-STATEMENTS.md",
        "sha256": "f854783fd11d823b90ba6971f0f01c3c1a6e6184be85a9d864af65d3191b5f8c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Durable epistemic notebooks",
      "headings": [
        "Durable epistemic notebooks",
        "What the notebook preserves",
        "Pure host interface",
        "Fresh context and materialized values",
        "Persistence, limits and verification"
      ],
      "sha256": "0953b101da90dd37fe7c91abfe92f3ec46890b998b5f960c7166518bed478bff",
      "url": "/docs/reference/EPISTEMIC-MEMORY.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/EPISTEMIC-MEMORY.md",
        "sha256": "0953b101da90dd37fe7c91abfe92f3ec46890b998b5f960c7166518bed478bff",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "A source-bound expense handoff between agents",
      "headings": [
        "A source-bound expense handoff between agents",
        "Files and responsibilities",
        "Prepare, hand off, run, check",
        "Checks and limits",
        "Verification and present status"
      ],
      "sha256": "b81803cb6618d7b8cdfe60e719d9590720d5d38316c451b6aad09236ef3d2f6f",
      "url": "/docs/reference/EXPENSE-HANDOFF.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/EXPENSE-HANDOFF.md",
        "sha256": "b81803cb6618d7b8cdfe60e719d9590720d5d38316c451b6aad09236ef3d2f6f",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Executable research mechanisms",
      "headings": [
        "Executable research mechanisms",
        "Interfaces and reproducibility",
        "Mechanism catalog",
        "Numerical interpretation",
        "Meaning and evidence"
      ],
      "sha256": "10006ab2e4ea8d0069bda4bc0f6c259c59362c833661ee5387a0034114f33cc0",
      "url": "/docs/reference/EXPERIMENTS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/EXPERIMENTS.md",
        "sha256": "10006ab2e4ea8d0069bda4bc0f6c259c59362c833661ee5387a0034114f33cc0",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Finite sheaf and schema transport experiments",
      "headings": [
        "Finite sheaf and schema transport experiments",
        "Local-to-global consistency",
        "Finite maps and predicates",
        "Bounds and verification"
      ],
      "sha256": "bdf32954b0237f63977efcb943b4d68b1c0221d88092bb59cf76fb27612025c7",
      "url": "/docs/reference/FINITE-TRANSPORT-EXPERIMENTS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/FINITE-TRANSPORT-EXPERIMENTS.md",
        "sha256": "bdf32954b0237f63977efcb943b4d68b1c0221d88092bb59cf76fb27612025c7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic Forge requirement and acceptance map",
      "headings": [
        "Symblic Forge requirement and acceptance map",
        "Source and check notation",
        "Complete 154-unit map",
        "Verification record",
        "Explicit limitations and review obligations",
        "2026-10-07 follow-up: configurable agents and focused authoring"
      ],
      "sha256": "6675b7ce31f98842ed10e9167ac08a49c698445d0ec1a1647d39d867c201c62c",
      "url": "/docs/reference/FORGE-ACCEPTANCE.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/FORGE-ACCEPTANCE.md",
        "sha256": "6675b7ce31f98842ed10e9167ac08a49c698445d0ec1a1647d39d867c201c62c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic Forge",
      "headings": [
        "Symblic Forge",
        "Start with an idea",
        "Authority, provenance and history",
        "Modes and controls",
        "Engineering workspace",
        "Models and controlled context",
        "Idea workshop and spec writing coach",
        "Exports, validation and handoff",
        "Persistence and API",
        "Verification and source map"
      ],
      "sha256": "ad6e13f9665d0ef07a1254e40834f683be00918ba0614574bd1192d38fdeca74",
      "url": "/docs/reference/FORGE.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/FORGE.md",
        "sha256": "ad6e13f9665d0ef07a1254e40834f683be00918ba0614574bd1192d38fdeca74",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Reusable graph fragments",
      "headings": [
        "Reusable graph fragments",
        "Agent entry",
        "Document and ports",
        "Operator API and interface",
        "Bounds and evidence"
      ],
      "sha256": "970e6c04f7688d78497cb45bbd8140d65d1a7f4f3efa9045c95e7bc57e4bed1c",
      "url": "/docs/reference/GRAPH-COMPOSITION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        },
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/GRAPH-COMPOSITION.md",
        "sha256": "970e6c04f7688d78497cb45bbd8140d65d1a7f4f3efa9045c95e7bc57e4bed1c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Incremental proof sessions: one inference per fresh context",
      "headings": [
        "Incremental proof sessions: one inference per fresh context",
        "Trust boundary",
        "Native builtins",
        "State",
        "Frontier (the task card)",
        "Append result",
        "Finite codes",
        "Prefix checker",
        "Limits and cost",
        "Native compiler integration",
        "Tests"
      ],
      "sha256": "857224e621f703e7ef907762493390b2f2e83e08910e755a92944c3b12a1031c",
      "url": "/docs/reference/INCREMENTAL-PROOFS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/INCREMENTAL-PROOFS.md",
        "sha256": "857224e621f703e7ef907762493390b2f2e83e08910e755a92944c3b12a1031c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Choosing the next evidence method",
      "headings": [
        "Choosing the next evidence method",
        "Use the planner",
        "Wire contract",
        "Selection and uncertainty",
        "Minimal example",
        "Bounds and checks"
      ],
      "sha256": "fc2d720def3ce7ab316fe5cf61f9f6c33a736916355bb6c587b89745d8a2f7bf",
      "url": "/docs/reference/INQUIRY.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/INQUIRY.md",
        "sha256": "fc2d720def3ce7ab316fe5cf61f9f6c33a736916355bb6c587b89745d8a2f7bf",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Optional JavaScript declaration contracts",
      "headings": [
        "Optional JavaScript declaration contracts",
        "The optional loading policy",
        "Isolation, bounds and identities",
        "Host integration"
      ],
      "sha256": "eb0670975e775e32ddd7f00190f5ee5eb2ea15e78d797bee9fdbfce7eedc7d6b",
      "url": "/docs/reference/JS-CONTRACTS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/JS-CONTRACTS.md",
        "sha256": "eb0670975e775e32ddd7f00190f5ee5eb2ea15e78d797bee9fdbfce7eedc7d6b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Local model routing for delegated templates",
      "headings": [
        "Local model routing for delegated templates",
        "Choice and authority",
        "Shared repair policy",
        "Identity and durable verification",
        "Receipts and limits",
        "Focused verification"
      ],
      "sha256": "06c9e18c9a2604762858a0a02bd82ca1d4dec30d576316221d79ac67ecc6770b",
      "url": "/docs/reference/LOCAL-ROUTING.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/LOCAL-ROUTING.md",
        "sha256": "06c9e18c9a2604762858a0a02bd82ca1d4dec30d576316221d79ac67ecc6770b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Portable verified programs, format 2",
      "headings": [
        "Portable verified programs, format 2",
        "Build, check and run",
        "Measured portability",
        "Integrity and bounds"
      ],
      "sha256": "a13e6f72939f3826268b438d57dc1bcf759a01807bbb2ef4419169be2473da41",
      "url": "/docs/reference/PORTABLE-FINITE.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PORTABLE-FINITE.md",
        "sha256": "a13e6f72939f3826268b438d57dc1bcf759a01807bbb2ef4419169be2473da41",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "One command per proof inference",
      "headings": [
        "One command per proof inference",
        "Enable it explicitly",
        "Syntax and references",
        "Fresh context and unchanged acceptance",
        "Bounds and identity"
      ],
      "sha256": "a1c0e6d2bcee78f5697bb08e46bcdbb20de5cae934c6d4958fda99efce307c74",
      "url": "/docs/reference/PROOF-COMMANDS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROOF-COMMANDS.md",
        "sha256": "a1c0e6d2bcee78f5697bb08e46bcdbb20de5cae934c6d4958fda99efce307c74",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "A focused context for one caller-owned proof obligation",
      "headings": [
        "A focused context for one caller-owned proof obligation",
        "Caller contract and visible state",
        "Full checks and parent adoption",
        "Bounds and evidence"
      ],
      "sha256": "e5fa1eb24952cad03d892d0140c0ae4a2afcc50ae4eb065e0783abbb27ab1f07",
      "url": "/docs/reference/PROOF-FOCUS-DELEGATION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROOF-FOCUS-DELEGATION.md",
        "sha256": "e5fa1eb24952cad03d892d0140c0ae4a2afcc50ae4eb065e0783abbb27ab1f07",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Exact intermediate obligations for fresh proof children",
      "headings": [
        "Exact intermediate obligations for fresh proof children",
        "Formula and assumption authority",
        "Selected-only native checks",
        "Acceptance and parent adoption"
      ],
      "sha256": "1fd152ca00307724b8275c0fdd585cfc71acdc3ca7ca856a6d0354d8a4c3c31d",
      "url": "/docs/reference/PROOF-OBLIGATION-DELEGATION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROOF-OBLIGATION-DELEGATION.md",
        "sha256": "1fd152ca00307724b8275c0fdd585cfc71acdc3ca7ca856a6d0354d8a4c3c31d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "One checked proof step per delegated child",
      "headings": [
        "One checked proof step per delegated child",
        "Request and authority",
        "Execution and accepted output",
        "Compatibility and evidence boundaries"
      ],
      "sha256": "c2ba3b5010543d517cac15888da3623cd1a9c4844fffdd4892abc05ba16114e8",
      "url": "/docs/reference/PROOF-STEP-DELEGATION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROOF-STEP-DELEGATION.md",
        "sha256": "c2ba3b5010543d517cac15888da3623cd1a9c4844fffdd4892abc05ba16114e8",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "One exact proof obligation as a numbered task card",
      "headings": [
        "One exact proof obligation as a numbered task card",
        "Caller input and visible card",
        "Runtime behavior and limits",
        "Why try this presentation"
      ],
      "sha256": "c6afbe3ea9c201985d7deb3c8b3ec9f9175fadf84396a10aaf6950644631e89f",
      "url": "/docs/reference/PROOF-TASK-CARD.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROOF-TASK-CARD.md",
        "sha256": "c6afbe3ea9c201985d7deb3c8b3ec9f9175fadf84396a10aaf6950644631e89f",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Finite protocol replay and compensation planning",
      "headings": [
        "Finite protocol replay and compensation planning",
        "Exact-revision acknowledgements",
        "One-use ownership across branches",
        "Saga compensation planning",
        "Bounds, validation and integration limits"
      ],
      "sha256": "443b350268c37233fa130713925060e1fbbf968a5507fa213ef0216d2f5104ef",
      "url": "/docs/reference/PROTOCOL-EXPERIMENTS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/PROTOCOL-EXPERIMENTS.md",
        "sha256": "443b350268c37233fa130713925060e1fbbf968a5507fa213ef0216d2f5104ef",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Observed requirement checks",
      "headings": [
        "Observed requirement checks"
      ],
      "sha256": "c01ebae357d7bd2a61d90cf0b8b6f55d51f43209f223c1accce7f705302bbe56",
      "url": "/docs/reference/REQUIREMENT-EXECUTION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/REQUIREMENT-EXECUTION.md",
        "sha256": "c01ebae357d7bd2a61d90cf0b8b6f55d51f43209f223c1accce7f705302bbe56",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Supplied geometry experiments, version 1",
      "headings": [
        "Supplied geometry experiments, version 1",
        "Hamiltonian integrators",
        "Fisher gradient",
        "Arithmetic, bounds and verification"
      ],
      "sha256": "7b516d8ff4ae60ec0a779a50ae1ef6bb527ca27c974957a4df253624f95a4348",
      "url": "/docs/reference/RESEARCH-GEOMETRY.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/RESEARCH-GEOMETRY.md",
        "sha256": "7b516d8ff4ae60ec0a779a50ae1ef6bb527ca27c974957a4df253624f95a4348",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Research transfer: fresh-context construction and the cognitive fabric",
      "headings": [
        "Research transfer: fresh-context construction and the cognitive fabric",
        "Executable research adapters",
        "The work-card execution cycle",
        "What the implementation now connects",
        "Research that informs the mechanism",
        "A numerical construction task from the vorticity energy method",
        "Evidence acquisition and broader mathematics",
        "Token and evaluation discipline"
      ],
      "sha256": "edbe6b6b6c708b161df2a81353f76fb10ea53a4fb70f83706b7f2a024a13225f",
      "url": "/docs/reference/RESEARCH-TRANSFER.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/RESEARCH-TRANSFER.md",
        "sha256": "edbe6b6b6c708b161df2a81353f76fb10ea53a4fb70f83706b7f2a024a13225f",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Solver proposal provenance",
      "headings": [
        "Solver proposal provenance"
      ],
      "sha256": "b5e6b980bd9d5efd07ce60cfb6eb8317f0f8d0e017af0e8ef02e004f71c0833e",
      "url": "/docs/reference/SOLVER-PROVENANCE.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SOLVER-PROVENANCE.md",
        "sha256": "b5e6b980bd9d5efd07ce60cfb6eb8317f0f8d0e017af0e8ef02e004f71c0833e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Start using Symblic",
      "headings": [
        "Start using Symblic",
        "Start with one checkable task",
        "Examples of useful projects",
        "Loops, decisions and waits",
        "What the current evidence establishes"
      ],
      "sha256": "73b4a1e825a1ce2d82a419789370f73d1c05e45e6b191494af3514d2519bf9ae",
      "url": "/docs/reference/START-HERE.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/START-HERE.md",
        "sha256": "73b4a1e825a1ce2d82a419789370f73d1c05e45e6b191494af3514d2519bf9ae",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "What the small-model construction test achieved",
      "headings": [
        "What the small-model construction test achieved",
        "The finished program runs without a model",
        "What was learned before this run",
        "What this demonstrates"
      ],
      "sha256": "0a0ee5118b6bd59bbfcfe45fd5e82686116b427501a8b5b54c9826aa8e621d0e",
      "url": "/docs/reference/STEPS-EVIDENCE.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/STEPS-EVIDENCE.md",
        "sha256": "0a0ee5118b6bd59bbfcfe45fd5e82686116b427501a8b5b54c9826aa8e621d0e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Build one checked step at a time",
      "headings": [
        "Build one checked step at a time",
        "Use the page",
        "When the model repeats a mistake",
        "A program with thirteen connected pieces",
        "Write a precise construction line",
        "Terminal use",
        "Bounds and evidence"
      ],
      "sha256": "ea9fb47e339729797babf5b0421ff2ce1c408030b88744bf506c284cac5709bd",
      "url": "/docs/reference/STEPS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/STEPS.md",
        "sha256": "ea9fb47e339729797babf5b0421ff2ce1c408030b88744bf506c284cac5709bd",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Durable Symblic workflows",
      "headings": [
        "Durable Symblic workflows",
        "Workflow format",
        "Failure and compensation",
        "Real scheduling and event firings",
        "Inputs, policies and resources",
        "CLI and API"
      ],
      "sha256": "a35fc028854f3c609c45d7e8e0518f2e3e2a9444472a739537aa28fdf64607dc",
      "url": "/docs/reference/SUPERVISOR.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SUPERVISOR.md",
        "sha256": "a35fc028854f3c609c45d7e8e0518f2e3e2a9444472a739537aa28fdf64607dc",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: The Complete Master Record & Technical Compendium",
      "headings": [
        "Symblic: The Complete Master Record & Technical Compendium",
        "Table of Contents",
        "1. Executive Summary & Thematic Overview",
        "2. Token Economics: The BPE Mechanics & The Unicode Hieroglyphic Trap",
        "Historical routing figures (original complete fixture not supplied)",
        "Character reduction versus token reduction",
        "3. Symblic Core Architecture: The 0-Token Kernel & Sterile Capsules",
        "Operational scope",
        "4. Reported Benchmark: Trip Expense & Policy Auditor",
        "The Task",
        "Historical illustrative program (not a complete acceptance contract)",
        "Historical reported static analysis (not rerun here)",
        "Historical reported runtime output (not independently reproduced)",
        "Historical reported figures (`o200k_base`; unreplicated)",
        "Turn 1: Extraction & Calculations",
        "Turn 2: Follow-up Pipeline Step (\"Draft Notification Email\")",
        "Cumulative 2-Turn Total",
        "5. The Agent Authoring Tax (Meta-Generation Economics)",
        "6. Is Symblic Pointless? (Deconstructing the Conceptual Critique)",
        "7. Reliability of Model Arithmetic and Formal Construction",
        "8. Cross-Agent Dispatch to Claude and Codex",
        "Historical proposals dispatched (not new agent authority):",
        "9. Bytes on the Kernel vs. Model Weights",
        "10. How Code Affects Bytes Directly on the Kernel",
        "11. Hardware Systems: CPU Logic Engine vs. GPU CUDA Kernels",
        "12. The Multi-Model Token Paradox & The High-Dimensional Black Box",
        "13. Is Symblic a Brute-Force Attack?",
        "14. Enterprise Architecture: Integrating Red Hat Logic",
        "15. Offensive Security: Integrating Black Hat Methodologies",
        "16. Master Comparative Reference Matrix"
      ],
      "sha256": "372c56be1739c63da590c088c0d9332a28c54f400d079b5374ea681f5831a3ae",
      "url": "/docs/reference/SYMBLIC-COMPLETE-MASTER-RECORD.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SYMBLIC-COMPLETE-MASTER-RECORD.md",
        "sha256": "372c56be1739c63da590c088c0d9332a28c54f400d079b5374ea681f5831a3ae",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: Systems, Hardware & Offensive Security Deep Dive",
      "headings": [
        "Symblic: Systems, Hardware & Offensive Security Deep Dive",
        "Table of Contents",
        "1. Bytes on the Kernel vs. Model Weights",
        "2. How Code Affects Bytes Directly on the Kernel",
        "A. Exact Rational Memory Allocation (No Floating-Point Drift)",
        "B. Bitwise Deterministic Output Serialization",
        "C. SHA-256 Cryptographic Lockfiles",
        "3. Hardware Systems: CPU Logic Engine vs. GPU CUDA Kernels",
        "4. The Multi-Model Token Paradox & The High-Dimensional Black Box",
        "5. Is Symblic a Brute-Force Attack?",
        "6. Enterprise Logic: Lessons from Red Hat",
        "7. Offensive Security: Integrating Black Hat Methodologies into Symblic"
      ],
      "sha256": "1c0c3fa276cfa69b24a955e7d54773bda029ec06da7a00a6de06d8bfec9139c5",
      "url": "/docs/reference/SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md",
        "sha256": "1c0c3fa276cfa69b24a955e7d54773bda029ec06da7a00a6de06d8bfec9139c5",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: Token Economics, Neuro-Symbolic Architecture & Agent Ergonomics",
      "headings": [
        "Symblic: Token Economics, Neuro-Symbolic Architecture & Agent Ergonomics",
        "Table of Contents",
        "1. Executive Summary",
        "2. Token Economics: The Unicode Trap & ASCII Efficiency",
        "Historical routing figures (original complete fixture not supplied)",
        "Character reduction versus token reduction",
        "3. Symblic Core Architecture: The 0-Token Kernel & Sterile Capsules",
        "Operational scope",
        "4. Reported Benchmark: Trip Expense & Policy Auditor",
        "The Task",
        "Historical illustrative program (not a complete acceptance contract)",
        "Historical reported figures (`o200k_base`; unreplicated)",
        "Turn 1: Extraction & Audit Calculations",
        "Turn 2: Follow-up Action (\"Draft Manager Notification Email\")",
        "Cumulative 2-Turn Total",
        "5. The Agent Authoring Tax (Meta-Generation Economics)",
        "6. Is Symblic Pointless? (Deconstructing the Conceptual Critique)",
        "7. Reliability of Model Arithmetic and Formal Construction",
        "8. Bytes on the Kernel vs. Model Weights",
        "Comparison Table",
        "How Code Directly Affects Bytes",
        "9. Systems Architecture: CPU Logic Engine vs. GPU CUDA Kernels",
        "10. Multi-Model Unification: Token Sequences vs. Semantic Contracts",
        "11. Cross-Agent Dispatch & Actionable Directives for Claude and Codex",
        "Historical proposals dispatched (not new agent authority):"
      ],
      "sha256": "8155754f525bf1ad0d9b5cac767f6f4d27cabc795feec8507edd128df3116f47",
      "url": "/docs/reference/SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md",
        "sha256": "8155754f525bf1ad0d9b5cac767f6f4d27cabc795feec8507edd128df3116f47",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Task cards and portable builds",
      "headings": [
        "Task cards and portable builds",
        "Optional exact declaration contracts",
        "Reuse and exact artifacts",
        "Construction networks"
      ],
      "sha256": "475ab5640be0cd48fda514e3e27b68dabc4ff42b5dbd5d9147136f735015ce0a",
      "url": "/docs/reference/TASK-CARDS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/TASK-CARDS.md",
        "sha256": "475ab5640be0cd48fda514e3e27b68dabc4ff42b5dbd5d9147136f735015ce0a",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic Terminal",
      "headings": [
        "Symblic Terminal",
        "Give an agent a direct instruction",
        "Fresh contexts and teams",
        "Reconnect and saved work",
        "Native tools, kept intact",
        "English page integration",
        "Cheat sheet and local context tools",
        "UI implementation and checks",
        "Offline component acceptance and release records"
      ],
      "sha256": "5cea9443dfc0fe5dd45181377cc49990e9c012f72be4556991ca4a76e155ef75",
      "url": "/docs/reference/TERMINAL.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/TERMINAL.md",
        "sha256": "5cea9443dfc0fe5dd45181377cc49990e9c012f72be4556991ca4a76e155ef75",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Constructing a finite energy witness",
      "headings": [
        "Constructing a finite energy witness"
      ],
      "sha256": "180e17043c094cd82b8d34ac5b4b814ad5a5f50a8df3f598d39c1494401c584d",
      "url": "/docs/reference/VORTICITY-CONSTRUCTION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [
        {
          "level": 12,
          "bite": 0,
          "title": "From a weak form to a finite energy problem"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/VORTICITY-CONSTRUCTION.md",
        "sha256": "180e17043c094cd82b8d34ac5b4b814ad5a5f50a8df3f598d39c1494401c584d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Typed workcards and reviewer roles",
      "headings": [
        "Typed workcards and reviewer roles",
        "Build one checked step at a time",
        "Builder, critic and reviewer",
        "A planner fills one visible hole at a time",
        "Records and limits",
        "Page and pure authoring API"
      ],
      "sha256": "ee1d30959e63fd3f49fecb67af918c1aa2a341833cf70a3e19cd949d53271abc",
      "url": "/docs/reference/WORKCARDS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/WORKCARDS.md",
        "sha256": "ee1d30959e63fd3f49fecb67af918c1aa2a341833cf70a3e19cd949d53271abc",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "documentation cases",
      "headings": [],
      "sha256": "755cbbbffed3fa37aac87186d1d9b881a75dbfdde1c4aa992a686c6d185d92c2",
      "url": "/docs/reference/documentation-cases.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/documentation-cases.json",
        "sha256": "755cbbbffed3fa37aac87186d1d9b881a75dbfdde1c4aa992a686c6d185d92c2",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 bounded construction",
      "headings": [],
      "sha256": "ee170526036d8deb80b620cc36d734fe17b87d56b6946b7f07a4462b1b58b569",
      "url": "/docs/reference/evidence/2026-10-05-bounded-construction.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-bounded-construction.json",
        "sha256": "ee170526036d8deb80b620cc36d734fe17b87d56b6946b7f07a4462b1b58b569",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 command menu pilot",
      "headings": [],
      "sha256": "56a44e3d2c81394130ce6d9ddf9d5529d1a23a023bc754f53620b7245f0a1e51",
      "url": "/docs/reference/evidence/2026-10-05-command-menu-pilot.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-command-menu-pilot.json",
        "sha256": "56a44e3d2c81394130ce6d9ddf9d5529d1a23a023bc754f53620b7245f0a1e51",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 constructor recovery controls",
      "headings": [],
      "sha256": "bc6e43d41747062f203c31d1c6ee5f3bbb0415b6c44e39eec58d65d57f5fd228",
      "url": "/docs/reference/evidence/2026-10-05-constructor-recovery-controls.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-constructor-recovery-controls.json",
        "sha256": "bc6e43d41747062f203c31d1c6ee5f3bbb0415b6c44e39eec58d65d57f5fd228",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 constructors",
      "headings": [],
      "sha256": "d56ad0055277af7dc16de52ed06079e41da40c875a786a3191040f4c5e574beb",
      "url": "/docs/reference/evidence/2026-10-05-constructors.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-constructors.json",
        "sha256": "d56ad0055277af7dc16de52ed06079e41da40c875a786a3191040f4c5e574beb",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 focused handoffs",
      "headings": [],
      "sha256": "7c0ce6f939dab08dd08fc1409c1679f166fb8ca73963f938658d4ccf27963d8c",
      "url": "/docs/reference/evidence/2026-10-05-focused-handoffs.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-focused-handoffs.json",
        "sha256": "7c0ce6f939dab08dd08fc1409c1679f166fb8ca73963f938658d4ccf27963d8c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 graph composition",
      "headings": [],
      "sha256": "315ae9ade2208b97133963f20ac40628f09af35d761376a5620fa1c974f043c8",
      "url": "/docs/reference/evidence/2026-10-05-graph-composition.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        },
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-graph-composition.json",
        "sha256": "315ae9ade2208b97133963f20ac40628f09af35d761376a5620fa1c974f043c8",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 micro v2 aggregate",
      "headings": [],
      "sha256": "f3516dc0b7198160c422c7a3ec5313af19c96ae6d9652225cc13e07d8904acf4",
      "url": "/docs/reference/evidence/2026-10-05-micro-v2-aggregate.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-micro-v2-aggregate.json",
        "sha256": "f3516dc0b7198160c422c7a3ec5313af19c96ae6d9652225cc13e07d8904acf4",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 model first delegation",
      "headings": [],
      "sha256": "091d0495cb7167ef6ddb298e78d6404468784f9cdb8e364d0fe4b7fdecf3f050",
      "url": "/docs/reference/evidence/2026-10-05-model-first-delegation.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-model-first-delegation.json",
        "sha256": "091d0495cb7167ef6ddb298e78d6404468784f9cdb8e364d0fe4b7fdecf3f050",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 obligation pilot",
      "headings": [],
      "sha256": "0c5efe65308410f96ac3b21e82129c83e1922dfec2dde78aa98bae8b22147644",
      "url": "/docs/reference/evidence/2026-10-05-obligation-pilot.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-obligation-pilot.json",
        "sha256": "0c5efe65308410f96ac3b21e82129c83e1922dfec2dde78aa98bae8b22147644",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 parser repair",
      "headings": [],
      "sha256": "0b25eb7042a87c2d72894d85930821b32e6f50ee3ffd3895fad8eb76be29e0ce",
      "url": "/docs/reference/evidence/2026-10-05-parser-repair.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-parser-repair.json",
        "sha256": "0b25eb7042a87c2d72894d85930821b32e6f50ee3ffd3895fad8eb76be29e0ce",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 proof card pilot",
      "headings": [],
      "sha256": "3618a16f6fff2efde265f89680199981ef40e29094d3fd56fd29073acb8e3e3e",
      "url": "/docs/reference/evidence/2026-10-05-proof-card-pilot.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-proof-card-pilot.json",
        "sha256": "3618a16f6fff2efde265f89680199981ef40e29094d3fd56fd29073acb8e3e3e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 proof command diagnostic",
      "headings": [],
      "sha256": "e9ecb9a481206251a7269ab9ca42a08d3259afd189b1d78449b55f9d1854afd1",
      "url": "/docs/reference/evidence/2026-10-05-proof-command-diagnostic.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-proof-command-diagnostic.json",
        "sha256": "e9ecb9a481206251a7269ab9ca42a08d3259afd189b1d78449b55f9d1854afd1",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 proof obligations",
      "headings": [],
      "sha256": "f8e465ad48f17ab53d13bb8d6c6a511b17b595d1e479d3201cfd10f8ec04b3d0",
      "url": "/docs/reference/evidence/2026-10-05-proof-obligations.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-proof-obligations.json",
        "sha256": "f8e465ad48f17ab53d13bb8d6c6a511b17b595d1e479d3201cfd10f8ec04b3d0",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 proof task card",
      "headings": [],
      "sha256": "702c3c783f20d652aae0d5d18a46351aec8a99a245dc4e6b2b42f2fc10f09d4e",
      "url": "/docs/reference/evidence/2026-10-05-proof-task-card.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-proof-task-card.json",
        "sha256": "702c3c783f20d652aae0d5d18a46351aec8a99a245dc4e6b2b42f2fc10f09d4e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 reform install",
      "headings": [],
      "sha256": "174492c4c98a218c74fd1993e35991244a240c7236e2b328a882a55b04954850",
      "url": "/docs/reference/evidence/2026-10-05-reform-install.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-reform-install.json",
        "sha256": "174492c4c98a218c74fd1993e35991244a240c7236e2b328a882a55b04954850",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 05 vorticity construction",
      "headings": [],
      "sha256": "d3ff5e3f979f60cf96826f514cfc862a62b9d0ba431503dbca78ffa4599bc446",
      "url": "/docs/reference/evidence/2026-10-05-vorticity-construction.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-05-vorticity-construction.json",
        "sha256": "d3ff5e3f979f60cf96826f514cfc862a62b9d0ba431503dbca78ffa4599bc446",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 06 continuation",
      "headings": [],
      "sha256": "44af94a6b106d6472572c62aac245cb73756dde7e1daece5f6fe3e3fa157faa6",
      "url": "/docs/reference/evidence/2026-10-06-continuation.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-06-continuation.json",
        "sha256": "44af94a6b106d6472572c62aac245cb73756dde7e1daece5f6fe3e3fa157faa6",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 06 english dot",
      "headings": [],
      "sha256": "aa929d71946a1dc4385ef358381ff1d7d2dc7c3e24963924c1f888c60f45c39c",
      "url": "/docs/reference/evidence/2026-10-06-english-dot.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-06-english-dot.json",
        "sha256": "aa929d71946a1dc4385ef358381ff1d7d2dc7c3e24963924c1f888c60f45c39c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "2026 10 06 english matrix",
      "headings": [],
      "sha256": "68d080c53a6e3eb7573742ed75943119b3f383b66b7162d0a736901b30ae8a9e",
      "url": "/docs/reference/evidence/2026-10-06-english-matrix.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/2026-10-06-english-matrix.json",
        "sha256": "68d080c53a6e3eb7573742ed75943119b3f383b66b7162d0a736901b30ae8a9e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "handoff.js",
      "headings": [
        "handoff.js",
        "Shared",
        "Unit `double(x)`",
        "Unit `ready()`",
        "Unit `next(x)`",
        "Assemble `handoff.js`"
      ],
      "sha256": "e352bf37d6f31e02d7f26e5c50176751c9e622c8016b062a23bac700717d89df",
      "url": "/examples/agent-handoff.sheet.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/agent-handoff.sheet.md",
        "sha256": "e352bf37d6f31e02d7f26e5c50176751c9e622c8016b062a23bac700717d89df",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "agent handoff.task",
      "headings": [],
      "sha256": "8442afe50ce5e0816a4ecc4492ba0fd0b8c1baa51dcd2e37568888771ca8175b",
      "url": "/examples/agent-handoff.task.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/agent-handoff.task.json",
        "sha256": "8442afe50ce5e0816a4ecc4492ba0fd0b8c1baa51dcd2e37568888771ca8175b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Matrix rain",
      "headings": [],
      "sha256": "a9633dbcbd1da556d3ead4fc7f4bfb5d67a9e98b73864630db75ee5e5118b6fa",
      "url": "/examples/cmatrix.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/cmatrix.sym",
        "sha256": "a9633dbcbd1da556d3ead4fc7f4bfb5d67a9e98b73864630db75ee5e5118b6fa",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "constructor",
      "headings": [],
      "sha256": "c1802fe6d2197c02b5c962b6a0b2c5d66a95c191871bb422324158ded07bb4f7",
      "url": "/examples/constructor.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/constructor.sym",
        "sha256": "c1802fe6d2197c02b5c962b6a0b2c5d66a95c191871bb422324158ded07bb4f7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "categorize.compiled",
      "headings": [],
      "sha256": "f2e400bb9cc5c3881ce6bfdf53f3aaec57c18a86ac09f298cd400db49b7971af",
      "url": "/examples/english/categorize.compiled.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/english/categorize.compiled.sym",
        "sha256": "f2e400bb9cc5c3881ce6bfdf53f3aaec57c18a86ac09f298cd400db49b7971af",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "falling number.compiled",
      "headings": [],
      "sha256": "c78df223aed00bb836aa4f5c1ed7d0a8fe5a91e6bc07ab345530fba82602cc12",
      "url": "/examples/english/falling-number.compiled.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/english/falling-number.compiled.sym",
        "sha256": "c78df223aed00bb836aa4f5c1ed7d0a8fe5a91e6bc07ab345530fba82602cc12",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "expense handoff",
      "headings": [],
      "sha256": "e42b468ea6203e8ac32d4944ae8fad445ad379b0ec9e036cf24989dada08b2db",
      "url": "/examples/expense-handoff.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/expense-handoff.json",
        "sha256": "e42b468ea6203e8ac32d4944ae8fad445ad379b0ec9e036cf24989dada08b2db",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "SourceBoundExpenses",
      "headings": [],
      "sha256": "6bb1b9f80f81cb47452f0f2a10d375072e0f3966f3232259437283202ce61e1e",
      "url": "/examples/expense-handoff.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/expense-handoff.sym",
        "sha256": "6bb1b9f80f81cb47452f0f2a10d375072e0f3966f3232259437283202ce61e1e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "incremental command.task",
      "headings": [],
      "sha256": "a9532747e3374ffe1f7079cbafd572abaedffab0c257a1023f2cf820f6f187a9",
      "url": "/examples/incremental-command.task.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/incremental-command.task.json",
        "sha256": "a9532747e3374ffe1f7079cbafd572abaedffab0c257a1023f2cf820f6f187a9",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "proof step card.task",
      "headings": [],
      "sha256": "f3aa336be473e88fc8f489fabfe62ae780adbf76ddcf8c8c6d3ec98ff0593edd",
      "url": "/examples/proof-step-card.task.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/proof-step-card.task.json",
        "sha256": "f3aa336be473e88fc8f489fabfe62ae780adbf76ddcf8c8c6d3ec98ff0593edd",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "proof step focus.task",
      "headings": [],
      "sha256": "3d9d2e28fa80e85b64e31c1467f5ea24c5e7a9fce64165a79c748dd23934cf1a",
      "url": "/examples/proof-step-focus.task.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/proof-step-focus.task.json",
        "sha256": "3d9d2e28fa80e85b64e31c1467f5ea24c5e7a9fce64165a79c748dd23934cf1a",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "proof step obligation.task",
      "headings": [],
      "sha256": "973a4fec063c715ce0081927b2e70d443364b7eb4d245d544533b7649334a91b",
      "url": "/examples/proof-step-obligation.task.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/proof-step-obligation.task.json",
        "sha256": "973a4fec063c715ce0081927b2e70d443364b7eb4d245d544533b7649334a91b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "proof step.task",
      "headings": [],
      "sha256": "6b2cd3054823b80cfaec86f18d65a6eaeac5e4dd0ae4ad939706daaf326a1e33",
      "url": "/examples/proof-step.task.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/proof-step.task.json",
        "sha256": "6b2cd3054823b80cfaec86f18d65a6eaeac5e4dd0ae4ad939706daaf326a1e33",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "reusable graph",
      "headings": [],
      "sha256": "e6381dd65689134fca927cca79096d4bcf2aa3cc51b3b12f0e82ce070a8004a3",
      "url": "/examples/reusable-graph.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [
        {
          "level": 13,
          "bite": 0,
          "title": "Agreement, correctness and shared mistakes"
        },
        {
          "level": 14,
          "bite": 0,
          "title": "Small spec units and fresh context"
        }
      ],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/reusable-graph.json",
        "sha256": "e6381dd65689134fca927cca79096d4bcf2aa3cc51b3b12f0e82ce070a8004a3",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "steps parcel built",
      "headings": [],
      "sha256": "03ec55ecdfdf1d8647704b3532a823019f1a53bd97f2cea63caf51a1bd10af63",
      "url": "/examples/steps-parcel-built.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/steps-parcel-built.sym",
        "sha256": "03ec55ecdfdf1d8647704b3532a823019f1a53bd97f2cea63caf51a1bd10af63",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "steps parcel inputs",
      "headings": [],
      "sha256": "c0b0f72220d37cb52374a9ce17f945376e519e70c26574ccf9708ad956147ca8",
      "url": "/examples/steps-parcel-inputs.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/steps-parcel-inputs.json",
        "sha256": "c0b0f72220d37cb52374a9ce17f945376e519e70c26574ccf9708ad956147ca8",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Parcel quotation from thirteen checked bricks — order 7",
      "headings": [],
      "sha256": "b818e8913cc27c06762ca980ab73e9b500ef2a2d5f0fd81da181f8058a725b85",
      "url": "/examples/steps-parcel.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/steps-parcel.json",
        "sha256": "b818e8913cc27c06762ca980ab73e9b500ef2a2d5f0fd81da181f8058a725b85",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Discrete vorticity construction",
      "headings": [],
      "sha256": "e5de948c75bdf38d5b12291f7f20d4fd2fa2971398b490bfbae71ce2646ee2e9",
      "url": "/examples/vorticity-construction.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/vorticity-construction.sym",
        "sha256": "e5de948c75bdf38d5b12291f7f20d4fd2fa2971398b490bfbae71ce2646ee2e9",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "workcard slots",
      "headings": [],
      "sha256": "849f8e41247b8ed0ec8b00c760fd78f058ab402552876c7ffbd5c898f2260f81",
      "url": "/examples/workcard-slots.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/workcard-slots.json",
        "sha256": "849f8e41247b8ed0ec8b00c760fd78f058ab402552876c7ffbd5c898f2260f81",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "workcard team",
      "headings": [],
      "sha256": "254d57f1bbbdcc6023eff7893055a9eeaf8ccad998268d9b29f46e6a0883c75e",
      "url": "/examples/workcard-team.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/workcard-team.json",
        "sha256": "254d57f1bbbdcc6023eff7893055a9eeaf8ccad998268d9b29f46e6a0883c75e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Authoring contract 1",
      "headings": [
        "Authoring contract 1"
      ],
      "sha256": "a6b0fa4785124725c56cf8e9fe5b2a28376847a4986636ec394da44dd2db2c4d",
      "url": "/docs/reference/grammar/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/grammar/README.md",
        "sha256": "a6b0fa4785124725c56cf8e9fe5b2a28376847a4986636ec394da44dd2db2c4d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "conformance",
      "headings": [],
      "sha256": "4cb1b7d583c30e58df00c4879bfdeb0782f2fea966ab78b1e650a2f8601f088a",
      "url": "/symblic/authoring/grammar/conformance.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/symblic/authoring/grammar/conformance.json",
        "sha256": "4cb1b7d583c30e58df00c4879bfdeb0782f2fea966ab78b1e650a2f8601f088a",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Small model cup checked playback",
      "headings": [],
      "sha256": "c4d67644ca3d689718eea3415abc68e1f3c9a9d99eec71feae05895c92aa82c4",
      "url": "/examples/41-small-model-cup.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/41-small-model-cup.sym",
        "sha256": "c4d67644ca3d689718eea3415abc68e1f3c9a9d99eec71feae05895c92aa82c4",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Small model chart checked playback",
      "headings": [],
      "sha256": "ae12c5313003378922f82ce93fc23ffd4c505cf664471afd5a1b7aede110d4db",
      "url": "/examples/42-small-model-chart.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/42-small-model-chart.sym",
        "sha256": "ae12c5313003378922f82ce93fc23ffd4c505cf664471afd5a1b7aede110d4db",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Small model programs checked playback",
      "headings": [],
      "sha256": "2df3e8c30a7817fc33c54cf73597a97cc2f8e003590ef91e65b043e568aacc6e",
      "url": "/examples/43-small-model-programs.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/43-small-model-programs.sym",
        "sha256": "2df3e8c30a7817fc33c54cf73597a97cc2f8e003590ef91e65b043e568aacc6e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Small model exact math checked playback",
      "headings": [],
      "sha256": "4decfe42e33c17afd2cb144dbce64e8bb730a7e8a9697586c387c747af0bf9fd",
      "url": "/examples/44-small-model-math.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/44-small-model-math.sym",
        "sha256": "4decfe42e33c17afd2cb144dbce64e8bb730a7e8a9697586c387c747af0bf9fd",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Small model pricing checked playback",
      "headings": [],
      "sha256": "d27c6af87dfced6bdfa23166d4fffd67c96b2bed05f56140d58d88ad245ffc99",
      "url": "/examples/45-small-model-pricing.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/45-small-model-pricing.sym",
        "sha256": "d27c6af87dfced6bdfa23166d4fffd67c96b2bed05f56140d58d88ad245ffc99",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Small model gantry geometry checked playback",
      "headings": [],
      "sha256": "19b7fb0e336f4e58203e95efbebad60063962314252f44a47cc23bafbc1075ea",
      "url": "/examples/46-small-model-gantry.sym",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/46-small-model-gantry.sym",
        "sha256": "19b7fb0e336f4e58203e95efbebad60063962314252f44a47cc23bafbc1075ea",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "artifacts",
      "headings": [],
      "sha256": "4bf7adf038a2ddcaceaf13663f53cb57e3f7e8f38df0b052b137bca803160d79",
      "url": "/examples/artifacts.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/artifacts.json",
        "sha256": "4bf7adf038a2ddcaceaf13663f53cb57e3f7e8f38df0b052b137bca803160d79",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Checked small-model cup and chart",
      "headings": [
        "Checked small-model cup and chart"
      ],
      "sha256": "534ee17e06e23e608a0809d4494e9b0d805018d229e17b49b317a350ece1e0fc",
      "url": "/examples/small-model-builds-20261007/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-builds-20261007/README.md",
        "sha256": "534ee17e06e23e608a0809d4494e9b0d805018d229e17b49b317a350ece1e0fc",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "alternate mesh",
      "headings": [],
      "sha256": "eff5f68aa3f82983ba8d6fccd6d9a22a7af9bed3978435246f57be94f6c9301e",
      "url": "/examples/small-model-builds-20261007/alternate-mesh.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-builds-20261007/alternate-mesh.json",
        "sha256": "eff5f68aa3f82983ba8d6fccd6d9a22a7af9bed3978435246f57be94f6c9301e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "evidence",
      "headings": [],
      "sha256": "15f7241a85fe3c3dbcedb5a7e57dbe45de0b63c1bd62c1e768fa0ce9668b319f",
      "url": "/examples/small-model-builds-20261007/evidence.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-builds-20261007/evidence.json",
        "sha256": "15f7241a85fe3c3dbcedb5a7e57dbe45de0b63c1bd62c1e768fa0ce9668b319f",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "target mesh",
      "headings": [],
      "sha256": "0d53d9061c9cafedc1ad4cf534889b571da23ebcb04ae82b0ddf8516661c47cc",
      "url": "/examples/small-model-builds-20261007/target-mesh.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-builds-20261007/target-mesh.json",
        "sha256": "0d53d9061c9cafedc1ad4cf534889b571da23ebcb04ae82b0ddf8516661c47cc",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Checked small-model gantry geometry",
      "headings": [
        "Checked small-model gantry geometry"
      ],
      "sha256": "26e512304905af6d84b6b18a510d16a3545233e9fd176c1ffb68b9d4bd5d6215",
      "url": "/examples/small-model-gantry-20261007/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-gantry-20261007/README.md",
        "sha256": "26e512304905af6d84b6b18a510d16a3545233e9fd176c1ffb68b9d4bd5d6215",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "alternate assembly",
      "headings": [],
      "sha256": "9b114c740b085bd3812aa36c75e991601f9b740ae4f78cc3f1924327ce528809",
      "url": "/examples/small-model-gantry-20261007/alternate-assembly.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-gantry-20261007/alternate-assembly.json",
        "sha256": "9b114c740b085bd3812aa36c75e991601f9b740ae4f78cc3f1924327ce528809",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "assemblies",
      "headings": [],
      "sha256": "cd60707ee0ca2b11d2fc6d8708d6bb81c32d2cd8e1383593e8a5a130d53d9d6c",
      "url": "/examples/small-model-gantry-20261007/assemblies.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-gantry-20261007/assemblies.json",
        "sha256": "cd60707ee0ca2b11d2fc6d8708d6bb81c32d2cd8e1383593e8a5a130d53d9d6c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "cases",
      "headings": [],
      "sha256": "6247327064a18a04278a3f7f08565c228f4b2835d2bc01b0de80a2a9bb6f4c10",
      "url": "/examples/small-model-gantry-20261007/cases.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-gantry-20261007/cases.json",
        "sha256": "6247327064a18a04278a3f7f08565c228f4b2835d2bc01b0de80a2a9bb6f4c10",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "evidence",
      "headings": [],
      "sha256": "185f68595ba46808986704e6c02c8193fb847888313888ff45b44649985a2a6e",
      "url": "/examples/small-model-gantry-20261007/evidence.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-gantry-20261007/evidence.json",
        "sha256": "185f68595ba46808986704e6c02c8193fb847888313888ff45b44649985a2a6e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "target assembly",
      "headings": [],
      "sha256": "8308d98830d689dbb53ea7609b178606a8e8b0a4f8beed6c7715b3db73c635a4",
      "url": "/examples/small-model-gantry-20261007/target-assembly.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-gantry-20261007/target-assembly.json",
        "sha256": "8308d98830d689dbb53ea7609b178606a8e8b0a4f8beed6c7715b3db73c635a4",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Checked small-model rational mathematics",
      "headings": [
        "Checked small-model rational mathematics"
      ],
      "sha256": "0801411793b2b09d57a8f1f93fe7a42ac4ecc778c8f400ace77e7d7b5d90d7e0",
      "url": "/examples/small-model-math-20261007/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-math-20261007/README.md",
        "sha256": "0801411793b2b09d57a8f1f93fe7a42ac4ecc778c8f400ace77e7d7b5d90d7e0",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "cases",
      "headings": [],
      "sha256": "7fc27b6ac09494dacb27577f698c71d5b12fc8ffada9838a0288796f20d5cdc9",
      "url": "/examples/small-model-math-20261007/cases.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-math-20261007/cases.json",
        "sha256": "7fc27b6ac09494dacb27577f698c71d5b12fc8ffada9838a0288796f20d5cdc9",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "evidence",
      "headings": [],
      "sha256": "c749cab75fa84f47cdf54dbe8363b2dc96ae9fe3eeb34624567ac720e922d387",
      "url": "/examples/small-model-math-20261007/evidence.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-math-20261007/evidence.json",
        "sha256": "c749cab75fa84f47cdf54dbe8363b2dc96ae9fe3eeb34624567ac720e922d387",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "solutions",
      "headings": [],
      "sha256": "13edafc30e3182996531024a68af7f68b270ff02d2946deaafbdf7d1f7fd6dcb",
      "url": "/examples/small-model-math-20261007/solutions.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-math-20261007/solutions.json",
        "sha256": "13edafc30e3182996531024a68af7f68b270ff02d2946deaafbdf7d1f7fd6dcb",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "exact-linear.js",
      "headings": [
        "exact-linear.js",
        "Shared",
        "Unit `normalizeFraction(n,d)`",
        "Unit `determinant(A)`",
        "Unit `matrixRank(A)`",
        "Unit `solveLinear(A,b)`",
        "Assemble `exact-linear.js`"
      ],
      "sha256": "8468d2e3604c1745dc67bedc89a05a4533e7b3b47ea1f50161e3f20fbcf3ddd0",
      "url": "/examples/small-model-math-20261007/spec-sheet.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-math-20261007/spec-sheet.md",
        "sha256": "8468d2e3604c1745dc67bedc89a05a4533e7b3b47ea1f50161e3f20fbcf3ddd0",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Checked small-model pricing page",
      "headings": [
        "Checked small-model pricing page"
      ],
      "sha256": "ad722329ee4f0212ef44fb6c4c2261bfed68907fae114112f133f3c0e2faa7a4",
      "url": "/examples/small-model-pricing-20261007/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-pricing-20261007/README.md",
        "sha256": "ad722329ee4f0212ef44fb6c4c2261bfed68907fae114112f133f3c0e2faa7a4",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "browser verification",
      "headings": [],
      "sha256": "5e8282b19446e47b546a9de3c2937b59d27707279861e2e4851e11cd8a915af3",
      "url": "/examples/small-model-pricing-20261007/browser-verification.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-pricing-20261007/browser-verification.json",
        "sha256": "5e8282b19446e47b546a9de3c2937b59d27707279861e2e4851e11cd8a915af3",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "evidence",
      "headings": [],
      "sha256": "6c8ae87a3443e2ba86b1c91823e01f925a90ef2afe5b40f2c4b777357367e631",
      "url": "/examples/small-model-pricing-20261007/evidence.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/small-model-pricing-20261007/evidence.json",
        "sha256": "6c8ae87a3443e2ba86b1c91823e01f925a90ef2afe5b40f2c4b777357367e631",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Benchmarks",
      "headings": [
        "Benchmarks",
        "`frontier/`: the frontier ladder (prepared, never run)"
      ],
      "sha256": "1219d1025bf1b8720cb209eb32a42b413d49bf8279cd8da354b40cce4d27a251",
      "url": "/benchmarks/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/benchmarks/README.md",
        "sha256": "1219d1025bf1b8720cb209eb32a42b413d49bf8279cd8da354b40cce4d27a251",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "F1 integer arithmetic.fixture",
      "headings": [],
      "sha256": "d62d62ffb70e387e764a6e7b6694611584f13e671f6b4aa5a9c70df0238df445",
      "url": "/benchmarks/frontier/F1-integer-arithmetic.fixture.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/benchmarks/frontier/F1-integer-arithmetic.fixture.json",
        "sha256": "d62d62ffb70e387e764a6e7b6694611584f13e671f6b4aa5a9c70df0238df445",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "F2 string utilities.fixture",
      "headings": [],
      "sha256": "04220f4238b0c64c3e2a249653a10e05358ec5fa80f935e7f9a133835e7b71df",
      "url": "/benchmarks/frontier/F2-string-utilities.fixture.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/benchmarks/frontier/F2-string-utilities.fixture.json",
        "sha256": "04220f4238b0c64c3e2a249653a10e05358ec5fa80f935e7f9a133835e7b71df",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "F3 collection algebra.fixture",
      "headings": [],
      "sha256": "de31c6fa652fac04a72a3123d5bac70aec5bd04e0ca543192381dd282460fbf5",
      "url": "/benchmarks/frontier/F3-collection-algebra.fixture.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/benchmarks/frontier/F3-collection-algebra.fixture.json",
        "sha256": "de31c6fa652fac04a72a3123d5bac70aec5bd04e0ca543192381dd282460fbf5",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "F4 expression tokenizer.fixture",
      "headings": [],
      "sha256": "340a1742e00f7b4d365d22701574cb7da58a103ca6e06d8b34e955ef61c6883f",
      "url": "/benchmarks/frontier/F4-expression-tokenizer.fixture.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/benchmarks/frontier/F4-expression-tokenizer.fixture.json",
        "sha256": "340a1742e00f7b4d365d22701574cb7da58a103ca6e06d8b34e955ef61c6883f",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "F5 expression evaluator.fixture",
      "headings": [],
      "sha256": "d5e12c15fe61722ecffea32a5960dd4d3b10021718966171e50a584202436b8e",
      "url": "/benchmarks/frontier/F5-expression-evaluator.fixture.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/benchmarks/frontier/F5-expression-evaluator.fixture.json",
        "sha256": "d5e12c15fe61722ecffea32a5960dd4d3b10021718966171e50a584202436b8e",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "F6 vending machine.fixture",
      "headings": [],
      "sha256": "46a4c248aa09a9195b393516c2b63bcd2c0f45fda8336af983f7f62f7d5f0161",
      "url": "/benchmarks/frontier/F6-vending-machine.fixture.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/benchmarks/frontier/F6-vending-machine.fixture.json",
        "sha256": "46a4c248aa09a9195b393516c2b63bcd2c0f45fda8336af983f7f62f7d5f0161",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "ladder",
      "headings": [],
      "sha256": "ed574d4550b5f6b36d6d9aa5cc7c2b89f9881c63341a09e21540b6cee9360a7f",
      "url": "/benchmarks/frontier/ladder.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/benchmarks/frontier/ladder.json",
        "sha256": "ed574d4550b5f6b36d6d9aa5cc7c2b89f9881c63341a09e21540b6cee9360a7f",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Honest assessment: what Symblic has shown, and what it has not",
      "headings": [
        "Honest assessment: what Symblic has shown, and what it has not",
        "The short version",
        "1. The ladder of small local models (2026-10-11)",
        "1.1 A four-unit sheet: which wording each model size needs",
        "1.2 A complete game level: 39 units, 229 examples, 68 required checks",
        "1.3 How much the sheets dictated",
        "1.4 What the 1B and 0.5B results show, and what they do not",
        "1.5 Automatic splitting (autogen) on a 3B model",
        "1.6 Other lanes, one trial each",
        "2. Earlier measurements (2026-10-02 to 2026-10-10)",
        "3. Limits that apply to everything above",
        "4. Questions that remain open"
      ],
      "sha256": "0bf024be4f361c53e2e60cf5bda1edf4f3118f739f168d1d113213f232afe4bb",
      "url": "/docs/HONEST-ASSESSMENT.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/HONEST-ASSESSMENT.md",
        "sha256": "0bf024be4f361c53e2e60cf5bda1edf4f3118f739f168d1d113213f232afe4bb",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Made with AI agents",
      "headings": [
        "Made with AI agents",
        "The short version",
        "Who did what",
        "Older files",
        "How the work was checked",
        "Documents that are AI essays or speculative AI writing",
        "The original request",
        "What was changed for publication"
      ],
      "sha256": "abcda5a6d1b561baf6c397056708ee118fe7708e3b8109ce71f0222377a0a3f7",
      "url": "/docs/MADE-WITH-AI.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/MADE-WITH-AI.md",
        "sha256": "abcda5a6d1b561baf6c397056708ee118fe7708e3b8109ce71f0222377a0a3f7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Map: where every part of Symblic went",
      "headings": [
        "Map: where every part of Symblic went",
        "Folders",
        "Python modules and other top-level code",
        "Command-line tools and scripts",
        "Browser pages",
        "Other files",
        "Tests"
      ],
      "sha256": "f67e026928f8a35a115955a7aac29613b94e7a8193bb69bc4f9dbeaf73aa877b",
      "url": "/docs/MAP.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/MAP.md",
        "sha256": "f67e026928f8a35a115955a7aac29613b94e7a8193bb69bc4f9dbeaf73aa877b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Documentation",
      "headings": [
        "Documentation"
      ],
      "sha256": "4a4dc71fad136c916d37bf81180c3cb59fe2f8d9a86e9e53b69a12cae58a3666",
      "url": "/docs/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/README.md",
        "sha256": "4a4dc71fad136c916d37bf81180c3cb59fe2f8d9a86e9e53b69a12cae58a3666",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Essays: speculative AI writing about Symblic",
      "headings": [
        "Essays: speculative AI writing about Symblic",
        "What was changed for publication"
      ],
      "sha256": "fa7f4145008a198539609471d6e624984b9649bfe65457cd4e4c37e5f89ece40",
      "url": "/docs/essays/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/README.md",
        "sha256": "fa7f4145008a198539609471d6e624984b9649bfe65457cd4e4c37e5f89ece40",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: Architectural Compendium & Master Reference Manual",
      "headings": [
        "Symblic: Architectural Compendium & Master Reference Manual",
        "Table of Contents",
        "1. The Core Architecture & Separation of Concerns",
        "2. Formal Symbolic Logic Foundation & Its Scope",
        "The Formal Logic Pillars & Their Strict Boundaries:",
        "3. Controlled Natural Language & Bounded Contexts",
        "The Controlled Natural Language (CNL) Architecture",
        "The 4-Step Translation Method",
        "The Rosetta Stone",
        "4. File Types, Compilation & Runtime Pipeline",
        "File Types:",
        "Compilation & Execution Pipeline:",
        "5. Complete Language Reference & Syntax",
        "Exact Rational Arithmetic",
        "The Type System",
        "The Model Bridge (`ask`)",
        "Datalog Horn Clauses",
        "Functions vs. Routines",
        "Tutorial Verification Examples",
        "Spider Study (Math + Bounded Fact)",
        "Invoice Extraction",
        "6. Architectural Comparison: Symblic vs. Python & Other Languages",
        "7. Empirical Cluster Receipts: Local Model Capabilities & Limits",
        "1. Multi-Hop Relational Logic (Family Trees, 15-Task Evaluation)",
        "2. Multi-Model Local Councils & Consensus Limits",
        "3. Checked Escalation (`route=escalate`)",
        "8. Backend Architecture: Python Runtime & Native Kernel Tradeoffs",
        "9. Large Contexts & Codebases: Relational Fact Extraction",
        "The Problem:",
        "The Symblic Approach: Codebase-as-a-Datalog-Database",
        "10. Finite Quadratic Minimization & Symblic 2.2 Integration",
        "1. Implemented Capabilities",
        "2. What the Energy Analogy Does NOT Prove",
        "11. High-Performance Computing (HPC) Execution & Distributed Scaling",
        "Path A: HPC Execution Runtime",
        "12. HPC Training & Reinforcement Learning with Verifiable Rewards (RLVR)",
        "What Should (and Should Not) Be Trained",
        "Would Training Make Significant Improvements?",
        "Could Training Cause Symblic to be WORSE? (Critical Failure Modes)",
        "Parameters & Data to Train On",
        "13. (Removed for publication)",
        "14. The Shippable Product Roadmap",
        "15. Strategic Roadmap for Future Verification Extensions",
        "1. Refinement Types (Proposal)",
        "2. Calibrated Uncertainty (Proposal)",
        "3. Linear Temporal Logic for Trajectories (Proposal)",
        "4. Native SMT Solver Integration (Z3)",
        "5. Formal Proof Export (Lean 4)",
        "16. Real-World Use Cases & Assurance Boundaries",
        "17. How to Explain Symblic (Conceptual & Developer Summary)",
        "18. Focused Minimalist Visual Identity",
        "Committed Brand Assets (`docs/reference/`):",
        "19. CLI Command Reference",
        "20. Symblic and Human Intersubjectivity: The Science of Unified Communication and Empathy",
        "20.1 The Epistemic Chasm: Why Humans Misunderstand Each Other",
        "20.2 Is \"True Empathy\" Possible?",
        "20.3 The Four Intersubjective Pillars of Symblic",
        "21. Expanded Minimalist Formal Logic Icon Suite",
        "22. Improving Symblic Core via Intersubjective & Epistemic Research",
        "22.1 Symblic's Current Deficiencies",
        "22.2 The Six Architectural Upgrades",
        "23. Deep Theoretical and Systems Critique of Symblic",
        "23.1 The Seven Foundational Defects",
        "23.2 Architectural Remedies",
        "24. Intense Adversarial Critique: Proof Theory, Taint Laundering, and Irreversible Physics",
        "24.1 Seven Deep Structural Contradictions",
        "24.2 Master Adversarial Risk Matrix",
        "25. Quantum Mathematical Foundations for Neuro-Symbolic Computation (Q-Symblic)",
        "25.1 The Six Quantum Mappings to Symblic",
        "26. Quantum Mechanics and Computational Determinism: Why Quantum Formalism Strengthens Symblic",
        "26.1 The Fallacy: Conflating Physical Hardware Collapse with Unitary Mathematics",
        "26.2 Why Current Symblic is Only Pseudo-Deterministic",
        "26.3 How Quantum Mathematics Eliminates Stochastic Fragility",
        "27. Modern Mathematical Physics: From the 2026 Navier-Stokes Proof to Geometric Neuro-Symbolism",
        "27.1 The Navier-Stokes Lesson: Specification Gaming in Formal Systems",
        "27.2 Upper-Level Physics Foundations Integrated into Symblic",
        "28. The Grand Mathematical Unification: From Navier-Stokes Turing Universality to Holographic String Theory",
        "28.1 The Six Pillars of Grand Unification",
        "29. The Grand Breakthrough: The Universal Epistemic Operating System (UEOS)",
        "29.1 The Five-Layer Unified Architecture",
        "29.2 The Historic Realization: Wave-Particle Duality in Computation"
      ],
      "sha256": "5ec61dd2d7c0228631b1ba9f97f8dc2211fb4caeb94e9cecd83e7d700a9aa860",
      "url": "/docs/essays/symblic_breakthrough_compendium.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_breakthrough_compendium.md",
        "sha256": "5ec61dd2d7c0228631b1ba9f97f8dc2211fb4caeb94e9cecd83e7d700a9aa860",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "The Limits of Neuro-Symbolic Computation: A Deep Theoretical and Engineering Critique of Symblic",
      "headings": [
        "The Limits of Neuro-Symbolic Computation: A Deep Theoretical and Engineering Critique of Symblic",
        "Executive Summary",
        "1. The Decidability Horizon: Gödel, Turing, and Bounded Checking",
        "2. The Capsule Pathology: Semantic Context Starvation",
        "3. Goodhart's Law & The Vacuous Truth Vulnerability",
        "4. The Distributed Determinism Myth: GPU Floating-Point Drift",
        "5. The Quine-Duhem Dilemma: Invariant Ambiguity",
        "6. Paradigm Impedance Mismatch: The Tri-Partite Cognitive Burden",
        "7. Economic Mechanism Design Failures in Auto-Routing",
        "8. Strategic Roadmap: Remedying the Structural Flaws"
      ],
      "sha256": "ee1b78ec7409b143abc399aa5726f6b93fe3d373e46fc9246dfe90fec0aec848",
      "url": "/docs/essays/symblic_critique_and_limitations.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_critique_and_limitations.md",
        "sha256": "ee1b78ec7409b143abc399aa5726f6b93fe3d373e46fc9246dfe90fec0aec848",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Improving Symblic via Intersubjectivity: Epistemic Types, Multi-Frame Verification, and Theory of Mind in Language Design",
      "headings": [
        "Improving Symblic via Intersubjectivity: Epistemic Types, Multi-Frame Verification, and Theory of Mind in Language Design",
        "1. The Core Critique: Symblic's Current Epistemic Naïveté",
        "Where Current Symblic Fails:",
        "2. Six Concrete Upgrades to Symblic Grounded in Research",
        "Upgrade 1: First-Class Epistemic Modality Types",
        "Upgrade 2: Multi-Frame Concordance Contracts (Native Multi-Frame Engine)",
        "Upgrade 3: The Davidsonian Triangulation Pass (Pre-Flight Semantic Calibration)",
        "Upgrade 4: The Principle of Charity & Epistemic Diagnostics (Smart Recovery)",
        "Upgrade 5: Incentive-Compatible Non-Degeneracy Proofs (Mechanism Design)",
        "Upgrade 6: Theory of Mind (ToM) & Aumann Knowledge Graph in Multi-Agent Symblic",
        "3. Implementation Roadmap for Symblic Core"
      ],
      "sha256": "8a1b2ed25cd8c6b7ee90f0b7f7d49fd1dd1d9a6d334989c48b3668576082558b",
      "url": "/docs/essays/symblic_epistemic_improvements.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_epistemic_improvements.md",
        "sha256": "8a1b2ed25cd8c6b7ee90f0b7f7d49fd1dd1d9a6d334989c48b3668576082558b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "The Grand Mathematical Unification of Symblic: From Navier-Stokes Turing Universality to Holographic String Theory",
      "headings": [
        "The Grand Mathematical Unification of Symblic: From Navier-Stokes Turing Universality to Holographic String Theory",
        "Executive Summary",
        "1. Navier-Stokes Turing Universality: Fluid Computing",
        "2. Holographic Neuro-Symbolism: AdS/CFT in Compilers",
        "3. String Worldsheets: Ultraviolet-Finite Execution",
        "4. Mirror Symmetry & T-Duality in Constraints",
        "5. Grothendieck Topos Theory: Perspectival Truth",
        "6. Homotopy Type Theory (HoTT) & Voevodsky Univalence"
      ],
      "sha256": "e89d3bd2c72c4ef511f2c3f080f822aa19a3cd5dcc6098489cc4b2c8baf01fd5",
      "url": "/docs/essays/symblic_grand_unification_and_string_theory.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_grand_unification_and_string_theory.md",
        "sha256": "e89d3bd2c72c4ef511f2c3f080f822aa19a3cd5dcc6098489cc4b2c8baf01fd5",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic on High-Performance Computing (HPC)",
      "headings": [
        "Symblic on High-Performance Computing (HPC)",
        "Executive Summary",
        "Part 1: Developing Symblic on an HPC System",
        "1.1 Path A: HPC Execution & Distributed Scaling",
        "1.2 Path B: HPC Training & Reinforcement Learning with Verifiable Rewards (RLVR)",
        "What Should (and Should Not) Be Trained",
        "Would Training Make Significant Improvements?",
        "1.3 Critical Failure Modes: Can Training Make Symblic Worse?",
        "Training Parameters & Dataset Composition",
        "Part 2: (Removed for publication)",
        "Part 3: The Shippable Product Roadmap"
      ],
      "sha256": "a0d69eda17269a2358d00e4afce24683bdae9f48413ac1cb0dbb061cc511a112",
      "url": "/docs/essays/symblic_hpc_foundations.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_hpc_foundations.md",
        "sha256": "a0d69eda17269a2358d00e4afce24683bdae9f48413ac1cb0dbb061cc511a112",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "The Limits of Neuro-Symbolic Computation: An Exhaustive Theoretical, Semantic, and Security Critique of Symblic",
      "headings": [
        "The Limits of Neuro-Symbolic Computation: An Exhaustive Theoretical, Semantic, and Security Critique of Symblic",
        "Executive Summary",
        "Master Architectural Risk Matrix",
        "1. Category Theory & Proof Theory: The Broken Curry-Howard Isomorphism",
        "2. Computational Linguistics: Montague Semantics Failure",
        "3. Computability Theory: Rice's Theorem & The Verification Trilemma",
        "4. Information Flow Security: Taint Laundering via \"Steered\" Types (`symblic/kernel/effects.py:29-34`)",
        "5. Statistical Optimization: Step Rewards & Shortcut Learning",
        "6. Distributed Systems: The Irreversibility Paradox",
        "7. Cognitive Psychology: The Automation Bias Trap (IOED)"
      ],
      "sha256": "0d2f3ffcb8fba2eff89ffe786f30b96958cdc2c4d936f440a334f45f8487e8d9",
      "url": "/docs/essays/symblic_intense_critique.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_intense_critique.md",
        "sha256": "0d2f3ffcb8fba2eff89ffe786f30b96958cdc2c4d936f440a334f45f8487e8d9",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic and Human Intersubjectivity: Formalizing Empathy, Bridging Perceptual Chasms, and the Architecture of Unified Communication",
      "headings": [
        "Symblic and Human Intersubjectivity: Formalizing Empathy, Bridging Perceptual Chasms, and the Architecture of Unified Communication",
        "Executive Summary",
        "1. The Epistemic Barrier: Why Humans Misunderstand Each Other",
        "1.1 The Phenomenological Chasm (Nagel & Wittgenstein)",
        "1.2 The Triangulation Principle & Radical Interpretation (Davidson)",
        "1.3 Double Contingency: The Black Box Problem (Luhmann)",
        "1.4 Naïve Realism and the Epistemic Fallacy (Ross)",
        "2. The Science of Empathy: Is \"True Empathy\" Possible?",
        "2.1 The Biological Dual-Stream Model (Singer & Bloom)",
        "2.2 Predictive Processing & Coupled Active Inference (Friston & Clark)",
        "2.3 The Levinasian Horizon: Alterity vs. Assimilation",
        "2.4 The Mathematical Boundary of Empathy",
        "3. Sociological & Economic Mechanics of Coordination",
        "3.1 Habermas's Four Validity Claims",
        "3.2 Aumann's Agreement Theorem & The Failure of Common Knowledge",
        "3.3 Crawford-Sobel Cheap Talk vs. Costly Signaling",
        "4. The Epistemic Solution: Multi-Frame Adequacy",
        "5. The Symblic Intersubjective Architecture (SIA)",
        "6. Philosophical & Practical Synthesis"
      ],
      "sha256": "33382774e84920e047158a82ad2a2cf8528431d3abf83de1c11f3416912c9a0b",
      "url": "/docs/essays/symblic_intersubjective_communication.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_intersubjective_communication.md",
        "sha256": "33382774e84920e047158a82ad2a2cf8528431d3abf83de1c11f3416912c9a0b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic Programming Language: The Complete Guide & Tutorial",
      "headings": [
        "Symblic Programming Language: The Complete Guide & Tutorial",
        "Table of Contents",
        "1. The \"Eureka\" Moment: What Symblic Really Is",
        "2. Bridging the Gap to Natural Language",
        "The Problem with Natural Language",
        "The Controlled Natural Language (CNL) Solution",
        "3. Architecture: Kernel vs. Model (The Two Realms)",
        "4. Language Reference & Syntax Guide",
        "Declarations & Exact Math",
        "The Type System",
        "The Model Bridge (`ask`)",
        "Verification & Self-Correction (`ensure`, `assert`)",
        "Relational Logic Engine (Datalog)",
        "Functions vs. Routines",
        "Modules & Standard Library",
        "Real-World Effects (`observe`, `act`)",
        "5. Hands-On Tutorials (From Scratch)",
        "Tutorial 1: The Basics (Exact Math + AI Fact)",
        "Tutorial 2: Bulletproof Entity Extraction",
        "Tutorial 3: Multi-Hop Relational Reasoning with Datalog",
        "Tutorial 4: Self-Correcting Transactional Retries",
        "6. Best Use Cases & High-Value Applications",
        "7. CLI Cheatsheet & Workflow"
      ],
      "sha256": "09e56c53a6255fdb490f365668db5dadc23842faa63d079d84bf6a12a008e5d4",
      "url": "/docs/essays/symblic_mastery_guide.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_mastery_guide.md",
        "sha256": "09e56c53a6255fdb490f365668db5dadc23842faa63d079d84bf6a12a008e5d4",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "The Natural Language Bridge: How to Think in Symblic",
      "headings": [
        "The Natural Language Bridge: How to Think in Symblic",
        "1. The Core Confusion: Why Symblic Feels Strange at First",
        "The Mental Breakthrough",
        "2. The 4-Step Mental Formula: From English to Symblic",
        "3. The Rosetta Stone: Translating Everyday Language to Symblic",
        "4. Why Types Are Your Secret Superpower",
        "What happens behind the scenes?",
        "5. End-to-End Case Studies",
        "Case Study 1: The Automated Refund Officer",
        "Case Study 2: Tracing Multi-Hop Supply Chains with Datalog",
        "6. How the Original Host's Task Executor Used This Bridge"
      ],
      "sha256": "91eef9600ae712d1d515b6aa886648db2819fa50fd3d7a0b304ef958b0458658",
      "url": "/docs/essays/symblic_natural_language_bridge.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_natural_language_bridge.md",
        "sha256": "91eef9600ae712d1d515b6aa886648db2819fa50fd3d7a0b304ef958b0458658",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "The Universal Epistemic Operating System: The Grand Breakthrough of Unified Symblic",
      "headings": [
        "The Universal Epistemic Operating System: The Grand Breakthrough of Unified Symblic",
        "Executive Summary",
        "1. The 5-Layer Unified Epistemic Architecture",
        "2. What We Learn From This: The Epistemic Lessons",
        "3. Hypothesized Quantitative Leaps",
        "4. What It Formally Proves",
        "5. The Overall Breakthrough"
      ],
      "sha256": "b18c3463664d3256c1d7431d85738cc9fb89ead3b86f68b4e28676141d52c4ef",
      "url": "/docs/essays/symblic_overall_breakthrough.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_overall_breakthrough.md",
        "sha256": "b18c3463664d3256c1d7431d85738cc9fb89ead3b86f68b4e28676141d52c4ef",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Modern Mathematical Physics and the Evolution of Symblic: From OpenAI's Navier-Stokes Proof to Geometric Neuro-Symbolism",
      "headings": [
        "Modern Mathematical Physics and the Evolution of Symblic: From OpenAI's Navier-Stokes Proof to Geometric Neuro-Symbolism",
        "Executive Summary",
        "Master Mapping: Mathematical Physics to Symblic",
        "1. The OpenAI Navier-Stokes Controversy (September 2026)",
        "2. Sobolev Spaces & BKM Regularity",
        "3. Symplectic Geometry & Noether's Theorems",
        "4. Wilsonian Renormalization Group (RG) Context Flow",
        "5. Information Geometry & Fisher-Rao Metric",
        "6. Optimal Transport & Wasserstein Consensus"
      ],
      "sha256": "6bbbbc5ede93a061f21c0455d1e294f039026f6d93be87b36d820c508376acac",
      "url": "/docs/essays/symblic_physics_and_advanced_mathematics.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_physics_and_advanced_mathematics.md",
        "sha256": "6bbbbc5ede93a061f21c0455d1e294f039026f6d93be87b36d820c508376acac",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Quantum Mechanics and Computational Determinism: Does Quantum Mathematics Weaken or Strengthen Symblic's Invariants?",
      "headings": [
        "Quantum Mechanics and Computational Determinism: Does Quantum Mathematics Weaken or Strengthen Symblic's Invariants?",
        "Executive Summary",
        "Why Current Symblic is Only Pseudo-Deterministic",
        "How Quantum Mathematics Eliminates Hidden Stochasticity",
        "1. Non-Commutative Tracking Eliminates Prompt Order Drift",
        "2. ZX-Calculus is Confluent and Deterministic",
        "3. The Ising Ground State is a Unique Global Minimum",
        "4. The No-Cloning Theorem Eradicates Concurrency Race Conditions",
        "The Three Strict Guards Protecting Q-Symblic's Determinism",
        "Comparison Matrix"
      ],
      "sha256": "9e71b5b0ea88f3b31d93c62de50f0055dc4246abb874d5676cf4d2823a78e67d",
      "url": "/docs/essays/symblic_quantum_determinism.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_quantum_determinism.md",
        "sha256": "9e71b5b0ea88f3b31d93c62de50f0055dc4246abb874d5676cf4d2823a78e67d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Quantum Mathematical Foundations for Neuro-Symbolic Computation: Applying Quantum Mechanics to Symblic",
      "headings": [
        "Quantum Mathematical Foundations for Neuro-Symbolic Computation: Applying Quantum Mechanics to Symblic",
        "Executive Summary",
        "Summary of Core Transformations",
        "1. Non-Commuting Epistemic Observables (Birkhoff & von Neumann 1936)",
        "2. Quantum Cognition & Probability Amplitudes (Busemeyer & Bruza 2012)",
        "3. DisCoCat & Diagrammatic ZX-Calculus (Coecke, Abramsky, Clark 2010)",
        "4. Invariants as Quantum Measurement & Decoherence (Zurek 2003)",
        "5. Ising Spin Glass Variational Solving (QUBO & Rayleigh-Ritz)",
        "6. Linear Quantum Types & The No-Cloning Theorem (Girard 1987)"
      ],
      "sha256": "feaa513caaf67dd379ad99ea71af7d1d5eb138047f4581cecd31b54d09dbe537",
      "url": "/docs/essays/symblic_quantum_foundations.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_quantum_foundations.md",
        "sha256": "feaa513caaf67dd379ad99ea71af7d1d5eb138047f4581cecd31b54d09dbe537",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: Strategic Development Roadmap & Exhaustive Use Cases",
      "headings": [
        "Symblic: Strategic Development Roadmap & Exhaustive Use Cases",
        "PART 1: Strategic Roadmap for Developing Symblic Further",
        "1. Language & Type System Enhancements",
        "1.1 Refinement & Dependent Types (Proposal)",
        "1.2 Calibrated Uncertainty & Probabilistic Types (Proposal)",
        "1.3 Linear Temporal Logic (LTL) for Agent Trajectories (Proposal)",
        "1.4 Algebraic Data Types (ADTs) & Pattern Matching (Proposal)",
        "2. Verification, Solvers & Formal Provers",
        "2.1 Native SMT Solver Integration (Z3 / CVC5)",
        "2.2 Formal Proof Export to Lean 4 or Coq",
        "2.3 Automated Autoformalization Engine (English $\\to$ Symblic)",
        "3. Compiler & Execution Optimizations",
        "3.1 Empirical Crystallization (Caching Verified Finite Results)",
        "3.2 Cascading & Checked Routing",
        "3.3 Static Cost & Latency Profiler",
        "4. Distributed Cluster & Multi-Agent Swarms",
        "4.1 Swarm Parallel Scheduler for the worker node Cluster",
        "4.2 Adversarial Red-Team / Blue-Team Debates",
        "4.3 Multi-Modal Sensory Asks (Vision, Audio, CAD) (Proposal)",
        "5. Tooling, Developer Experience & Ecosystem",
        "5.1 Language Server Protocol (LSP) for VS Code / Neovim",
        "5.2 Reactive Interactive Notebook (Symblic Notebook)",
        "5.3 Decentralized Package Registry (`sympkg`)",
        "5.4 Property-Based Fuzzing (`symblic fuzz`)",
        "PART 2: Exhaustive Catalog of Actual Use Cases",
        "Category 1: Enterprise, Legal & Regulatory Compliance",
        "1. Automated Contract Invariant Auditing",
        "2. KYC / AML Banking Sanctions & Fraud Detection",
        "3. GDPR & Privacy Compliance Policy Prover",
        "4. Automated Regulatory Tax Filing Verification",
        "Category 2: Healthcare, Pharmacy & Life Sciences",
        "5. Pediatric & Renal Dosage Safety Checking",
        "6. Clinical Trial Eligibility Matching",
        "7. Automated Chemistry & Biology Lab Protocols",
        "Category 3: Finance, Accounting & Supply Chain",
        "8. Autonomous Accounts Payable (Three-Way Matching)",
        "9. Multi-Tier Supply Chain Single-Point-of-Failure Analysis",
        "10. Commercial Real Estate Lease Abstraction & Rent Roll Auditing",
        "Category 4: Software Engineering, DevSecOps & Cloud Security",
        "11. Automated CVE Vulnerability & Patch Impact Auditing",
        "12. Cloud IAM & RBAC Access-Control Prover",
        "13. Autonomous Bug Fixing with Guaranteed Non-Regression",
        "Category 5: Personal Automation",
        "14. Smart Email & Ticket Triage",
        "15. Workload Admission Control",
        "Category 6: Scientific Research & CAD Hardware Modeling",
        "17. Literate, 100% Reproducible Research Papers (`.symd`)",
        "18. Parametric 3D CAD & Geometry Design",
        "19. Automated Meta-Analyses & Literature Synthesis",
        "3. Summary: Why This Matters"
      ],
      "sha256": "6cf7014f03c661bf0258a91dfde076d27de37211da2c333ca935677209402195",
      "url": "/docs/essays/symblic_roadmap_and_use_cases.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_roadmap_and_use_cases.md",
        "sha256": "6cf7014f03c661bf0258a91dfde076d27de37211da2c333ca935677209402195",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic vs. Python & Other Programming Languages",
      "headings": [
        "Symblic vs. Python & Other Programming Languages",
        "1. Executive Summary: Is Symblic \"Better\"?",
        "2. Comprehensive Comparison Matrix",
        "3. The 7 Major Architectural Advantages of Symblic",
        "1. Lossless, Exact Rational Arithmetic",
        "2. Native Multi-Hop Relational Logic (Datalog)",
        "3. Sterile Isolation Capsules vs. \"Context Rot\"",
        "4. Transactional Self-Correction (`ensure ... else retry`)",
        "5. Multi-Model Consensus & Redundancy",
        "6. Cryptographic Determinism & Replay",
        "7. Safe External Actions (`observe` and `act`)",
        "4. Where Other Languages Are Better",
        "5. The Best Architecture: Symblic + Python Together"
      ],
      "sha256": "dca58d96613c062a1d32c44fac4763f1536b33f4cb916486f9d0b8109868e4e3",
      "url": "/docs/essays/symblic_vs_other_languages.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/essays/symblic_vs_other_languages.md",
        "sha256": "dca58d96613c062a1d32c44fac4763f1536b33f4cb916486f9d0b8109868e4e3",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic beta review — 2026-10-08",
      "headings": [
        "Symblic beta review — 2026-10-08",
        "1. Symblic Terminal",
        "What worked",
        "Findings",
        "2. Symblic Forge",
        "What worked",
        "Findings",
        "3. Symblic English editor (`symblic.html#english`)",
        "What worked",
        "Findings",
        "4. Cross-cutting observations",
        "5. Artifacts",
        "6. Commentary — the state of Symblic, inside and out",
        "7. Fixes applied (same day, post-review)"
      ],
      "sha256": "007f8f5c365c10b0aa6a5e05b500ba09081c51c8c45dd75079df03bc95e1b319",
      "url": "/docs/reference/2026-10-08-symblic-beta-review.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/2026-10-08-symblic-beta-review.md",
        "sha256": "007f8f5c365c10b0aa6a5e05b500ba09081c51c8c45dd75079df03bc95e1b319",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic Autogen: more agents when one is not enough",
      "headings": [
        "Symblic Autogen: more agents when one is not enough",
        "Light local models: the kernel lane",
        "Policy",
        "Submission",
        "Decision procedure",
        "Verdicts: code only",
        "Placement, staging and promotion",
        "Record and events",
        "Handoff protocol for workers",
        "Perpetual lanes",
        "API",
        "CLI",
        "Hub panel",
        "Traps",
        "Limits",
        "Review history"
      ],
      "sha256": "bd881ff2090639f269d31192fb9fa021f047c447593d5ccc468e2473ff4547a5",
      "url": "/docs/reference/AUTOGEN.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/AUTOGEN.md",
        "sha256": "bd881ff2090639f269d31192fb9fa021f047c447593d5ccc468e2473ff4547a5",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic as an autonomous capability compiler",
      "headings": [
        "Symblic as an autonomous capability compiler",
        "1. Position",
        "Concept map",
        "2. The four stages",
        "Proposed promotion rule (Stage IV): designed, not built",
        "3. Algorithm compilation (\"intelligence into algorithms\")",
        "4. Composition of Symblic computations",
        "5. The thought experiment as a runnable protocol",
        "Fixed factors",
        "The compiler ladder",
        "Task families of increasing difficulty",
        "Commands",
        "Measurement",
        "Confounds the operator must report",
        "Placement and stopping",
        "Where the evidence stands",
        "6. Known versus claimed",
        "7. Defects found in the core modules while writing this document"
      ],
      "sha256": "aebd25700cf36c93ff92562e9846f2f0ad4a204831f51e204c42239a9dc17276",
      "url": "/docs/reference/CAPABILITY-COMPILER.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/CAPABILITY-COMPILER.md",
        "sha256": "aebd25700cf36c93ff92562e9846f2f0ad4a204831f51e204c42239a9dc17276",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Frontier ladder: one frozen small model, one budget, six compiler rungs",
      "headings": [
        "Frontier ladder: one frozen small model, one budget, six compiler rungs",
        "Hypothesis",
        "Controls",
        "The ladder: a rung is a mode",
        "Task families",
        "Budget, time and heat",
        "Operator commands, in order",
        "How to read the table",
        "Confounds and limits",
        "Mismatches found while preparing",
        "Verification of this preparation"
      ],
      "sha256": "b8e9eef5fe892a3c8f37ca45e4e77b25c1a707822383690799d323ef5dd56839",
      "url": "/docs/reference/FRONTIER-LADDER.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/FRONTIER-LADDER.md",
        "sha256": "b8e9eef5fe892a3c8f37ca45e4e77b25c1a707822383690799d323ef5dd56839",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Local autogen: light models on the kernel lane",
      "headings": [
        "Local autogen: light models on the kernel lane",
        "What runs where",
        "Starting a run",
        "One attempt",
        "Regeneration, timeouts and stops",
        "Decomposition",
        "Where attempts run",
        "Record",
        "Limits",
        "Tests"
      ],
      "sha256": "6cd620a78a03578a46b2e6adfde1ed320510d105b817af4cb6dac185e00d9d0b",
      "url": "/docs/reference/LOCAL-AUTOGEN.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/LOCAL-AUTOGEN.md",
        "sha256": "6cd620a78a03578a46b2e6adfde1ed320510d105b817af4cb6dac185e00d9d0b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Light local models through Symblic: beta record (2026-10-11)",
      "headings": [
        "Light local models through Symblic: beta record (2026-10-11)",
        "Ladder on the 4-unit mini sheet (Tetris `SHAPES, COLORS`, `cellsOf`, `emptyBoard`, `fits`)",
        "Beta matrix, batch 1 (`symblic/bench/local_beta.py`, 02:01 to 02:40 host local time, node-b and node-d, not on the host)",
        "Autogen through the kernel lane, first run on a local model (02:35 onward, coder:3b on node-i)",
        "Kernel changes made from these failures (all under tests)",
        "What is being built on this evidence",
        "Beta matrix, batch 2 (02:47-03:23, node-b and node-d only; `python3 symblic/bench/local_beta.py report --batch batch2-20261011`)",
        "RESULT 05:50: the 3B rung built the Kirby level (harness 68/68)",
        "RESULT 06:12: the 4B rung built the Kirby level too (harness 68/68)",
        "RESULT 06:28: the 1B rung built the Kirby level, mostly by the 0.5B model (harness 68/68)",
        "RESULT 06:48: the floor. qwen2.5:0.5b alone built the Kirby level (harness 68/68)",
        "Kirby ladder: the sheet variants (04:30)",
        "Host-load incident on the host (02:57-03:45) and the fix",
        "Added for publication: how much of each page the sheets dictated (measured 10:05)"
      ],
      "sha256": "003277ea7b8bafd863bc0f4af4f8440abb263fc0635724dfdc7017f580dd6140",
      "url": "/docs/reference/LOCAL-BETA-REPORT-2026-10-11.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/LOCAL-BETA-REPORT-2026-10-11.md",
        "sha256": "003277ea7b8bafd863bc0f4af4f8440abb263fc0635724dfdc7017f580dd6140",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Local beta: Symblic lanes with light local models",
      "headings": [
        "Local beta: Symblic lanes with light local models",
        "Rules the script enforces",
        "Lanes and what counts as a pass",
        "Fixtures"
      ],
      "sha256": "721a28ce9078895648f7b32bd2666f5fdbfda5e37c82f4fd2bc42dc7fa6bd653",
      "url": "/docs/reference/LOCAL-BETA.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/LOCAL-BETA.md",
        "sha256": "721a28ce9078895648f7b32bd2666f5fdbfda5e37c82f4fd2bc42dc7fa6bd653",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "MICA SOURCES",
      "headings": [],
      "sha256": "93e9ec130387d6ba15329825937cb3232a6138fac492775c5c6f1e204f2f9f24",
      "url": "/docs/reference/MICA-SOURCES.json",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/MICA-SOURCES.json",
        "sha256": "93e9ec130387d6ba15329825937cb3232a6138fac492775c5c6f1e204f2f9f24",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "MICA source-to-method adoption matrix",
      "headings": [
        "MICA source-to-method adoption matrix",
        "ezelikman/parsel",
        "IPRC-DIP/ANPL",
        "ZhangHanDong/agent-spec",
        "archiki/ADaPT",
        "FoundationAgents/ReCode",
        "github/spec-kit",
        "FoundationAgents/AFlow",
        "SqueezeAILab/LLMCompiler",
        "alexzhang13/rlm",
        "princeton-nlp/tree-of-thought-llm",
        "Z3Prover/z3",
        "pschanely/crosshair",
        "HypothesisWorks/hypothesis",
        "dafny-lang/dafny",
        "microsoft/codet",
        "huangd1999/AgentCoder",
        "ggml-org/llama.cpp",
        "dottxt-ai/outlines",
        "google-deepmind/funsearch",
        "lm-sys/routellm",
        "EnvCommons/NL2RepoBench",
        "SWE-bench/SWE-bench"
      ],
      "sha256": "67d8f2a0e740a73bdb150f303e84d0bbbb6b815e712838da6f5c96457f86833d",
      "url": "/docs/reference/MICA-SOURCES.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/MICA-SOURCES.md",
        "sha256": "67d8f2a0e740a73bdb150f303e84d0bbbb6b815e712838da6f5c96457f86833d",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "MICA: bounded contract assembly through native Symblic",
      "headings": [
        "MICA: bounded contract assembly through native Symblic",
        "Authority and evidence",
        "Proposal encoding",
        "Execution path",
        "Budgets, stopping and recovery",
        "Frozen finite verification packs",
        "Models and measurements",
        "Scoped host costs",
        "Accepted Forge construction",
        "Explicit deterministic fragment",
        "Six experimental modes",
        "Agent and browser interface",
        "Validation and remaining work"
      ],
      "sha256": "ce9457c849dd24a54be4cc9b9c9c34699f3e090c86fe0309d72d02e97f584728",
      "url": "/docs/reference/MICA.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/MICA.md",
        "sha256": "ce9457c849dd24a54be4cc9b9c9c34699f3e090c86fe0309d72d02e97f584728",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Reference documents",
      "headings": [
        "Reference documents",
        "Start here",
        "The language",
        "Building with small models",
        "Exact builtins, logic and proofs",
        "Measurements and records",
        "Research behind the design",
        "Critiques",
        "Speculative AI writing",
        "Interfaces of the original host",
        "Images"
      ],
      "sha256": "7489806f3c29a7ecf3455dd8c6a81b6d27c35c2508b7502bf0a616d06f111758",
      "url": "/docs/reference/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/README.md",
        "sha256": "7489806f3c29a7ecf3455dd8c6a81b6d27c35c2508b7502bf0a616d06f111758",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Autonomous recursive decomposition (autogen `until_done`)",
      "headings": [
        "Autonomous recursive decomposition (autogen `until_done`)",
        "1. What the operator asked for",
        "2. Research mechanisms and where they live",
        "2.1 The test designer and its sandbox",
        "3. The `until_done` decision procedure",
        "3.1 Perpetual lanes",
        "3.2 Stuck and resume",
        "4. Record fields and events",
        "5. Worked example",
        "6. Limits and traps",
        "Unproductive splits end (2026-10-11)"
      ],
      "sha256": "f88e1cbe3b56e77ba714169e5b324740977197f8978ae1d4ef8d2c9cc9aa94d7",
      "url": "/docs/reference/RECURSION.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/RECURSION.md",
        "sha256": "f88e1cbe3b56e77ba714169e5b324740977197f8978ae1d4ef8d2c9cc9aa94d7",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic, 2026-10-10 evening: what was built, what was measured, what is live",
      "headings": [
        "Symblic, 2026-10-10 evening: what was built, what was measured, what is live",
        "1. Live on the dashboard (restarts 21:19 and 22:04)",
        "2. Measured, not claimed",
        "3. What autogen is, in one paragraph",
        "4. Reviews that shaped it",
        "5. Private, staged or refused",
        "6. Live experiments (appended as they finish)",
        "7. Reproduce",
        "8. Honest summary",
        "Autogen v2 (2026-10-11, 00:20): regenerate until done"
      ],
      "sha256": "86064f7f7e5c32c227e8d673a6a0f8a0549b792d397a528c94f7637d92736bcd",
      "url": "/docs/reference/REPORT-2026-10-10.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/REPORT-2026-10-10.md",
        "sha256": "86064f7f7e5c32c227e8d673a6a0f8a0549b792d397a528c94f7637d92736bcd",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Declared JSON output shape",
      "headings": [
        "Declared JSON output shape"
      ],
      "sha256": "66d7f95329544e666547810447716d42a910186230eb81092e1765c730977637",
      "url": "/docs/reference/STRUCTURED-JSON.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/STRUCTURED-JSON.md",
        "sha256": "66d7f95329544e666547810447716d42a910186230eb81092e1765c730977637",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Symblic: Empirical Reality, Critical Analysis, and Practical Roadmap",
      "headings": [
        "Symblic: Empirical Reality, Critical Analysis, and Practical Roadmap",
        "1. Executive Summary: Is Symblic a Waste?",
        "2. Anatomy of the Beta Trial: How the Systems Were Created",
        "2.1 The Origin and Pipeline",
        "2.2 The Draft (v1) vs. Executed (v2) Discrepancy",
        "Kirby Animation Test",
        "3. 3D Notes Graph View",
        "3. Empirical Successes: What Truly Works",
        "3.1 Synthesis of Complex Architectural Stacks",
        "3.2 Immune to Context Degradation",
        "3.3 True Reproducibility via Build Disciplinary Rules",
        "4. Honest Downfalls & Real Failures",
        "4.1 The \"Natural English\" Illusion",
        "4.2 The Small-Model Reality Gap",
        "4.3 Fragile Infrastructure Edges",
        "4.4 The Metaphysical / Theoretical Bloat Trap",
        "5. Comparative Evaluation",
        "6. Concrete Engineering Improvements (Roadmap)",
        "1. Static Statement Linter (Pre-Flight Analysis)",
        "2. Hard Step Timeouts & Automated Watchdogs",
        "3. Automatic Test & Assertion Synthesis",
        "4. Standardized Project Manifests",
        "5. Decouple Practical Code from Theoretical Docs",
        "7. Concrete High-Value Use Cases vs. Anti-Patterns",
        "Where Symblic Excels (Recommended Use Cases)",
        "Where Symblic Fails (Anti-Patterns / Do Not Use)",
        "8. Preserved Repository Artifacts"
      ],
      "sha256": "bff55717be4bbeffdc54f3c366a7d50c0bb0b9d49346b0e74528c8687f974a40",
      "url": "/docs/reference/SYMBLIC-CRITICAL-ANALYSIS.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/SYMBLIC-CRITICAL-ANALYSIS.md",
        "sha256": "bff55717be4bbeffdc54f3c366a7d50c0bb0b9d49346b0e74528c8687f974a40",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Evidence records",
      "headings": [
        "Evidence records"
      ],
      "sha256": "f860bfc4e0a1a172b965cc065053e1b8822c8e2b8c7a7f09223769d5aa66b06b",
      "url": "/docs/reference/evidence/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/evidence/README.md",
        "sha256": "f860bfc4e0a1a172b965cc065053e1b8822c8e2b8c7a7f09223769d5aa66b06b",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Reinforcements: independent audits",
      "headings": [
        "Reinforcements: independent audits"
      ],
      "sha256": "2708db7888bb5f7a56e04f397c6d03231a50ec557585bb6cbe3f7e815e9c52bb",
      "url": "/docs/reference/reinforcements/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/docs/reference/reinforcements/README.md",
        "sha256": "2708db7888bb5f7a56e04f397c6d03231a50ec557585bb6cbe3f7e815e9c52bb",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Examples",
      "headings": [
        "Examples",
        "Native programs (`*.sym`)",
        "Crystals (`crystals/`)",
        "Plain-English statements (`english/`)",
        "Handing a bounded task to a small agent (`symblic/delegate`)",
        "Spec sheets, step constructions, workcards and graphs",
        "Records of small-model builds (`small-model-*-20261007/`)",
        "Larger kits"
      ],
      "sha256": "a64b0a7ea7c56118a84ddb3bd2703b40ab2494999adf5192176980180cb7ae84",
      "url": "/examples/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/README.md",
        "sha256": "a64b0a7ea7c56118a84ddb3bd2703b40ab2494999adf5192176980180cb7ae84",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Crystals",
      "headings": [
        "Crystals"
      ],
      "sha256": "96888d1fc181363a1b3d3f6acf2487c74e29e84a608e22a2f390b6aed094d148",
      "url": "/examples/crystals/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/examples/crystals/README.md",
        "sha256": "96888d1fc181363a1b3d3f6acf2487c74e29e84a608e22a2f390b6aed094d148",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Kits: complete spec-sheet builds, with everything needed to trust the result",
      "headings": [
        "Kits: complete spec-sheet builds, with everything needed to trust the result"
      ],
      "sha256": "eb686746703ca28054bb10f754bf31d4285777cf866adccca8e972c80d7bab5c",
      "url": "/kits/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/README.md",
        "sha256": "eb686746703ca28054bb10f754bf31d4285777cf866adccca8e972c80d7bab5c",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Kirby kit: a complete platformer level, written unit by unit by small local models",
      "headings": [
        "Kirby kit: a complete platformer level, written unit by unit by small local models",
        "Layout",
        "Requirements",
        "Checks that need no model",
        "Building it against an Ollama server",
        "The feature contract: what the level must do",
        "The level",
        "Units, time and determinism",
        "Kirby (a 24 x 24 box)",
        "Enemies (24 x 24 boxes)",
        "One step, in order",
        "Input, keys and the page",
        "Three wordings for three model sizes",
        "What a passing build establishes, and what it does not",
        "How this kit was made"
      ],
      "sha256": "0a035e9c44f96e90800d2df97a995ef4ea31ca72a58c7ac0f64a035b50de12d0",
      "url": "/kits/kirby/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/kirby/README.md",
        "sha256": "0a035e9c44f96e90800d2df97a995ef4ea31ca72a58c7ac0f64a035b50de12d0",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Kirby results: seven pages written by small local models",
      "headings": [
        "Kirby results: seven pages written by small local models",
        "Read this before drawing conclusions"
      ],
      "sha256": "fc63420d398f2f47101af1bdc7794381717df6975e231b707a88141c491a65ec",
      "url": "/kits/kirby/results/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/kirby/results/README.md",
        "sha256": "fc63420d398f2f47101af1bdc7794381717df6975e231b707a88141c491a65ec",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "kirby.html",
      "headings": [
        "kirby.html",
        "Shared",
        "Unit `LEVEL`",
        "Unit `mulberry32(seed)`",
        "Unit `tileAt(g, r, c), solidAt(g, r, c), standAt(g, r, c)`",
        "Unit `span(a, size)`",
        "Unit `solidRow(g, r, x, w), standRow(g, r, x, w), solidCol(g, c, y, h)`",
        "Unit `makeEnemy(kind, r, c, rng)`",
        "Unit `parseLevel(rows, rng)`",
        "Unit `newGame(seed)`",
        "Unit `cameraX(x)`",
        "Unit `walk(g)`",
        "Unit `fall(g)`",
        "Unit `moveX(g)`",
        "Unit `moveY(g)`",
        "Unit `jump(g)`",
        "Unit `hurt(g)`",
        "Unit `boxesTouch(ax, ay, aw, bx, by, bw)`",
        "Unit `inFront(k, e)`",
        "Unit `pull(g)`",
        "Unit `waddleStep(g, e)`",
        "Unit `brontoStep(e)`",
        "Unit `moveEnemies(g)`",
        "Unit `swallow(g), spit(g)`",
        "Unit `shotStep(g)`",
        "Unit `touchEnemies(g)`",
        "Unit `touchTiles(g)`",
        "Unit `step(g)`",
        "Unit `tick(g, ms)`",
        "Unit `input(g, action, pressed)`",
        "Unit `snapshot(g)`",
        "Unit `keyAction(e)`",
        "Unit `handleKey(game, e, pressed)`",
        "Unit `circle(ctx, x, y, r, color), diamond(ctx, x, y, r, color)`",
        "Unit `drawTile(ctx, ch, x, y)`",
        "Unit `drawTiles(ctx, g)`",
        "Unit `drawKirby(ctx, g)`",
        "Unit `drawEnemy(ctx, e, cam)`",
        "Unit `drawHud(ctx, g)`",
        "Unit `draw(ctx, g)`",
        "Unit `startGame()`",
        "Assemble `kirby.html`"
      ],
      "sha256": "8dd5e4a3e3f570db9642b9dffaa64baa44fe0269b4bceb922dd0ad0d7923d1c0",
      "url": "/kits/kirby/sheets/kirby-1b.sheet.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/kirby/sheets/kirby-1b.sheet.md",
        "sha256": "8dd5e4a3e3f570db9642b9dffaa64baa44fe0269b4bceb922dd0ad0d7923d1c0",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "kirby.html",
      "headings": [
        "kirby.html",
        "Shared",
        "Unit `LEVEL`",
        "Unit `mulberry32(seed)`",
        "Unit `tileAt(g, r, c), solidAt(g, r, c), standAt(g, r, c)`",
        "Unit `span(a, size)`",
        "Unit `solidRow(g, r, x, w), standRow(g, r, x, w), solidCol(g, c, y, h)`",
        "Unit `makeEnemy(kind, r, c, rng)`",
        "Unit `parseLevel(rows, rng)`",
        "Unit `newGame(seed)`",
        "Unit `cameraX(x)`",
        "Unit `walk(g)`",
        "Unit `fall(g)`",
        "Unit `moveX(g)`",
        "Unit `moveY(g)`",
        "Unit `jump(g)`",
        "Unit `hurt(g)`",
        "Unit `boxesTouch(ax, ay, aw, bx, by, bw)`",
        "Unit `inFront(k, e)`",
        "Unit `pull(g)`",
        "Unit `waddleStep(g, e)`",
        "Unit `brontoStep(e)`",
        "Unit `moveEnemies(g)`",
        "Unit `swallow(g), spit(g)`",
        "Unit `shotStep(g)`",
        "Unit `touchEnemies(g)`",
        "Unit `touchTiles(g)`",
        "Unit `step(g)`",
        "Unit `tick(g, ms)`",
        "Unit `input(g, action, pressed)`",
        "Unit `snapshot(g)`",
        "Unit `keyAction(e)`",
        "Unit `handleKey(game, e, pressed)`",
        "Unit `circle(ctx, x, y, r, color), diamond(ctx, x, y, r, color)`",
        "Unit `drawTile(ctx, ch, x, y)`",
        "Unit `drawTiles(ctx, g)`",
        "Unit `drawKirby(ctx, g)`",
        "Unit `drawEnemy(ctx, e, cam)`",
        "Unit `drawHud(ctx, g)`",
        "Unit `draw(ctx, g)`",
        "Unit `startGame()`",
        "Assemble `kirby.html`"
      ],
      "sha256": "33457b83a73c764c048b5a9e45d3ebfe9cf42cd87d2141c4f45c2af8d56a76fe",
      "url": "/kits/kirby/sheets/kirby-3b.sheet.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/kirby/sheets/kirby-3b.sheet.md",
        "sha256": "33457b83a73c764c048b5a9e45d3ebfe9cf42cd87d2141c4f45c2af8d56a76fe",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "kirby.html",
      "headings": [
        "kirby.html",
        "Shared",
        "Unit `LEVEL`",
        "Unit `mulberry32(seed)`",
        "Unit `tileAt(g, r, c), solidAt(g, r, c), standAt(g, r, c)`",
        "Unit `span(a, size)`",
        "Unit `solidRow(g, r, x, w), standRow(g, r, x, w), solidCol(g, c, y, h)`",
        "Unit `makeEnemy(kind, r, c, rng)`",
        "Unit `parseLevel(rows, rng)`",
        "Unit `newGame(seed)`",
        "Unit `cameraX(x)`",
        "Unit `walk(g)`",
        "Unit `fall(g)`",
        "Unit `moveX(g)`",
        "Unit `moveY(g)`",
        "Unit `jump(g)`",
        "Unit `hurt(g)`",
        "Unit `boxesTouch(ax, ay, aw, bx, by, bw)`",
        "Unit `inFront(k, e)`",
        "Unit `pull(g)`",
        "Unit `waddleStep(g, e)`",
        "Unit `brontoStep(e)`",
        "Unit `moveEnemies(g)`",
        "Unit `swallow(g), spit(g)`",
        "Unit `shotStep(g)`",
        "Unit `touchEnemies(g)`",
        "Unit `touchTiles(g)`",
        "Unit `step(g)`",
        "Unit `tick(g, ms)`",
        "Unit `input(g, action, pressed)`",
        "Unit `snapshot(g)`",
        "Unit `keyAction(e)`",
        "Unit `handleKey(game, e, pressed)`",
        "Unit `circle(ctx, x, y, r, color), diamond(ctx, x, y, r, color)`",
        "Unit `drawTile(ctx, ch, x, y)`",
        "Unit `drawTiles(ctx, g)`",
        "Unit `drawKirby(ctx, g)`",
        "Unit `drawEnemy(ctx, e, cam)`",
        "Unit `drawHud(ctx, g)`",
        "Unit `draw(ctx, g)`",
        "Unit `startGame()`",
        "Assemble `kirby.html`"
      ],
      "sha256": "fb93fcd80d75b3887d446831679b8fd9b820003d964e08a4b6c7c764774f6b20",
      "url": "/kits/kirby/sheets/kirby.sheet.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/kirby/sheets/kirby.sheet.md",
        "sha256": "fb93fcd80d75b3887d446831679b8fd9b820003d964e08a4b6c7c764774f6b20",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Tetris kit: a complete falling-block game, written unit by unit by small local models",
      "headings": [
        "Tetris kit: a complete falling-block game, written unit by unit by small local models",
        "What the page must do",
        "Layout",
        "Requirements",
        "Checks that need no model",
        "Building it against an Ollama server",
        "What made 4B models succeed, and what a pass means",
        "How this kit was made"
      ],
      "sha256": "a67a574a0219028693498546d21340542f473e296fd6c8d0782e78be6c0f75ad",
      "url": "/kits/tetris/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/tetris/README.md",
        "sha256": "a67a574a0219028693498546d21340542f473e296fd6c8d0782e78be6c0f75ad",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    },
    {
      "title": "Tetris results: two pages written by small local models",
      "headings": [
        "Tetris results: two pages written by small local models"
      ],
      "sha256": "d10c1e03b6c74edf2a996da63d49616f8a49c25ad87ca5ef7c6e5c7961b4fe50",
      "url": "/kits/tetris/results/README.md",
      "status": "Public source / indexed metadata; validation not inferred",
      "description": "Public repository source; inspect its stated assumptions, version and evidence limits.",
      "lessons": [],
      "provenance": {
        "kind": "public_repository_source",
        "path": "/kits/tetris/results/README.md",
        "sha256": "d10c1e03b6c74edf2a996da63d49616f8a49c25ad87ca5ef7c6e5c7961b4fe50",
        "indexer": "tools/scripts/symblic_refresh_catalog.py",
        "scope": "source metadata only; lesson links and status do not certify coverage or validity"
      }
    }
  ]
};
