"""One worksheet, several printed forms, one stack to mark.

A form is a printed copy with its own page code, so a scan of mixed copies sorts itself out:
- versions: the same questions with supports a student needs (scaffolds, large print, more room to write,
  fewer choices, a home language), chosen by the teacher and handed to whoever needs them;
- variants: a different copy for each student (other numbers, other items from a pool, shuffled
  choices), so copying a neighbor's answers doesn't work.

`expand` turns the worksheet as Claude wrote it into a list of (form, definition) pairs, each definition
an ordinary worksheet that `sheet.normalize` checks and `sheet` lays out. The base form is the worksheet as
written (with each variable at its base value).
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
import math
import operator
import random
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

from .sheet import WorksheetError

SCAFFOLDS = ("plain", "hint", "steps", "example", "frame", "word_bank", "glossary")
MODES = ("bilingual", "glossary", "companion")
REFERENCES = ("multiplication", "hundreds", "number_line", "fractions", "glossary", "formulas")
# The home languages of most US English learners (OELA, SY 2022-23, top 20 plus the next most common).
# quality: how far Claude's translation can be trusted unchecked. "high": spot-check; "medium": have a
# bilingual adult read it; "low": print only key words and directions, and have an adult check those (no
# public benchmark covers it, or studies found frequent errors). pdf: "yes" prints correctly in the
# worksheet itself; "plain" prints, in a plain style the language's readers will find stiff; "no" needs a
# shaping engine, so the translation goes on the Word page ("language_mode": "companion").
LANGUAGES = {
    "es": ("Spanish", "Español", "high", "yes"), "ar": ("Arabic", "العربية", "high", "yes"),
    "zh-Hans": ("Chinese (Simplified)", "简体中文", "high", "yes"),
    "zh-Hant": ("Chinese (Traditional)", "繁體中文", "high", "yes"), "vi": ("Vietnamese", "Tiếng Việt", "high", "yes"),
    "pt": ("Portuguese", "Português", "high", "yes"), "ru": ("Russian", "Русский", "high", "yes"),
    "ht": ("Haitian Creole", "Kreyòl ayisyen", "medium", "yes"), "hmn": ("Hmong", "Hmoob", "low", "yes"),
    "ur": ("Urdu", "اردو", "medium", "plain"), "ps": ("Pashto", "پښتو", "low", "plain"),
    "fr": ("French", "Français", "high", "yes"), "ko": ("Korean", "한국어", "high", "yes"),
    "fa": ("Persian (Farsi)", "فارسی", "high", "yes"), "prs": ("Dari", "دری", "medium", "yes"),
    "uk": ("Ukrainian", "Українська", "high", "yes"), "sw": ("Swahili", "Kiswahili", "medium", "yes"),
    "so": ("Somali", "Soomaali", "low", "yes"), "om": ("Oromo", "Afaan Oromoo", "low", "yes"),
    "ne": ("Nepali", "नेपाली", "medium", "no"), "tl": ("Tagalog", "Tagalog", "high", "yes"),
    "te": ("Telugu", "తెలుగు", "medium", "no"), "bn": ("Bengali", "বাংলা", "medium", "no"),
    "my": ("Burmese", "မြန်မာ", "low", "no"), "kar": ("Karen (S'gaw)", "ကညီကျိာ်", "low", "no"),
    "am": ("Amharic", "አማርኛ", "medium", "found"), "mh": ("Marshallese", "Kajin M̧ajeļ", "low", "yes"),
    "chk": ("Chuukese", "Chuuk", "low", "yes"), "rw": ("Kinyarwanda", "Ikinyarwanda", "low", "yes"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ", "medium", "no"), "gu": ("Gujarati", "ગુજરાતી", "medium", "no"),
    "ja": ("Japanese", "日本語", "high", "yes"), "tr": ("Turkish", "Türkçe", "high", "yes"),
    "uz": ("Uzbek", "Oʻzbekcha", "medium", "yes"), "ti": ("Tigrinya", "ትግርኛ", "low", "found"),
}
# What each support does to what a worksheet measures (CCSSO Accessibility Manual, 2016). Accommodations
# keep the standard; modifications change it, so scores earned with them are recorded "with support".
MODIFICATIONS = {"hint": "hints", "example": "a worked example", "steps": "the steps laid out",
                 "max_choices": "fewer answer choices"}

_VERSION_FIELDS = {"id", "name", "label", "scaffolds", "large_print", "space", "per_page", "max_choices", "grid", "only",
                   "language", "language_mode", "translation", "reference", "formulas", "notes", "copies",
                   "comment_language"}
_VARIANT_FIELDS = {"count", "seed", "shuffle_choices"}


# --- Expressions: {{ a * b }} in a variant's text --------------------------------------------------

def _decimal(x) -> Decimal:
    """An exact value as a Decimal: a Fraction divided out to 40 places, so rounding sees its true digits."""
    x = Fraction(str(x)) if isinstance(x, float) else Fraction(x)
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(x.numerator) / Decimal(x.denominator)


def _round_half_up(x, places: int = 0) -> Decimal:
    """Rounded the way schools teach: 2.5 to 3, 0.625 to 0.63 (Python's round() sends 2.5 to 2)."""
    return _decimal(x).quantize(Decimal(1).scaleb(-int(places)), rounding=ROUND_HALF_UP)


def _round(x, places: int = 0):
    r = _round_half_up(x, places)
    return int(r) if int(places) <= 0 else Fraction(r)


def _money(x) -> str:
    return f"${_round_half_up(x, 2):,.2f}"


def _dec(x, places: int = 2) -> str:
    return f"{_round_half_up(x, places):.{int(places)}f}"


def _mixed(x) -> str:
    x = Fraction(x)
    whole, rest = divmod(abs(x.numerator), x.denominator)
    sign = "-" if x < 0 else ""
    if not rest:
        return f"{sign}{whole}"
    return f"{sign}{whole} {rest}/{x.denominator}" if whole else f"{sign}{rest}/{x.denominator}"


FUNCTIONS = {"round": _round, "abs": abs, "min": min, "max": max, "gcd": math.gcd, "lcm": math.lcm,
             "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil, "frac": lambda *a: _frac(*a), "money": _money,
             "dec": _dec, "mixed": _mixed, "pct": lambda x: f"{float(x) * 100:g}%", "str": str}
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
            ast.Gt: operator.gt, ast.GtE: operator.ge}


