"""Partial JSON is a display preview only; it never authorizes a final answer."""
import json


def answer_preview(raw):
    """Read a JSON prefix, exposing only answer text, never quotes/IDs or reasoning.

    Incomplete escapes are withheld until complete. A final JSON parse and citation
    validation still happen in Pipeline, including when this preview looks complete.
    """
    decoder = json.JSONDecoder()
    n = len(raw)

    def whitespace(i):
        while i < n and raw[i].isspace():
            i += 1
        return i

    def string(i):
        try:
            return decoder.raw_decode(raw, i)
        except json.JSONDecodeError:
            # At most an unfinished escape / unicode pair needs trimming. Invalid
            # JSON elsewhere produces no preview and is handled by final validation.
            tail = raw[i:]
            for trim in range(min(12, len(tail)-1) + 1):
                candidate = tail[:len(tail)-trim] + '"'
                try:
                    value = json.loads(candidate)
                    if isinstance(value, str):
                        return value.encode('utf-8', errors='ignore').decode('utf-8'), n
                except json.JSONDecodeError:
                    pass
            return '', n

    def value(i, depth=0):
        i = whitespace(i)
        if i >= n or depth > 24:
            return None, n
        if raw[i] == '"':
            return string(i)
        if raw[i] == '{':
            obj, i = {}, whitespace(i+1)
            while i < n and raw[i] == '"':
                key, j = string(i)
                j = whitespace(j)
                if j >= n or raw[j] != ':':
                    break
                obj[key], i = value(j+1, depth+1)
                i = whitespace(i)
                if i >= n or raw[i] != ',':
                    break
                i = whitespace(i+1)
            return obj, i+1 if i < n and raw[i] == '}' else i
        if raw[i] == '[':
            items, i = [], whitespace(i+1)
            while i < n and raw[i] != ']':
                item, j = value(i, depth+1)
                if j <= i:
                    return items, n
                items.append(item)
                i = whitespace(j)
                if i >= n or raw[i] != ',':
                    break
                i = whitespace(i+1)
            return items, i+1 if i < n and raw[i] == ']' else i
        try:
            return decoder.raw_decode(raw, i)
        except json.JSONDecodeError:
            return None, n

    parsed, _ = value(0)
    if not isinstance(parsed, dict):
        parsed = {}
    claims = parsed.get('claims')
    return {'short_answer': parsed.get('short_answer') if isinstance(parsed.get('short_answer'), str) else '',
            'claims': [c['text'] for c in claims if isinstance(c, dict) and isinstance(c.get('text'), str)]
                      if isinstance(claims, list) else [],
            'reason': parsed.get('reason') if isinstance(parsed.get('reason'), str) else ''}
