"""English intake: a fixed list of whole imperative sentences, each mapped to one bounded OS intent.

parse_imperative_sentence('Create a text file named "note.txt".') returns a ParsedIntent with
intent='create_file' and path='note.txt'. Only a WHOLE sentence that matches one of the patterns is
recognized (create, find/locate, read, write, append, make or list a directory, copy, move, delete a
file, save/flush, inspect processes/models/system); quoted arguments are required for paths and text.
Anything else, including a recognized command with extra words after it, is 'unsupported', so a matched
prefix is never executed by accident. No model is involved: this is plain pattern matching, and it does
not understand arbitrary English. The terminal engine (terminal_server.py) executes the intents."""
from __future__ import annotations
import re
import json
from typing import Any, Dict, List, Optional

SUPPORTED_INTENTS = (
    "create_file",
    "locate_file",
    "read_file",
    "write_file",
    "append_file",
    "make_directory",
    "list_directory",
    "copy_file",
    "move_file",
    "remove_file",
    "inspect_process",
    "inspect_model",
    "inspect_system",
    "flush_file",
    "unsupported",
)

# Regex patterns for deterministic extraction
# Matches quoted strings or bare words
QSTR = r'"([^"]*)"|\'([^\']*)\''

def _extract_quoted(text: str) -> List[str]:
    """Extract all quoted string payloads or paths from text."""
    matches = re.findall(QSTR, text)
    res = []
    for m in matches:
        res.append(m[0] if m[0] != "" else m[1])
    return res

class ParsedIntent:
    def __init__(
        self,
        intent: str,
        path: Optional[str] = None,
        destination_path: Optional[str] = None,
        payload: Optional[str] = None,
        process_id: Optional[str] = None,
        model_id: Optional[str] = None,
        arguments: Optional[List[str]] = None,
        raw_text: str = "",
        error: Optional[str] = None,
    ):
        self.intent = intent
        self.path = path
        self.destination_path = destination_path
        self.payload = payload
        self.process_id = process_id
        self.model_id = model_id
        self.arguments = arguments or []
        self.raw_text = raw_text
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "path": self.path,
            "destination_path": self.destination_path,
            "payload": self.payload,
            "process_id": self.process_id,
            "model_id": self.model_id,
            "arguments": self.arguments,
            "raw_text": self.raw_text,
            "error": self.error,
        }

    def to_symblic_program(self) -> str:
        """Native display of the intent as data; this does not execute OS effects.

        OS commands run named adapters in terminal_server. The earlier synthetic
        fs.* effects were not registered Symblic capabilities and were misleading.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return 'program OSIntent.\nlet intent = ' + json.dumps(payload, ensure_ascii=False) + '.\nshow intent.\n'


def parse_imperative_sentence(sentence: str) -> ParsedIntent:
    """Recognize the whole bounded command, never execute a matched substring."""
    import ast
    s = sentence.strip()
    if s.endswith('.'):
        s = s[:-1].rstrip()
    q = r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
    patterns = [
        ('flush_file', r'save\s+(?:the\s+)?file(?:\s+(' + q + '))?', ('path',)),
        ('write_file', r'find\s+(' + q + r')\s+and\s+inside\s+it\s+write\s+(' + q + ')', ('path', 'payload')),
        ('create_file', r'create\s+(?:a\s+)?(?:text\s+)?file\s+(?:named\s+)?(' + q + ')', ('path',)),
        ('locate_file', r'(?:find|locate)(?:\s+(?:the\s+)?file)?\s+(' + q + ')', ('path',)),
        ('read_file', r'read(?:\s+(?:the\s+)?file)?\s+(' + q + ')', ('path',)),
        ('write_file', r'write\s+(' + q + r')\s+to\s+(' + q + ')', ('payload', 'path')),
        ('write_file', r'(?:replace\s+contents\s+of|write(?:\s+to)?)\s+(' + q + r')(?:\s+with)?\s+(' + q + ')', ('path', 'payload')),
        ('append_file', r'append\s+(' + q + r')\s+to\s+(' + q + ')', ('payload', 'path')),
        ('make_directory', r'(?:make|create)\s+directory\s+(' + q + ')', ('path',)),
        ('list_directory', r'list\s+(?:directory|files)(?:\s+(?:in\s+)?(' + q + '))?', ('path',)),
        ('copy_file', r'copy\s+(' + q + r')\s+to\s+(' + q + ')', ('path', 'destination_path')),
        ('move_file', r'move\s+(' + q + r')\s+to\s+(' + q + ')', ('path', 'destination_path')),
        ('remove_file', r'(?:delete|remove)\s+(?:the\s+)?file\s+(' + q + ')', ('path',)),
        ('inspect_process', r'inspect\s+(?:running\s+)?process(?:es)?', ()),
        ('inspect_model', r'inspect\s+models?', ()),
        ('inspect_system', r'inspect\s+system', ()),
    ]
    for intent, pattern, keys in patterns:
        match = re.fullmatch(pattern, s, re.IGNORECASE)
        if match:
            try:
                fields = {key: ast.literal_eval(value) for key, value in zip(keys, match.groups()) if value is not None}
            except (ValueError, SyntaxError):
                return ParsedIntent('unsupported', raw_text=sentence, error='Malformed quoted text')
            if intent == 'list_directory':
                fields.setdefault('path', '.')
            return ParsedIntent(intent, raw_text=sentence, **fields)
    return ParsedIntent('unsupported', raw_text=sentence,
                        error='Unsupported OS command: this intake recognizes only the fixed sentences listed in '
                              'symblic/os/intake.py. Arbitrary English needs an agent, not this intake.')
