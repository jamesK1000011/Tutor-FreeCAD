# SPDX-License-Identifier: LGPL-2.1-or-later
"""Simplified Technical English for lesson words: the checks every lesson
(stored or written on the fly by the agent) passes before it runs.

The rules are data (data/ste_rules.json): a short subset of ASD-STE100
Simplified Technical English, Issue 9, in our own words, never its
dictionary. Kinds of text:

    instruction  a step's say: each sentence one instruction, imperative,
                 starting with an action verb, at most 20 words (a step with
                 nothing to do, such as a closing look, may describe)
    hint         a hint: may describe; the general rules
    why          the optional explainer: one sentence, at most 15 words

General rules for all: no passive (is/are/be … + past participle), no -ing
words (other than a few nouns such as "nothing"), no filler words (please,
just, simply …), no sequence words joining two instructions (then, and
then), each number with its unit (15 mm, 90 deg). UI names in **bold** are
taken as written and not checked (they are the program's own words).
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "data", "ste_rules.json")
_RULES = {}


def rules():
    if not _RULES:
        with open(RULES_PATH, encoding="utf-8") as f:
            _RULES.update(json.load(f))
    return _RULES


_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`")
_SENT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*|\d+(?:[.,]\d+)?|[°%²³×]")


def _plain(text):
    """UI names (bold or code) as one neutral word."""
    return _BOLD.sub("UINAME", str(text))


def sentences(text):
    t = " ".join(_plain(text).split())
    return [s for s in _SENT.split(t) if s.strip()]


def words(sentence):
    return _WORD.findall(sentence)


def problems(text, kind="instruction", where="text", may_describe=False):
    """What breaks the rules in text, as short reasons ([] when it passes)."""
    r = rules()
    out = []
    sents = sentences(text)
    if kind == "why" and len(sents) > 1:
        out.append(f"{where}: one sentence only (the explainer)")
    limit = {"instruction": r["max_words_instruction"], "hint": r["max_words_descriptive"], "why": r["max_words_why"]}[kind]
    verbs = set(r["action_verbs"])
    for s in sents:
        ws = words(s)
        low = [w.lower() for w in ws]
        q = f"{where}: “{s[:40]}{'…' if len(s) > 40 else ''}”"
        n = len(ws)
        if n > limit:
            out.append(f"{q} has {n} words; at most {limit}")
        joined = " " + " ".join(low) + " "
        for f in r["fillers"]:
            if f" {f} " in joined:
                out.append(f"{q}: no “{f}”")
        seq = next((x for x in r["sequence_words"] if f" {x} " in joined), None)
        if seq is None and low and low[0] in r.get("sequence_starts", ()):
            seq = low[0]
        if seq:
            out.append(f"{q}: one instruction per sentence, no “{seq}”; write two sentences")
        for i, w in enumerate(low[:-1]):
            if w in r["passive_aux"]:
                nxt = low[i + 1] if low[i + 1] not in ("not", "now", "also", "then") or i + 2 >= len(low) else low[i + 2]
                if (nxt.endswith("ed") and len(nxt) > 4) or nxt in r["participles"]:
                    out.append(f"{q}: passive (“{w} {nxt}”); say who does it")
                    break
        for w in low:
            if w.endswith("ing") and len(w) > 4 and w not in r["ing_allowed"]:
                out.append(f"{q}: no -ing word (“{w}”)")
                break
        for i, w in enumerate(low):
            if re.match(r"^\d", w):
                rest = low[i + 1:i + 2]
                if not rest or (rest[0] not in r["units"] and rest[0] != "×"):
                    out.append(f"{q}: give {w} its unit (15 mm, 90 deg)")
                    break
        if kind == "instruction":
            lead = [w for w in low if w not in r["fillers"]]
            first = lead[0] if lead else ""
            if first in r["not_for_buttons"]:
                out.append(f"{q}: “{first}” is not an approved verb here; use “{r['not_for_buttons'][first]}”")
            elif first not in verbs and not may_describe:
                out.append(f"{q}: start with an action verb ({', '.join(sorted(verbs)[:8])} …)")
            m = re.search(r"(?:,|\band)\s+(" + "|".join(re.escape(v) for v in sorted(verbs, key=len, reverse=True)) + r")\b", s, re.I)
            if m:
                out.append(f"{q}: two instructions (“…{m.group(0).strip()}”); write two sentences")
    return out


def lesson_problems(lesson):
    """Every word of a lesson against the rules: says, hints, explainers and
    branch words."""
    out = []
    for s in lesson.get("steps") or []:
        if not isinstance(s, dict):
            continue
        w = f"steps.{s.get('id')}"
        describe = not s.get("do")  # a step with nothing to do (a closing look) may describe
        if isinstance(s.get("say"), str):
            out += problems(s["say"], "instruction", f"{w}.say", may_describe=describe)
        if isinstance(s.get("why"), str):
            out += problems(s["why"], "why", f"{w}.why")
        for i, h in enumerate(s.get("hints") or []):
            if isinstance(h, str):
                out += problems(h, "hint", f"{w}.hints[{i}]")
        for i, b in enumerate(s.get("branches") or []):
            if isinstance(b, dict) and isinstance(b.get("say"), str):
                out += problems(b["say"], "hint", f"{w}.branches[{i}].say")
    return out