def evaluate(expr: str, env: dict):
    """A small, safe arithmetic language: numbers, the question's variables, + - * / // % **, comparisons,
    and, or, not, and FUNCTIONS. Division of whole numbers is exact (6/4 is 3/2)."""
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
            return Fraction(str(node.value)) if isinstance(node.value, float) else node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise WorksheetError(f"{{{{{expr}}}}}: no variable named {node.id!r}")
            return env[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            left, right = ev(node.left), ev(node.right)
            if not all(isinstance(v, (int, float, Fraction)) and not isinstance(v, bool) for v in (left, right)):
                raise WorksheetError(f"{{{{{expr}}}}}: arithmetic needs numbers on both sides")
            if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > 10 ** 6):
                raise WorksheetError(f"{{{{{expr}}}}}: powers are limited to exponents up to 12")
            if isinstance(node.op, ast.Div) and isinstance(left, (int, Fraction)) and isinstance(right, (int, Fraction)):
                return _small(Fraction(left) / Fraction(right))
            return _small(_BINARY[type(node.op)](left, right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else (not v) if isinstance(node.op, ast.Not) else v
        if isinstance(node, ast.BoolOp):
            values = [ev(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = ev(comp)
                if type(op) not in _COMPARE or not _COMPARE[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
            if node.keywords:
                raise WorksheetError(f"{{{{{expr}}}}}: write a function's values in order, without names "
                                     f"(dec(x, 1), not dec(x, places=1))")
            return FUNCTIONS[node.func.id](*[ev(a) for a in node.args])
        raise WorksheetError(f"{{{{{expr}}}}}: only arithmetic, comparisons, and {', '.join(FUNCTIONS)} can be used")
    try:
        return ev(ast.parse(expr.strip(), mode="eval"))
    except SyntaxError:
        raise WorksheetError(f"{{{{{expr}}}}} isn't an expression (write it like a * b + 2)")
    except ZeroDivisionError:
        raise WorksheetError(f"{{{{{expr}}}}} divides by zero for some values; add a \"where\" to rule them out")


def _small(value):
    """A result a worksheet could print: refuses runaway numbers before they take the sandbox down."""
    if isinstance(value, (int, Fraction)) and abs(value) > 10 ** 15:
        raise WorksheetError("an expression's value is over 10^15: check the variables' ranges")
    return value


def _frac(a, b=1) -> str:
    """frac(3, 4) prints 3/4: a fraction that stays a fraction (other values print as decimals)."""
    x = Fraction(a) / Fraction(b)
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def show(value) -> str:
    """A value as it prints: 2.5 for a value with an exact decimal, 1/3 for one without, no trailing zeros.
    frac() keeps a fraction as a fraction."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Fraction):
        d = value.denominator
        while d % 2 == 0:
            d //= 2
        while d % 5 == 0:
            d //= 5
        if d == 1:  # an exact decimal, written out exactly (no float rounding of tiny or huge values)
            if value.denominator == 1:
                return str(value.numerator)
            text = format(_decimal(value).normalize(), "f")
            return text
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


_TEMPLATE = re.compile(r"\{\{(.+?)\}\}")


def _fill(value, env: dict, in_diagram: bool = False):
    """Every {{ expression }} in a question's strings, evaluated. In a diagram, a field that is only an
    expression becomes a number, so bar heights and points can vary too."""
    if isinstance(value, str):
        whole = _TEMPLATE.fullmatch(value.strip())
        if whole and in_diagram:
            v = evaluate(whole.group(1), env)
            return float(v) if isinstance(v, Fraction) else v
        return _TEMPLATE.sub(lambda m: show(evaluate(m.group(1), env)), value)
    if isinstance(value, list):
        return [_fill(v, env, in_diagram) for v in value]
    if isinstance(value, dict):
        return {k: v if k in ("vars", "where", "pool") else _fill(v, env, in_diagram or k == "diagram")
                for k, v in value.items()}
    return value


def _values(spec, name: str, where: str) -> list:
    """Every value a variable can take."""
    if isinstance(spec, list):
        return spec
    if not isinstance(spec, dict):
        raise WorksheetError(f"{where}: variable {name!r} needs {{\"min\": ..., \"max\": ...}} or {{\"choose\": [...]}}")
    if "choose" in spec:
        return list(spec["choose"])
    if "min" not in spec or "max" not in spec:
        raise WorksheetError(f"{where}: variable {name!r} needs \"min\" and \"max\" (and optional \"step\"), or \"choose\"")
    lo, hi, step = Fraction(str(spec["min"])), Fraction(str(spec["max"])), Fraction(str(spec.get("step", 1)))
    if step <= 0 or hi < lo:
        raise WorksheetError(f"{where}: variable {name!r} needs min <= max and a step above 0")
    out, v = [], lo
    while v <= hi and len(out) < 10000:
        out.append(int(v) if v.denominator == 1 else v)
        v += step
    return out


def _assignments(q: dict, where: str) -> tuple[dict, list[dict]]:
    """(the base values, every allowed set of values in a shuffled order) for a question's variables."""
    specs = q.get("vars") or {}
    names = list(specs)
    pools = [_values(specs[n], n, where) for n in names]
    if math.prod(len(p) for p in pools) > 200000:
        raise WorksheetError(f"{where}: the variables allow too many combinations; narrow the ranges")
    allowed = []
    for combo in itertools.product(*pools):
        env = dict(zip(names, combo))
        if not q.get("where") or evaluate(q["where"], env):
            allowed.append(env)
    if not allowed:
        raise WorksheetError(f"{where}: no values of the variables meet \"where\": {q['where']}")
    given = {n: specs[n]["base"] for n in names if isinstance(specs[n], dict) and "base" in specs[n]}
    given = {n: Fraction(str(v)) if isinstance(v, float) else v for n, v in given.items()}
    base = next((env for env in allowed if all(env[n] == v for n, v in given.items())), None)
    if base is None:  # the base values given rule out every allowed set
        raise WorksheetError(f"{where}: no allowed values go with the base values {given}: check them against "
                             "\"where\" and each variable's range")
    return base, allowed


def _items(value) -> list[str]:
    """A list written as a list, or as one string (a single step, a single word)."""
    return [value] if isinstance(value, str) else [str(v) for v in value]


def _strip(q: dict) -> dict:
    return {k: v for k, v in q.items() if k not in ("vars", "where", "pool", "support")}


# --- Variants: a copy for each student --------------------------------------------------------------

def _variants(raw: dict, spec: dict) -> list[tuple[dict, dict]]:
    unknown = set(spec) - _VARIANT_FIELDS
    if unknown:
        raise WorksheetError(f"\"variants\": unknown field {', '.join(sorted(unknown))} (use count, seed, shuffle_choices)")
    count = spec.get("count")
    if not isinstance(count, int) or not 2 <= count <= 60:
        raise WorksheetError("\"variants\": \"count\" is how many different copies to print, 2 to 60 (one per student)")
    rng = random.Random(spec.get("seed", 1))
    plans = []  # per question: a function from copy number to the question for that copy
    for q in raw["questions"]:
        where = f"question {q.get('q', '?')}"
        if q.get("type") == "passage" and not q.get("pool"):
            plans.append(lambda n, q=q: q)
            continue
        alternatives = [_strip(q)] + [{**_strip(q), **alt} for alt in q.get("pool", [])]
        if q.get("pool") and any(not isinstance(a, dict) for a in q["pool"]):
            raise WorksheetError(f"{where}: \"pool\" is a list of objects, each the fields that change")
        offset = rng.randrange(len(alternatives))
        if q.get("vars"):
            _, allowed = _assignments(q, where)
            rng.shuffle(allowed)
        else:
            allowed = [{}]

        def plan(n, q=q, alternatives=alternatives, offset=offset, allowed=allowed):
            alt = alternatives[(n + offset) % len(alternatives)]
            return _fill(alt, allowed[n % len(allowed)])
        plans.append(plan)
    forms = []
    for n in range(1, count + 1):
        questions = [plan(n) for plan in plans]
        if spec.get("shuffle_choices"):
            questions = [_shuffle(q, random.Random(f"{spec.get('seed', 1)}-{n}-{q.get('q')}")) for q in questions]
        defn = {**{k: v for k, v in raw.items() if k not in ("versions", "variants", "questions")},
                "questions": questions}
        forms.append(({"id": str(n), "name": f"Copy {n}", "label": str(n), "kind": "variant"}, defn))
    return forms


def _shuffle(q: dict, rng: random.Random) -> dict:
    """A choice question with its options in another order, relettered; each option remembers its letter
    on the base copy (`base`), so class results line up across copies."""
    if q.get("type") != "choice" or q.get("fixed_order") or len(q.get("options", [])) < 3:
        return q
    options = [dict(o) for o in q["options"]]
    order = list(range(len(options)))
    rng.shuffle(order)
    letters = [o["letter"] for o in options]
    out = []
    for new_letter, k in zip(letters, order):
        out.append({**options[k], "letter": new_letter, "base": options[k].get("base", options[k]["letter"])})
    answer = next(o["letter"] for o in out if o["base"] == q["answer"])
    return {**q, "options": out, "answer": answer}


# --- Versions: supports for the students who need them ----------------------------------------------

def _translation(raw: dict, version: dict, base_dir: Path) -> dict:
    lang = version["language"]
    inline = (raw.get("translations") or {}).get(lang)
    if inline:
        return inline
    path = version.get("translation") or f"{raw['assignment_id']}.{lang}.json"
    path = Path(path) if Path(path).is_absolute() else base_dir / path
    if not path.exists():
        raise WorksheetError(f"version {version['id']!r}: language {lang!r} needs its translation, "
                             f"{path.name} beside the worksheet (see \"Home languages\" in the format guide)")
    try:
        return _nfc(json.loads(path.read_text()))
    except ValueError as e:
        raise WorksheetError(f"{path.name}: not valid JSON ({e})")


def _nfc(value):
    """Composed characters (Vietnamese tones, accents), so fonts find one glyph for each letter."""
    import unicodedata
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc(v) for v in value]
    if isinstance(value, dict):
        return {k: _nfc(v) for k, v in value.items()}
    return value


def _reduce(q: dict, keep: int, drop_first: list[str] = ()) -> dict:
    """At most `keep` options: the ones the support names under "drop" go first, then the last ones that
    aren't the answer. Letters stay as printed on the base copy, so marking and results line up."""
    options = q["options"]
    if len(options) <= keep:
        return q

    order = [o for o in options if o["letter"] in drop_first] + \
            [o for o in reversed(options) if o["letter"] not in drop_first]
    gone = set()
    for o in order:
        if len(options) - len(gone) <= keep:
            break
        if o["letter"] != q["answer"]:
            gone.add(o["letter"])
    return {**q, "options": [o for o in options if o["letter"] not in gone],
            "columns": min(q.get("columns", 1), keep)}


def _print_size(raw: dict, version: dict, where: str) -> float:
    """large_print as a scale of the usual print. true means 18pt, the usual large-print minimum; a number
    from 8 up is a size in points; a smaller one is a scale (1.5 = half again as big)."""
    from .sheet import STYLES, grade_of
    value = version.get("large_print")
    if not value:
        return 1.0
    style = raw.get("style") or ("primary" if grade_of(raw) <= 3 else "compact" if raw.get("compact") else "standard")
    base = STYLES.get(style, STYLES["standard"])["prompt_size"]
    if value is True:
        value = 18
    if isinstance(value, str) and re.fullmatch(r"\s*\d+(\.\d+)?\s*pt\s*", value):
        value = float(value.strip().removesuffix("pt"))
    if not isinstance(value, (int, float)) or value <= 0:
        raise WorksheetError(f"{where}: \"large_print\" is true (18pt), a size in points (\"18pt\" or 18), or a "
                             "scale such as 1.5")
    scale = value / base if value >= 8 else float(value)
    version["_pt"] = round(base * scale, 1)
    if not 1 <= scale <= 2.2:
        raise WorksheetError(f"{where}: \"large_print\" {version['large_print']!r} is {scale:.1f} times this "
                             f"worksheet's {base:g}pt print; keep it between {base:g}pt and {base * 2.2:.0f}pt")
    return scale


def _translated(entry, q: dict) -> str:
    """A question's translation as printed: a string as written, or {"prompt", "options": {letter: text}}
    with one option a line, only the options this version printed."""
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict) or "prompt" not in entry:
        raise WorksheetError(f"question {q.get('q')}: a translation is a string, or {{\"prompt\": ..., "
                             "\"options\": {\"A\": ...}}}")
    lines = [entry["prompt"]]
    options = entry.get("options") or {}
    for o in q.get("options", []):
        if o["letter"] in options:
            lines.append(f"{o['letter']}. {options[o['letter']]}")
    return "\n".join(lines)


def _version(raw: dict, version: dict, index: int, base_dir: Path) -> tuple[dict, dict]:
    where = f"version {version.get('id', index)!r}"
    unknown = set(version) - _VERSION_FIELDS - {"_pt"}
    if unknown:
        raise WorksheetError(f"{where}: unknown field {', '.join(sorted(unknown))}; a version can have "
                             f"{', '.join(sorted(_VERSION_FIELDS))}")
    if not version.get("id") or not re.fullmatch(r"[A-Za-z0-9-]{1,12}", str(version["id"])) \
            or re.fullmatch(r"p?\d+", str(version["id"])):  # those name each student's copy and practice sheet
        raise WorksheetError(f"{where}: \"id\" is a short name of letters, digits, or dashes that isn't only a "
                             "number (\"support\", \"es\", \"lp2\")")
    scaffolds = version.get("scaffolds", [])
    scaffolds = list(SCAFFOLDS) if scaffolds == "all" else scaffolds
    bad = [s for s in scaffolds if s not in SCAFFOLDS]
    if bad:
        raise WorksheetError(f"{where}: unknown scaffold {', '.join(bad)}; use any of {', '.join(SCAFFOLDS)}, or \"all\"")
    scale = _print_size(raw, version, where)
    space = float(version.get("space") or 1)
    if version.get("space") is True:
        space = 1.4
    if not 1 <= space <= 2:
        raise WorksheetError(f"{where}: \"space\" is how much more room to write, 1.2 to 2 times (true means 1.4)")
    per_page = version.get("per_page")
    if per_page is not None and (not isinstance(per_page, int) or per_page < 1):
        raise WorksheetError(f"{where}: \"per_page\" is the most questions on a page, 1 or more")
    keep = version.get("max_choices")
    if keep is not None and (not isinstance(keep, int) or keep < 2):
        raise WorksheetError(f"{where}: \"max_choices\" is how many options to keep, 2 or more")
    only = version.get("only")
    numbers = {q.get("q") for q in raw["questions"] if q.get("type", "short") not in ("passage", "note")}
    if only is not None and (not isinstance(only, list) or not only or set(only) - numbers):
        raise WorksheetError(f"{where}: \"only\" lists the question numbers this version keeps, from "
                             f"{', '.join(map(str, sorted(n for n in numbers if n is not None)))}")
    reference = version.get("reference", [])
    bad = [r for r in reference if r not in REFERENCES]
    if bad:
        raise WorksheetError(f"{where}: unknown reference page {', '.join(bad)}; use any of {', '.join(REFERENCES)}")
    lang = version.get("language")
    mode = version.get("language_mode", "bilingual") if lang else None
    if lang and mode not in MODES:
        raise WorksheetError(f"{where}: \"language_mode\" is one of {', '.join(MODES)}")
    known = LANGUAGES.get(lang) if lang else None
    if lang and known and known[3] == "no" and mode != "companion":
        raise WorksheetError(f"{where}: {known[0]} needs a shaping engine to print, which PDFs made here don't "
                             "have. Set \"language_mode\": \"companion\": its translation goes on a Word page, which "
                             "Word and Google Docs print correctly, beside the English worksheet")
    tr = _translation(raw, version, base_dir) if lang else {}

    questions, glossary, changes, terms = [], [], [], []
    if lang and tr.get("glossary"):
        glossary = [(g.get("term", ""), g.get("translation", "")) for g in tr["glossary"]]
    used_passages = {q.get("passage") for q in raw["questions"] if only is None or q.get("q") in only}
    for q in raw["questions"]:
        q = copy.deepcopy(q)
        support = q.pop("support", None) or {}
        q.pop("pool", None)
        if q.get("type") == "passage":
            if only is not None and q.get("id") not in used_passages:
                continue
            questions.append(q)
            if lang and mode == "bilingual" and str(q.get("id")) in (tr.get("passages") or {}):
                questions.append({"type": "passage", "note": True, "lang": lang,
                                  "title": (tr.get("passage_titles") or {}).get(str(q["id"])) or q.get("title") or "",
                                  "text": tr["passages"][str(q["id"])]})
            continue
        if q.get("type") == "note" or (only is not None and q.get("q") not in only):
            if q.get("type") == "note":
                questions.append(q)
            continue
        asides, help_ = [], []  # help_: supports printed here that change what the question measures
        kind = q.get("type", "short")
        if support.get("glossary"):  # for a key-words page, whether or not the words also print on the sheet
            terms += [f"{g['term']}: {g['meaning']}" for g in support["glossary"]]
        if "plain" in scaffolds and support.get("plain"):
            q["prompt"] = support["plain"]
            if q.get("passage") or q.get("spelling"):
                help_.append("plain wording on a reading or vocabulary question")
        if "glossary" in scaffolds and support.get("glossary"):
            asides.append({"kind": "words", "text": [f"{g['term']}: {g['meaning']}" for g in support["glossary"]]})
        if "word_bank" in scaffolds and support.get("word_bank"):
            if kind in ("blanks", "label"):  # the answers to choose from: recall becomes recognition
                q["word_bank"] = list(dict.fromkeys(list(q.get("word_bank", [])) + _items(support["word_bank"])))
                help_.append("a word bank on a fill-in question")
            else:
                asides.append({"kind": "bank", "text": _items(support["word_bank"])})
        if "hint" in scaffolds and support.get("hint"):
            asides.append({"kind": "hint", "text": support["hint"]})
            help_.append(MODIFICATIONS["hint"])
        if "steps" in scaffolds and support.get("steps"):
            asides.append({"kind": "steps", "text": _items(support["steps"])})
            help_.append(MODIFICATIONS["steps"])
        if "example" in scaffolds and support.get("example"):
            asides.append({"kind": "example", "text": support["example"]})
            help_.append(MODIFICATIONS["example"])
        if "frame" in scaffolds and support.get("frame") and kind == "short":
            q["frame"] = [support["frame"]] if isinstance(support["frame"], str) else list(support["frame"])
            q["lines"] = int(q.get("lines", 4)) + len(q["frame"])  # starters take room: the student's lines stay
        if keep and kind == "choice" and len(q.get("options", [])) > keep:
            q = _reduce(q, keep, support.get("drop", []))
            help_.append(MODIFICATIONS["max_choices"])
        if lang and mode == "bilingual":
            entry = (tr.get("questions") or {}).get(str(q.get("q")))
            if entry:
                asides.append({"kind": "translation", "text": _translated(entry, q), "lang": lang})
        if version.get("grid") and kind == "math":
            q["grid"] = True
        if asides:
            q["asides"] = asides
        if help_:
            q["scaffolded"] = sorted(set(help_))
            changes += help_
        questions.append(q)

    head = []
    name = tr.get("name") or (LANGUAGES[lang][1] if lang in LANGUAGES else lang) if lang else ""
    if lang and mode in ("bilingual", "glossary") and (tr.get("instructions") or glossary):
        lines = [tr["instructions"]] if tr.get("instructions") and mode == "bilingual" else []
        if glossary:
            lines += [f"{term} = {meaning}" for term, meaning in glossary]
        title = tr.get("glossary_title") or (tr.get("title") if mode == "bilingual" else "") or name
        head.append({"type": "passage", "note": True, "lang": lang, "title": title, "text": "\n".join(lines)})
    if lang and mode == "companion":  # in English: the language's own script may not print here
        head.append({"type": "passage", "note": True, "title": "",
                     "text": f"Your {version.get('name') or lang} page goes with this sheet. You may answer in "
                             f"{version.get('name') or lang} or English."})
    defn = {**{k: v for k, v in raw.items() if k not in ("versions", "variants", "questions", "translations")},
            "questions": head + questions}
    if version.get("comment_language") or (lang and tr.get("comment_language")):
        defn["comment_language"] = version.get("comment_language") or tr["comment_language"]
    if scale > 1 or space > 1 or per_page:
        defn["print"] = {"scale": scale, "space": space, "per_page": per_page}
    if only is not None:
        changes.append("fewer questions")
    name = (known[1] if known else tr.get("name", lang)) if lang else ""
    form = {"id": str(version["id"]), "name": version.get("name") or str(version["id"]),
            "label": str(version.get("label") or chr(66 + index)), "kind": "version",
            "scaffolds": scaffolds, "large_print": version.get("_pt") if scale > 1 else None,
            "space": space if space > 1 else None,
            "per_page": per_page, "max_choices": keep, "grid": bool(version.get("grid")), "only": only,
            "language": lang, "language_mode": mode, "language_name": name, "reference": reference,
            "formulas": version.get("formulas", []), "glossary_terms": list(dict.fromkeys(terms)),
            "notes": version.get("notes", ""),
            "copies": version.get("copies"), "translation": tr if lang else None,
            "modifies": sorted(set(changes)), "print": defn.get("print"),
            "comment_language": defn.get("comment_language"),
            "language_quality": known[2] if known else ("unknown" if lang else None),
            "language_english": known[0] if known else lang, "reviewed": bool(tr.get("reviewed_by")) if lang else None}
    return form, defn


def expand(raw: dict, base_dir: Path) -> list[tuple[dict, dict]]:
    """[(form, worksheet definition)]: the base first, then each version, then each variant."""
    original = raw
    base_q = []
    for q in raw["questions"]:
        if q.get("vars"):
            values, _ = _assignments(q, f"question {q.get('q', '?')}")
            q = {**_fill({k: v for k, v in q.items() if k != "pool"}, values), "vars": q["vars"],
                 **({"pool": q["pool"]} if "pool" in q else {})}
        base_q.append(q)
    raw = {**raw, "questions": base_q}
    base = {**{k: v for k, v in raw.items() if k not in ("versions", "variants", "translations", "personal")},
            "questions": [_strip(q) if q.get("type") != "passage" else q for q in base_q]}
    forms = [({"id": "", "name": "As written", "label": "", "kind": "base"}, base)]
    versions = raw.get("versions") or []
    if not isinstance(versions, list):
        raise WorksheetError("\"versions\" is a list of versions, each with an \"id\"")
    ids = set()
    if versions:
        forms[0][0]["label"] = "A"  # every copy names its form, so the base copy's footer looks like the others
    for k, v in enumerate(versions):
        form, defn = _version(raw, v, k, base_dir)
        if form["id"] in ids:
            raise WorksheetError(f"two versions have the id {form['id']!r}")
        ids.add(form["id"])
        forms.append((form, defn))
    for k, sheet in enumerate(raw.get("personal") or [], start=1):  # one sheet per student (practice.py)
        defn = {**{key: v for key, v in raw.items() if key not in ("versions", "variants", "personal", "questions")},
                "questions": sheet["questions"],
                **{key: sheet[key] for key in ("print", "comment_language") if sheet.get(key)}}
        forms.append(({"id": f"p{sheet['student_id']}", "name": f"Practice for {sheet['student_id']}",
                       "label": sheet["student_id"], "kind": "variant", "student_id": sheet["student_id"],
                       **{key: sheet[key] for key in ("language", "language_name", "language_english", "modifies")
                          if sheet.get(key)}}, defn))
    if raw.get("variants"):
        if not isinstance(raw["variants"], dict):
            raise WorksheetError("\"variants\" is an object: {\"count\": 30} for a different copy per student")
        forms += _variants(original, raw["variants"])  # drawn from the questions before base values went in
    elif not raw.get("personal") and any(q.get("vars") or q.get("pool") for q in raw["questions"]):
        raise WorksheetError("questions have \"vars\" or \"pool\", but there's no \"variants\": add "
                             "\"variants\": {\"count\": N} to print N different copies")
    return forms



# --- What goes with a version: its home-language page and its reference page --------------------

def companion(form: dict, defn: dict, out_dir: Path) -> Path:
    """The version's translation as a Word page: directions, key words, any passage, and each question.
    Word and Google Docs shape every script, so this prints correctly in any language."""
    from . import script as SC
    from . import wordfile as W
    tr, lang, name = form["translation"], form["language"], form["language_name"]
    rtl = SC.has_rtl(json.dumps(tr, ensure_ascii=False))
    doc = W.Doc()
    doc.para(tr.get("title") or defn["title"], bold=True, size=18, markup=False, lang=lang, rtl=rtl)
    doc.para(f"{defn['title']}: {name}", italic=True, color="666666", markup=False)
    if tr.get("instructions"):
        doc.para(tr["instructions"], markup=False, lang=lang, rtl=rtl)
    if tr.get("glossary"):
        doc.heading(tr.get("glossary_title") or "Key words", 2)
        doc.table([["English", name]] + [[g.get("term", ""), g.get("translation", "")] for g in tr["glossary"]],
                  [2.6, 3.9], lang=lang, rtl_columns=(1,) if rtl else ())
    titles = {b.get("id"): b.get("title") or "" for b in defn["questions"] if b.get("type") == "passage"}
    for pid, text in (tr.get("passages") or {}).items():
        doc.heading(titles.get(pid) or name, 2)
        for para in str(text).split("\n\n"):
            doc.para(para, markup=False, lang=lang, rtl=rtl)
    questions = tr.get("questions") or {}
    for q in defn["questions"]:
        if q.get("type") == "passage" or str(q.get("q")) not in questions:
            continue
        doc.para(f"{q['q']}.", bold=True, after=40, markup=False)
        for line in str(questions[str(q["q"])]).split("\n"):
            doc.para(line, markup=False, lang=lang, rtl=rtl, after=40)
    path = out_dir / "versions" / f"{form['id']}.docx"
    doc.save(path, f"{defn['title']} ({name})")
    return path


def reference_pages(form: dict, defn: dict, out_dir: Path, L) -> Path:
    """A version's reference pages (a multiplication chart, a number line, key words...), one PDF. Students
    keep them beside the worksheet; they have no page code and aren't handed in."""
    from reportlab.pdfgen import canvas
    from . import sheet as S
    f = L.f
    path = out_dir / "versions" / f"{form['id']}-reference.pdf"
    path.parent.mkdir(exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=(S.PAGE_W, S.PAGE_H))
    c.setTitle(f"{defn['title']}: reference")

    def page(title: str) -> None:
        c.setFillGray(0)
        c.setFont(f.bold, 18)
        c.drawString(54, S.PAGE_H - 64, title)
        c.setFont(f.regular, 9)
        c.setFillGray(0.4)
        c.drawString(54, S.PAGE_H - 80, f.text(f"{defn['title']}: keep this page beside your worksheet. "
                                                 "It isn't handed in."))
        c.setFillGray(0)

    def grid(cells: list[list[str]], x0: float, top: float, cell: float, size: float, shade_head: bool) -> None:
        for r, row in enumerate(cells):
            for col, text in enumerate(row):
                x, y = x0 + col * cell, top - (r + 1) * cell
                head = shade_head and (r == 0 or col == 0)
                c.setFillGray(0.88 if head else 1)
                c.setStrokeGray(0.55)
                c.rect(x, y, cell, cell, stroke=1, fill=1)
                c.setFillGray(0)
                c.setFont(f.bold if head else f.regular, size)
                c.drawCentredString(x + cell / 2, y + cell / 2 - size * 0.35, text)

    for kind in form["reference"]:
        if kind == "multiplication":
            page("Multiplication chart")
            cells = [["×"] + [str(n) for n in range(1, 13)]] + \
                    [[str(r)] + [str(r * n) for n in range(1, 13)] for r in range(1, 13)]
            grid(cells, 54, S.PAGE_H - 110, 38.9, 13, True)
        elif kind == "hundreds":
            page("Hundreds chart")
            grid([[str(r * 10 + n) for n in range(1, 11)] for r in range(10)], 56, S.PAGE_H - 120, 50, 16, False)
        elif kind == "number_line":
            page("Number lines")
            for k, (lo, hi, step, every) in enumerate([(-10, 10, 1, 1), (0, 20, 1, 1), (0, 1, Fraction(1, 10), 1)]):
                y = S.PAGE_H - 190 - k * 170
                x0, x1 = 66, S.PAGE_W - 66
                c.setLineWidth(1.4)
                c.line(x0 - 12, y, x1 + 12, y)
                n = int((hi - lo) / step)
                for i in range(n + 1):
                    x = x0 + (x1 - x0) * i / n
                    v = lo + step * i
                    c.line(x, y - 8, x, y + 8)
                    label = show(v) if not isinstance(v, Fraction) or v.denominator == 1 else f"{float(v):.1f}"
                    c.setFont(f.regular, 12 if n <= 20 else 10)
                    c.drawCentredString(x, y - 24, f.text(label.replace("-", "−")))
        elif kind == "fractions":
            page("Fraction strips")
            width, top = S.PAGE_W - 108, S.PAGE_H - 110
            for r, parts in enumerate([1, 2, 3, 4, 5, 6, 8, 10, 12]):
                y = top - (r + 1) * 62
                for k in range(parts):
                    x = 54 + width * k / parts
                    c.setFillGray(0.93 if r % 2 else 1)
                    c.setStrokeGray(0.3)
                    c.rect(x, y, width / parts, 50, stroke=1, fill=1)
                    c.setFillGray(0)
                    c.setFont(f.regular, 13 if parts < 10 else 11)
                    c.drawCentredString(x + width / parts / 2, y + 20, "1" if parts == 1 else f"1/{parts}")
        elif kind in ("glossary", "formulas"):
            entries = []
            if kind == "formulas":
                entries = [str(x) for x in form.get("formulas", [])]
                if not entries:
                    raise WorksheetError(f"version {form['id']!r}: a formulas page needs \"formulas\": [...]")
            else:
                entries = list(form.get("glossary_terms") or [])
                tr = form.get("translation") or {}
                entries += [f"{g.get('term', '')} = {g.get('translation', '')}" for g in tr.get("glossary", [])]
                if not entries:
                    raise WorksheetError(f"version {form['id']!r}: a glossary page needs \"glossary\" in the questions' "
                                         "support, or in the translation")
            page("Formulas" if kind == "formulas" else "Key words")
            y = S.PAGE_H - 120
            for entry in entries:
                font, _ = L.lang_font(entry, form.get("language") or "")
                for line in L.wrap(entry, font, 15, S.PAGE_W - 120):
                    if y < 60:
                        c.showPage()
                        page("Formulas" if kind == "formulas" else "Key words")
                        y = S.PAGE_H - 120
                    L.draw_line(c, line, 60, S.PAGE_W - 60, y, font, 15)
                    y -= 22
                y -= 8
        c.showPage()
    c.save()
    return path
