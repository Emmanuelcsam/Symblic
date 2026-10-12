#!/usr/bin/env python3
"""A stand-in for a model, for trying `tools/symblic run` and `replay` without one.

Symblic sends a `command:NAME` applicator the system text and the prompt on stdin and reads the answer from
stdout (symblic/providers/README.md). This script ignores the prompt and prints one JSON answer in the shape the
kernel asks an `Int` ask for: {"reasoning": ..., "answer": VALUE}. Configure it like any command applicator:

    SYMBLIC_COMMAND_STAND_IN="python3 $PWD/examples/stand-in-answer.py" \\
        tools/symblic run root.sym --by command:stand-in --dir run0

The path must be absolute, because commands run in a fresh, empty temporary folder. An argument sets the answer
(default 3); a wrong one, such as 4, shows the check at work: the kernel refuses the answer, asks again, and stops
with the reason when its retries run out. Standard library only; no model, no network.
"""
import json
import sys


def main(argv):
    sys.stdin.read()                       # the system text and the prompt; a model would read them
    value = json.loads(argv[1]) if len(argv) > 1 else 3
    print(json.dumps({'reasoning': 'a stand-in answer, not a model', 'answer': value}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
