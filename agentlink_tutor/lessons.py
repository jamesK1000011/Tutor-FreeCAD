# SPDX-License-Identifier: LGPL-2.1-or-later
"""Lesson files: found, loaded, checked, namespaced, and the person's progress.

A lesson is one <name>.lesson.json in a lessons/ folder, checked against
data/lesson.schema.json and then for what a schema cannot say:

- setup is one of {doc: "new"}, {fixture: "x.FCStd"}, {calls: [...]} or
  {after: "<lesson id>"} (bind may ride beside any of them): after makes
  the lesson the next chapter of another, which it starts from (chain());
- step ids are unique; next and goto name steps;
- every "$var" is defined (vars, setup.bind or a step's bind);
- each check uses the closed vocabulary (checks.py), or a kind an installed
  add-on adds;
- each target spec is one known kind (parsed only; resolving it on screen
  is the window's job);
- each call names a tool Agent Link knows, when the caller says which tools
  there are;
- its words are Simplified Technical English (ste.py, data/ste_rules.json:
  one instruction per sentence, action verbs, short sentences, no passive);
- the hint ladder keeps its rungs: hints 1 and 2 (a nudge, the field) never
  say a value the step's check wants (a number or a file name); only hint 3
  does (hint_problems).

A lesson's id starts with the package that ships it ("agentlink_tutor.pd.pad-
sketch"), so two add-ons' lessons never collide. Lessons the agent writes
on the fly (inline) are named "inline.<name>", have INLINE_MAX_STEPS (30)
steps or fewer and live for the session only; a longer job goes in batches,
each inline lesson after the one before (setup.after), as stored courses
go chapter by chapter.

Add-ons ship lessons too (addon_folders): a lessons/ folder beside an
add-on's agentlink_families module (or the folders its LESSONS names), its
lessons' ids starting with the add-on's package name. installed_library()
holds the Tutor's own and every add-on's.

Progress is kept as id@version lines in FreeCAD's parameters
(Mod/AgentLink/Tutor, Done), on this computer only.
"""
import json
import os
import re
import sys

from . import checks

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "data", "lesson.schema.json")
CORE_DIR = os.path.join(HERE, "lessons")
PACKAGE = __name__.rpartition(".")[0]
SCHEMA_VERSION = 1
INLINE_MAX_STEPS = 30
INLINE_PREFIX = "inline."
SUFFIX = ".lesson.json"
SETUP_KINDS = ("doc", "fixture", "calls", "after")
VAR = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)$")

# Target specs: one kind each, with the options that may ride beside it.
TARGET_KINDS = {
    "cmd": set(), "menu": set(), "wb": set(), "task": set(), "tree": set(),
    "face": {"of"}, "sub": {"of"}, "edge": {"of"}, "dock": set(), "view": set(), "ext": None,
}


class LessonError(ValueError):
    pass


# ---- a small JSON Schema subset (what lesson.schema.json uses) -------------

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(v, t):
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t])


