# Authoring contract 1

Start with the installed interface:

```sh
tools/symblic grammar catalog --agent-json
tools/symblic grammar check program.sym --agent-json
```

[The guide](../AUTHORING-GRAMMAR.md) explains the CLI/Python interfaces and result
fields. [program-subset.ebnf](program-subset.ebnf) is a portable authoring subset;
[formula.ebnf](formula.ebnf) and [proof-command.ebnf](proof-command.ebnf) document
the controlled proof surfaces with their explicit side conditions.
[conformance.json](../../../symblic/authoring/grammar/conformance.json) contains finite positive/negative examples.

**Parser acceptance covers only the existing syntax/profile/reference checks.**
It does not execute a program or establish inference validity, proof completion,
intent fidelity or truth. The optional caller-authored command-menu schema can
retain a syntactically valid but invalid inference. The ordinary proof checker
must still reject that inference. These files are not an integrated provider
decoding grammar or a claim that a backend enforces the exported schema.