def validate(value, schema, where="$", root=None):
    """Problems with value against schema: type, enum, minimum, maximum,
    minLength, maxLength, pattern, properties, required,
    additionalProperties, items, minItems, maxItems and local $ref."""
    root = root or schema
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        schema = node
    t = schema.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(_is(value, x) for x in ts):
            return [f"{where}: expected {' or '.join(ts)}, got {type(value).__name__}"]
    out = []
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if _is(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{where}: {value} is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{where}: {value} is above {schema['maximum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            out.append(f"{where}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(f"{where}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{where}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                out.append(f"{where}: missing {k}")
        extra = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                out += validate(v, props[k], f"{where}.{k}", root)
            elif extra is False:
                out.append(f"{where}: unexpected {k}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{where}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{where}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, v in enumerate(value):
                out += validate(v, schema["items"], f"{where}[{i}]", root)
    return out


_SCHEMA = None


def schema():
    global _SCHEMA
    if _SCHEMA is None:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


# ---- versions --------------------------------------------------------------


def _parse(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3]) or (0,)


def satisfies(spec, version):
    """True when version meets every clause of spec (">=1.1", ">=1,<2")."""
    have = _parse(version)
    for clause in (c.strip() for c in str(spec).split(",") if c.strip()):
        for op in (">=", "<=", "==", ">", "<"):
            if clause.startswith(op):
                want = _parse(clause[len(op):])
                n = max(len(have), len(want))
                a, b = have + (0,) * (n - len(have)), want + (0,) * (n - len(want))
                if not {">=": a >= b, "<=": a <= b, "==": a == b, ">": a > b, "<": a < b}[op]:
                    return False
                break
        else:
            raise ValueError(f"version clause {clause!r}: use >=, <=, ==, > or <")
    return True


# ---- $vars -----------------------------------------------------------------


def refs(value):
    """Every $name referred to anywhere in value."""
    out = set()
    if isinstance(value, str):
        m = VAR.match(value)
        if m:
            out.add(m.group(1))
    elif isinstance(value, dict):
        for v in value.values():
            out |= refs(v)
    elif isinstance(value, list):
        for v in value:
            out |= refs(v)
    return out


def defined(lesson):
    names = set((lesson.get("vars") or {}).keys())
    names |= set(((lesson.get("setup") or {}).get("bind") or {}).keys())
    for s in lesson.get("steps") or []:
        if isinstance(s, dict):
            names |= set((s.get("bind") or {}).keys())
    return names


# ---- targets (parsed, never resolved here) ---------------------------------


def target_kind(spec):
    """The kind of a target spec, or raise LessonError saying what is wrong."""
    if not isinstance(spec, dict) or not spec:
        raise LessonError("a target is an object such as {cmd: \"PartDesign_Pad\"}")
    kinds = [k for k in spec if k in TARGET_KINDS]
    if len(kinds) != 1:
        raise LessonError(f"a target has one kind of {', '.join(TARGET_KINDS)}; this has {kinds or 'none'}")
    k = kinds[0]
    extra = set(spec) - {k}
    allowed = TARGET_KINDS[k]
    if allowed is not None and extra - allowed:
        raise LessonError(f"target {k} takes no {', '.join(sorted(extra - allowed))}")
    v = spec[k]
    if k in ("cmd", "wb", "tree", "dock", "view", "sub", "ext") and not (isinstance(v, str) and v):
        raise LessonError(f"target {k}: a name")
    if k == "menu" and not (isinstance(v, str) and v) and not (isinstance(v, list) and v and all(isinstance(x, str) and x for x in v)):
        raise LessonError("target menu: the command's name (\"PartDesign_Pad\", its path read from the window), or the titles in order")
    if k == "task" and not (isinstance(v, str) and v) and not (isinstance(v, dict) and v and set(v) <= {"name", "label", "button"}):
        raise LessonError("target task: a label, or {name, label, button}")
    if k in ("face", "edge") and not (isinstance(v, dict) and v):
        raise LessonError(f"target {k}: a query such as {{normal: [0, 0, 1], largest: true}}")
    if k in ("face", "sub", "edge") and not isinstance(spec.get("of"), str):
        inside = isinstance(v, dict) and "of" in v
        raise LessonError(f"target {k}: put of beside {k}, not inside it: {{{k}: {{...}}, of: \"Pad\"}}" if inside
                          else f"target {k}: of, beside {k}, names the object: {{{k}: {{...}}, of: \"Pad\"}}")
    return k


# Query words taken for the ones facepick knows (at: near).
QUERY_ALIASES = {"at": "near", "point": "near"}


def normal_target(spec):
    """spec as the agent may write it, made the one form: of written inside
    a face or edge query moved beside it, and at (or point) taken for near.
    Anything else is left for target_kind to judge."""
    if not isinstance(spec, dict):
        return spec
    out = dict(spec)
    for k in ("face", "edge"):
        q = out.get(k)
        if isinstance(q, dict):
            q = dict(q)
            if "of" in q and "of" not in out:
                out["of"] = q.pop("of")
            for a, b in QUERY_ALIASES.items():
                if a in q and b not in q:
                    q[b] = q.pop(a)
            out[k] = q
    if isinstance(out.get("sub"), dict) and set(out["sub"]) == {"name", "of"} and "of" not in out:
        out["of"], out["sub"] = out["sub"]["of"], out["sub"]["name"]
    return out


# ---- checking a lesson -----------------------------------------------------


def _calls(lesson):
    """(where, call) for every tool call in a lesson, a call's else too."""
    def each(where, c):
        yield where, c
        if isinstance(c, dict):
            for j, e in enumerate(c.get("else") or []):
                yield f"{where}.else[{j}]", e

    for i, c in enumerate((lesson.get("setup") or {}).get("calls") or []):
        yield from each(f"setup.calls[{i}]", c)
    for s in lesson.get("steps") or []:
        if isinstance(s, dict):
            for i, c in enumerate(s.get("do") or []):
                yield from each(f"steps.{s.get('id')}.do[{i}]", c)


# Tools a lesson never calls (red team, 2026-11-18): a lesson is data from
# an add-on or an agent, and "Do it for me" runs its calls as the person's
# click. What runs code, installs code, changes settings, holds the person's
# OK or drives the window's input stays out of every lesson.
NEVER_CALLED = {"batch", "job_start", "live_run", "gui_input", "dialog_answer", "gui_unstick", "addon", "addon_test", "app_extensions",
                "agentlink_update", "app_restart", "app_force_restart", "pref_set", "pref_reset", "pref_import", "pref_pack",
                "port_scaffold", "outputs_clean", "doc_revert", "doc_close", "crash_collect"}


# The tools a lesson may call (red team 3, R3-5): an allow list of CAD,
# view, sketch and read tools. Every other tool is refused, so printers
# (printer_*), slicers (slice*, orca_*), packs (pack_*, library_pack), add-on
# writers and every tool that comes later stay out of lessons. The set holds
# every tool the shipped lessons call (tests/test_red_team.py checks it).
LESSON_TOOLS = frozenset("""
asm_add asm_bom asm_check asm_explode asm_fits asm_ground asm_joint asm_joint_remove asm_limits asm_list asm_new asm_new_part asm_pose
asm_rigid_group asm_sub
bim_building bim_component bim_covering bim_curtain_wall bim_edit bim_equipment bim_fence bim_frame bim_grid bim_level bim_list
bim_material bim_member bim_opening bim_panel bim_pipe bim_pipe_connector bim_profiles bim_quantities bim_rebar bim_reextrude bim_roof
bim_section bim_space bim_stairs bim_structural_system bim_structure bim_truss bim_wall
body_check cam_dressup cam_edit cam_job cam_list cam_op cam_path cam_post cam_setup cam_tool clearance compound_explode compound_filter
doc_info doc_new draft_2d_view draft_array draft_clone draft_dimension draft_facebinder draft_from_sketch draft_hatch draft_label
draft_layer draft_link_array draft_modify draft_outline draft_plane draft_shape draft_style draft_text draft_to_sketch
export fea_buckle fea_clear fea_heat fea_hold fea_load fea_modes fea_native fea_parts fea_probe fea_refine fea_results fea_setup
fea_shell fea_solve feature_edit feature_list feature_remove feature_suppress fem_add fem_mesh
dfm_check fit history_undo history_redo hw_hole import_file link_make material_get material_list material_set measure measure_mass
meshobj_boolean meshobj_boundary meshobj_curvature meshobj_decimate meshobj_export meshobj_from_shape meshobj_info meshobj_merge
meshobj_offset meshobj_primitive meshobj_refine meshobj_repair meshobj_sections meshobj_segments meshobj_smooth meshobj_split
meshobj_transform meshobj_trim
object_align object_appearance object_delete object_duplicate object_get object_group object_list object_rename object_set
param_bind param_list param_remove param_set part_review
part_attach part_boolean part_chamfer part_compound part_container part_datum part_defeature part_extract part_extrude part_face
part_fillet part_fix part_from_mesh part_join part_loft part_offset part_offset2d part_primitive part_project part_refine
part_revolve part_ruled part_section part_slices part_split part_sweep part_thickness part_transform part_wire
pd_binder pd_body_new pd_boolean pd_chamfer pd_clone pd_datum pd_datum_plane pd_draft pd_fillet pd_gear pd_groove pd_helix pd_hole
pd_linear_pattern pd_loft pd_mirrored pd_move_feature pd_multitransform pd_pad pd_pipe pd_pocket pd_polar_pattern pd_primitive
pd_reorder pd_revolution pd_shaft pd_thickness pd_tip
points_crop points_export points_fit points_import points_info points_merge points_mesh points_sample points_structure
recompute section selection session_state shape_query sheet_cells sheet_list sheet_new sheet_read sheet_rows sheet_set sheet_table
show sketch_add sketch_array sketch_attach sketch_bspline sketch_carbon sketch_constrain sketch_copy sketch_edit sketch_extend
sketch_external sketch_join sketch_merge sketch_mirror sketch_new sketch_offset sketch_project sketch_state sketch_to_bspline
sketch_validate surface_blend surface_boundary surface_cut surface_extend surface_fill surface_loft surface_points surface_polynomial
surface_sections surface_sew surface_thicken
td_area td_balloon td_centermarks td_cosmetic td_datum td_detail td_dim td_dim_align td_dim_format td_dim_special td_dimset
td_finish td_gdt td_geometry td_hatch td_leader td_lines td_list td_note td_page td_projection td_section td_section_position
td_table td_title td_tolerance td_view td_view_more td_weld
units_convert varset_new varset_set workbench cmd_run
""".split())
# Of those, the tools that write or read a file by path: a lesson gives
# them a plain file name only, in the session's folder.
FILE_TOOLS = frozenset({"export", "cam_post", "meshobj_export", "points_export", "import_file", "points_import"})
FILE_KEYS = ("path", "file", "files", "export", "import")
# cmd_run in a lesson: only these FreeCAD commands, and the view commands.
LESSON_COMMANDS = frozenset({"Std_Edit", "Sketcher_LeaveSketch", "Std_ToggleVisibility", "Std_ShowSelection", "Std_HideSelection",
                             "Std_SelectAll", "Std_Undo", "Std_Redo"})
# Argument names that hold the person's OK or override a guard: never in a lesson.
GATE_ARGS = ("confirm",)


def never_called(tool):
    """True for a tool no lesson calls: any tool not in LESSON_TOOLS."""
    t = str(tool or "")
    return t not in LESSON_TOOLS or t in NEVER_CALLED or t.startswith(("cookbook_", "macro_")) or "approve" in t


def _gates(obj, where):
    """confirm anywhere in a call's args, or force: true (a gate's
    override; fea_load's force is a vector and stays)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in GATE_ARGS:
                out.append(f"{where}.{k}: a lesson never gives {k} (it is the person's word)")
            elif k == "force" and isinstance(v, bool):
                out.append(f"{where}.force: a lesson never sets force (it overrides a guard)")
            else:
                out += _gates(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _gates(v, f"{where}[{i}]")
    return out


def _plain_name(v):
    return isinstance(v, str) and v.strip() == v and v not in ("", ".", "..") and not any(c in v for c in "/\\~$") and not v.startswith(".")


def call_problems(tool, args, where="call"):
    """Why a lesson may not make this call: [] when it may."""
    t = str(tool or "")
    if never_called(t):
        return [f"{where}: a lesson never calls {t} (only CAD, view, sketch and read tools; not printers, slicers, packs, code or settings)"]
    args = args if isinstance(args, dict) else {}
    out = _gates(args, f"{where}.args")
    if t in FILE_TOOLS:
        for k in FILE_KEYS:
            if k not in args:
                continue
            vals = args[k] if isinstance(args[k], list) else [args[k]]
            if not all(_plain_name(v) for v in vals):
                out.append(f"{where}.args.{k}: a plain file name in the session's folder (no folder, no ~, no $)")
    if t == "cmd_run":
        name = str(args.get("name") or args.get("command") or "")
        if name not in LESSON_COMMANDS and not name.startswith("Std_View"):
            out.append(f"{where}.args.name: a lesson runs only {', '.join(sorted(LESSON_COMMANDS))} or a Std_View command")
    return out


def _never_problems(lesson):
    out = []
    for where, c in _calls(lesson):
        if isinstance(c, dict):
            out += call_problems(c.get("tool"), c.get("args"), where)
    return out


def _else_problems(lesson):
    """A call's else: calls ({tool, args}), none with an else of its own."""
    out = []
    for where, c in _calls(lesson):
        if ".else[" not in where:
            continue
        if not isinstance(c, dict) or not isinstance(c.get("tool"), str) or not re.match(r"^[a-z][a-z0-9_]*$", c["tool"]):
            out.append(f"{where}: a call {{tool, args}}")
            continue
        extra = set(c) - {"tool", "args"}
        if extra:
            out.append(f"{where}: an else call holds tool and args only (not {', '.join(sorted(extra))})")
        if "args" in c and not isinstance(c["args"], dict):
            out.append(f"{where}.args: an object")
    return out


def _bind_problems(bind, where):
    out = []
    for name, spec in (bind or {}).items():
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            out.append(f"{where}.{name}: a binding is named like a variable")
        if isinstance(spec, str) and spec:
            continue
        if isinstance(spec, dict) and len(spec) == 1 and next(iter(spec)) in ("new", "exists"):
            out += checks.problems(spec, f"{where}.{name}")
            continue
        out.append(f"{where}.{name}: an object's name, or {{new: type}} / {{exists: query}}")
    return out


# ---- the hint ladder ---------------------------------------------------------

_NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w.]*\d)")
CMP_KEYS = ("eq", "lt", "gt", "le", "ge")


def expected_values(check, vars_=None):
    """The values a check wants that a person would type: the numbers of its
    comparisons and sizes, and file names; $vars from the lesson's vars."""
    vars_ = vars_ or {}
    out = set()

    def val(v):
        m = VAR.match(v) if isinstance(v, str) else None
        return vars_.get(m.group(1), v) if m else v

    def walk(c):
        if isinstance(c, list):
            for x in c:
                walk(x)
            return
        if not isinstance(c, dict):
            return
        for k, v in c.items():
            if k in CMP_KEYS:
                v = val(v)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.add(float(v))
            elif k == "size" and isinstance(v, list):
                out.update(float(val(x)) for x in v if isinstance(val(x), (int, float)))
            elif k in ("radii", "dims") and isinstance(v, list):
                out.update(float(val(x)) for x in v if isinstance(val(x), (int, float)) and not isinstance(val(x), bool))
            elif k == "file" and isinstance(v, str):
                out.add(v)
            elif k in ("all", "any", "not"):
                walk(v)
            elif k in ("exists", "absent", "new") and isinstance(v, dict):
                for w in (v.get("where") or {}).values():
                    w = val(w)
                    if isinstance(w, dict):
                        walk(w)
                    elif isinstance(w, (int, float)) and not isinstance(w, bool):
                        out.add(float(w))
    walk(check)
    out.discard(0.0)
    return out


def reveals(text, values):
    """The values text says (15 in "Type 15", 15.0 too; Part.stl)."""
    said = set()
    for m in _NUM.finditer(str(text)):
        try:
            said.add(float(m.group(1).replace(",", ".")))
        except ValueError:
            pass
    low = str(text).lower()
    return sorted((v for v in values if (isinstance(v, float) and v in said) or (isinstance(v, str) and v.lower() in low)), key=str)


def hint_problems(lesson):
    """Hints 1 and 2 that give the value away (the ladder's rule for every
    lesson: 1 a nudge, 2 the field only, 3 the value, then Do it for me)."""
    out = []
    for s in lesson.get("steps") or []:
        if not isinstance(s, dict) or "check" not in s:
            continue
        values = expected_values(s["check"], lesson.get("vars"))
        for i, h in enumerate((s.get("hints") or [])[:2]):
            got = reveals(h, values)
            if got:
                shown = ", ".join(f"{v:g}" if isinstance(v, float) else v for v in got)
                out.append(f"steps.{s.get('id')}.hints[{i}]: rung {i + 1} gives away {shown}; only the third hint says the value")
    return out


_BOLD_TOKEN = re.compile(r"\*\*\{[^{}]*\}\*\*")


def word_problems(lesson):
    """The person's words carry no internal names: a command is named by a
    token inside bold (**{PartDesign_Pad}** or **{PartDesign_Pad|Pad}**,
    words.ui_text), never as PartDesign_Pad or Sketcher::SketchObject."""
    from . import words

    out = []
    for s in lesson.get("steps") or []:
        texts = [("say", s.get("say")), ("why", s.get("why"))]
        texts += [(f"hints[{i}]", h) for i, h in enumerate(s.get("hints") or [])]
        texts += [(f"branches[{i}].say", b.get("say")) for i, b in enumerate(s.get("branches") or [])]
        for where, t in texts:
            if not isinstance(t, str):
                continue
            w = f"steps.{s.get('id')}.{where}"
            rest = _BOLD_TOKEN.sub("", t)
            if "{" in rest or "}" in rest:
                out.append(f"{w}: a command goes in bold as **{{Command_Name}}** or **{{Command_Name|words}}**")
            for name in words.internal_names(words.TOKEN.sub("", t)):
                out.append(f"{w}: {name} is FreeCAD's internal name; write what the window shows, or **{{{name}}}** for a command")
    return out


def check(lesson, tools=None, extra_kinds=(), inline=False):
    """What is wrong with a lesson, as a list ([] when fine). tools: the tool
    names there are (None: not checked). extra_kinds: check kinds installed
    add-ons add. Keys starting with _ are the loader's own (its folder,
    owner, the chapters before) and are not checked."""
    if isinstance(lesson, dict):
        lesson = {k: v for k, v in lesson.items() if not k.startswith("_")}
    out = validate(lesson, schema())
    if out or not isinstance(lesson, dict):
        return out
    setup = lesson.get("setup") or {}
    if "setup" in lesson and sum(k in setup for k in SETUP_KINDS) != 1:
        out.append("setup: one of doc, fixture, calls or after")
    if isinstance(setup.get("after"), str) and setup["after"] == lesson["id"]:
        out.append("setup.after: a lesson does not come after itself")
    if "result" in lesson:
        out += checks.problems(lesson["result"], "result", extra_kinds)
        if refs(lesson["result"]) - set((lesson.get("vars") or {}).keys()):
            out.append("result: name objects by a query ({exists: {type, where}}), not by a step's binding; a later chapter reads it")
    if inline:
        if not lesson["id"].startswith(INLINE_PREFIX):
            out.append(f"id: an inline lesson is named {INLINE_PREFIX}<name>")
        if len(lesson["steps"]) > INLINE_MAX_STEPS:
            out.append(f"steps: an inline lesson has {INLINE_MAX_STEPS} steps or fewer; write a longer job in batches, "
                       "each a lesson with setup {after: the one before}")
        if "fixture" in setup:
            out.append("setup.fixture: an inline lesson has no files")
        if any(isinstance(st, dict) and st.get("picture") for st in lesson["steps"]):
            out.append("steps: an inline lesson has no pictures (no files)")
    ids = [s["id"] for s in lesson["steps"]]
    for d in sorted({i for i in ids if ids.count(i) > 1}):
        out.append(f"steps: id {d} is used twice")
    known = set(ids)
    out += _bind_problems(setup.get("bind"), "setup.bind")
    vars_ = set((lesson.get("vars") or {}).keys())
    for name in sorted(vars_ & set((setup.get("bind") or {}).keys())):
        out.append(f"setup.bind.{name}: a binding has the name of a variable (the object then takes the variable's place)")
    for s in lesson["steps"]:
        w = f"steps.{s['id']}"
        for name in sorted(vars_ & set((s.get("bind") or {}).keys())):
            out.append(f"{w}.bind.{name}: a binding has the name of a variable (the object then takes the variable's place)")
        if "check" in s:
            out += checks.problems(s["check"], f"{w}.check", extra_kinds)
        out += _bind_problems(s.get("bind"), f"{w}.bind")
        for i, t in enumerate(s.get("targets") or []):
            try:
                target_kind(t)
            except LessonError as e:
                out.append(f"{w}.targets[{i}]: {e}")
        if s.get("next") is not None and s["next"] not in known:
            out.append(f"{w}.next: no step {s['next']}")
        for i, b in enumerate(s.get("branches") or []):
            if b["goto"] not in known:
                out.append(f"{w}.branches[{i}].goto: no step {b['goto']}")
            out += checks.problems(b["when"], f"{w}.branches[{i}].when", extra_kinds)
    missing = refs(lesson) - defined(lesson)
    for m in sorted(missing):
        out.append(f"${m} is used but never defined (vars, setup.bind or a step's bind)")
    out += _else_problems(lesson)
    out += _never_problems(lesson)
    if tools is not None:
        for where, c in _calls(lesson):
            if not isinstance(c, dict) or not isinstance(c.get("tool"), str) or c["tool"] in tools:
                continue
            # A call with an else may name a tool this Agent Link lacks
            # (a newer one's): its else is done instead.
            alt = [e.get("tool") for e in (c.get("else") or []) if isinstance(e, dict)]
            if alt and all(a in tools for a in alt):
                continue
            out.append(f"{where}: no tool {c['tool']}")
    out += hint_problems(lesson)
    out += word_problems(lesson)
    from . import ste

    out += ste.lesson_problems(lesson)
    if detours(lesson) >= set(ids):
        out.append("steps: every step is a branch's target; the lesson has no main path")
    return out


def pictures(lesson):
    """The picture files a lesson's steps show, as given (pictures/x.png)."""
    return [st["picture"]["file"] for st in lesson.get("steps") or []
            if isinstance(st, dict) and isinstance(st.get("picture"), dict) and isinstance(st["picture"].get("file"), str)]


def picture_problems(lesson, folder):
    """Each picture a lesson shows is a file in its folder (pictures/)."""
    out = []
    for f in pictures(lesson):
        if not os.path.isfile(os.path.join(folder, f)):
            out.append(f"picture {f}: no such file beside the lesson")
    return out


def picture_path(lesson, step):
    """The full path of a step's picture, or None."""
    pic = (step or {}).get("picture")
    folder = lesson.get("_folder") or CORE_DIR
    if not isinstance(pic, dict) or not isinstance(pic.get("file"), str):
        return None
    path = os.path.join(folder, pic["file"])
    return path if os.path.isfile(path) else None


def detours(lesson):
    """Step ids entered only through a branch (skipped on the main path)."""
    return {b["goto"] for s in lesson.get("steps") or [] for b in (s.get("branches") or [])}


# ---- finding lessons -------------------------------------------------------


def _log(msg):
    sys.stderr.write(f"Tutor: {msg}\n")


class Library:
    """The lessons installed: folders, each with the package that owns it.
    A lesson whose id does not start with its owner's name is refused with a
    log line, and so is a second lesson with an id already taken."""

    def __init__(self, tools=None, extra_kinds=()):
        self.folders = []
        self.tools = tools
        self.extra_kinds = tuple(extra_kinds)
        self._lessons = None
        self.refused = []

    def add_folder(self, folder, owner):
        if (folder, owner) not in self.folders:
            self.folders.append((folder, owner))
            self._lessons = None

    def _load(self):
        found = {}
        self.refused = []
        for folder, owner in self.folders:
            if not os.path.isdir(folder):
                continue
            for n in sorted(os.listdir(folder)):
                if not n.endswith(SUFFIX):
                    continue
                path = os.path.join(folder, n)
                try:
                    with open(path, encoding="utf-8") as f:
                        lesson = json.load(f)
                except (OSError, ValueError) as e:
                    self._refuse(path, f"cannot be read ({e})")
                    continue
                problems = check(lesson, self.tools, self.extra_kinds) + picture_problems(lesson, folder)
                if problems:
                    self._refuse(path, "; ".join(problems[:3]))
                    continue
                if not lesson["id"].startswith(owner + "."):
                    self._refuse(path, f"its id {lesson['id']} does not start with {owner}.")
                    continue
                if lesson["id"] in found:
                    self._refuse(path, f"id {lesson['id']} is already taken")
                    continue
                lesson["_folder"] = folder
                lesson["_owner"] = owner
                found[lesson["id"]] = lesson
        for lid in list(found):
            try:
                found[lid]["_after"] = chain(found[lid], found.get)
            except LessonError as e:
                self._refuse(lid + SUFFIX, str(e))
                found.pop(lid)
        self._lessons = found

    def _refuse(self, path, why):
        self.refused.append((os.path.basename(path), why))
        _log(f"lesson {os.path.basename(path)} left out: {why}")

    def lessons(self):
        if self._lessons is None:
            self._load()
        return self._lessons

    def get(self, lesson_id):
        got = self.lessons().get(lesson_id)
        if got is None:
            raise LessonError(f"no lesson {lesson_id}; the lessons are: {', '.join(sorted(self.lessons())) or 'none'}")
        return got

    def listing(self, progress=None, freecad=None, api=None, workbenches=None):
        """[{id, title, minutes, done}] of the lessons whose requires are met."""
        out = []
        for lid, l in sorted(self.lessons().items()):
            if not requirements_met(l, freecad, api, workbenches):
                continue
            row = {"id": lid, "title": l["title"], "minutes": l.get("minutes"),
                   "done": bool(progress and progress.done(lid, l["version"]))}
            if l.get("course"):
                row["course"] = f"{l['course']['id']} {l['course']['chapter']}"
            if l.get("_owner") and l["_owner"] != PACKAGE:
                row["from"] = l["_owner"]
            out.append(row)
        return out


def core_library(tools=None):
    lib = Library(tools)
    lib.add_folder(CORE_DIR, PACKAGE)
    return lib


# ---- add-ons' lessons ----------------------------------------------------------

FAMILIES_SUFFIX = ".agentlink_families"


def _skipped():
    """Add-on modules Agent Link left out (another API): their lessons too."""
    try:
        from agentlink import families

        return {x.get("module") for x in getattr(families, "SKIPPED", ()) or () if isinstance(x, dict)}
    except Exception:  # noqa: BLE001  (no Agent Link: tests)
        return set()


def addon_folders(modules=None):
    """(folder, owner) for each add-on's lessons: every agentlink_families
    module Agent Link loaded (modules: name -> module; sys.modules by
    default), but the Tutor's own and any it left out. The folders are the
    ones its LESSONS names (a folder or a list, beside the module), else
    lessons/ beside it when there is one. The owner is the add-on's package
    name: its lessons' ids start with it."""
    mods = sys.modules if modules is None else modules
    skipped = _skipped()
    out = []
    for name in sorted(n for n in list(mods) if n.endswith(FAMILIES_SUFFIX)):
        owner = name[: -len(FAMILIES_SUFFIX)]
        mod = mods.get(name)
        if mod is None or owner == PACKAGE or "." in owner or name in skipped:
            continue
        here = os.path.dirname(os.path.abspath(getattr(mod, "__file__", "") or ""))
        if not here:
            continue
        named = getattr(mod, "LESSONS", None)
        if isinstance(named, str):
            named = [named]
        folders = [os.path.join(here, f) for f in (named or ["lessons"]) if isinstance(f, str)]
        for f in folders:
            if os.path.isdir(f):
                out.append((f, owner))
    return out


_INSTALLED = {}


def installed_library(tools=None, refresh=False, modules=None):
    """The Tutor's lessons and every installed add-on's (addon_folders),
    plus folders given to the lessons service (register_folder); made
    once, again with refresh."""
    lib = _INSTALLED.get("lib")
    if lib is None or refresh:
        lib = core_library(tools)
        for folder, owner in addon_folders(modules) + list(_REGISTERED):
            lib.add_folder(folder, owner)
        _INSTALLED["lib"] = lib
    return lib


_REGISTERED = []


def register_folder(folder, owner):
    """An add-on's lessons folder given by name (the lessons service:
    hooks.service("lessons").register_folder(folder, owner)); the library
    takes it at once."""
    if not (isinstance(folder, str) and isinstance(owner, str) and owner.isidentifier()):
        raise LessonError("register_folder(folder, owner): a folder, and the add-on's package name")
    if (folder, owner) not in _REGISTERED:
        _REGISTERED.append((folder, owner))
    lib = _INSTALLED.get("lib")
    if lib is not None:
        lib.add_folder(folder, owner)


# ---- chapters ---------------------------------------------------------------------


def chain(lesson, lookup):
    """The lessons a lesson comes after, the first chapter first ([] when
    its setup has no after). lookup(id) -> a lesson or None. A missing
    chapter or a loop raises LessonError."""
    out, seen, cur = [], {lesson.get("id")}, lesson
    while True:
        after = ((cur.get("setup") or {}).get("after"))
        if not after:
            return out
        if after in seen:
            raise LessonError(f"setup.after: the chapters go round in a loop at {after}")
        prev = lookup(after)
        if prev is None:
            raise LessonError(f"setup.after: no lesson {after} (it comes before this one)")
        seen.add(after)
        out.insert(0, prev)
        cur = prev


def requirements_met(lesson, freecad=None, api=None, workbenches=None):
    """False when what is known says the lesson cannot run here; what is not
    known (None) does not hide it."""
    req = lesson.get("requires") or {}
    if freecad and req.get("freecad") and not satisfies(req["freecad"], freecad):
        return False
    if api is not None and req.get("agentlink_api") and not satisfies(req["agentlink_api"], api):
        return False
    if workbenches is not None and not set(req.get("workbenches") or ()) <= set(workbenches):
        return False
    return True


def inline(lesson, tools=None, extra_kinds=(), lookup=None):
    """A lesson the agent wrote, checked: named inline.<name>, 30 steps or
    fewer (a longer job: batches, each after the one before). lookup(id):
    the lessons its setup.after may name (stored ones, and this session's
    inline ones)."""
    if isinstance(lesson, dict):
        # Keys with _ in front are the loader's own (its folder, owner):
        # never the agent's to set (red team, 2026-11-18).
        lesson = {"schema": SCHEMA_VERSION, "version": "0.0.0", **{k: v for k, v in lesson.items() if not str(k).startswith("_")}}
    problems = check(lesson, tools, extra_kinds, inline=True)
    if problems:
        raise LessonError("; ".join(problems[:5]))
    lesson["_after"] = chain(lesson, lookup or (lambda _id: None))
    return lesson


# ---- progress --------------------------------------------------------------

PARAMS = "User parameter:BaseApp/Preferences/Mod/AgentLink/Tutor"


class _Memory:
    def __init__(self):
        self.values = {}

    def GetString(self, name, default=""):
        return self.values.get(name, default)

    def SetString(self, name, value):
        self.values[name] = value


def _params():
    try:
        import FreeCAD

        return FreeCAD.ParamGet(PARAMS)
    except ImportError:
        return _Memory()


class Progress:
    """Lessons done, as id@version lines (Done); a lesson whose version
    changes counts as not done until it is done again."""

    KEY = "Done"

    def __init__(self, params=None):
        self.params = params if params is not None else _params()

    def entries(self):
        raw = self.params.GetString(self.KEY, "")
        return [x for x in (ln.strip() for ln in raw.splitlines()) if x]

    def done(self, lesson_id, version):
        return f"{lesson_id}@{version}" in self.entries()

    def mark(self, lesson_id, version):
        if lesson_id.startswith(INLINE_PREFIX):
            return  # the session's own lessons are not remembered
        keep = [e for e in self.entries() if e.rpartition("@")[0] != lesson_id]
        self.params.SetString(self.KEY, "\n".join(keep + [f"{lesson_id}@{version}"]))
