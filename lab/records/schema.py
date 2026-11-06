"""Hand-written validators for each record type (spec: Records). Every read goes through load()."""
from pathlib import Path

from lab.records.store import RecordError, read_json

RECORD_TYPES = ("question", "experiment", "setup_event", "setup_repair")
STATUSES = ("planned", "built", "build_failed", "ready", "needs_approval", "approved", "printing", "answered",
            "abandoned")
PROVENANCES = ("prospective", "migrated", "post_hoc")
STRENGTHS = ("slightly", "clearly", "a lot")
VERDICT_KINDS = ("ranking", "inconclusive", "acceptance", "sweep", "criteria")
GRADES = ("clean", "faint", "banded")
WITNESS_CONDITIONS = ("normal", "abnormal", "inconclusive")
ANCHOR_CONDITIONS = ("same", "different", "inconclusive")
OUTCOMES = ("supported", "refuted", "unresolved", "inconclusive")
ROLES = ("variant", "control", "anchor")

S, N, B, L, D, A = str, (int, float), bool, list, dict, object
NUL = type(None)


def F(types, required=False, choices=None, each=None, fields=None):
    """A field rule: allowed types, required or not, allowed values, a rule for each list item, nested fields."""
    return {"types": types if isinstance(types, tuple) else (types,), "required": required, "choices": choices,
            "each": each, "fields": fields}


VARIANT = {"id": F(S, True), "tab": F((S, NUL)), "factor_value": F(A), "role": F(S, choices=ROLES),
           "same_as": F((S, NUL)), "copies": F(int), "label": F(S)}
BUILD = {"id": F(S, True), "ok": F(B, True), "at": F((S, NUL)), "inputs": F(D), "job": F((S, NUL)), "artifact": F((S, NUL)),
         "artifact_sha256": F((S, NUL)), "sliced_sha256": F((S, NUL)), "sliced": F((S, NUL)), "estimate": F((D, NUL)), "plate": F((D, NUL)),
         "measured": F((D, NUL)), "error": F((S, NUL)), "factor_scope": F(S, choices=("specific", "bundle")),
         "bundle_differences": F(L), "notes": F(L), "realization": F((D, NUL)), "check": F((D, NUL)), "staged": F((D, NUL)), "legacy": F(A)}
RUN = {"id": F(S, True), "build_id": F((S, NUL)), "started_at": F((S, NUL)), "setup": F((D, NUL)),
       "baseline_missing": F(L), "usage": F((D, NUL)), "failed": F((D, NUL)), "photos": F(L), "legacy": F(A),
       "printer_log": F((D, NUL)), "usage_revisions": F(L),
       "started_from": F(S, choices=("page", "one-tap")), "started_by": F(S, choices=("pi-hub one-tap",)),
       "one_tap": F((D, NUL)), "bambuddy": F((D, NUL))}
CRITERION = {"key": F(S, True), "label": F(S, True), "choices": F(L, True)}
MARK = {"variant": F(S, True), "mark_z_mm": F((N, NUL)), "defect_z_mm": F((N, NUL))}
WITNESS = {"id": F(S, True), "condition": F(S, True, WITNESS_CONDITIONS), "note": F((S, NUL))}
VERDICT = {"kind": F(S, True, VERDICT_KINDS), "print_runs": F(L), "order": F(L, each=F(L)),
           "strength": F((S, NUL), choices=STRENGTHS + (None,)), "about_target": F((B, NUL)), "lighting": F((S, NUL)),
           "marks": F(L, each=F(D, fields=MARK)), "witness": F((D, NUL), fields=WITNESS),
           "witness_override": F((S, NUL)), "reason": F((S, NUL)), "good_enough": F((B, NUL)),
           "blocking_defects": F(L), "grades": F(D), "note": F((S, NUL)), "by": F(S, True, ("owner",)), "at": F((S, NUL), True),
           "confirmed": F(B)}
ANCHOR = {"id": F(S, True), "compared_to": F(S, True), "condition": F(S, True, ANCHOR_CONDITIONS),
          "strength": F((S, NUL), choices=STRENGTHS + (None,)), "note": F((S, NUL))}
OBSERVATION = {"type": F(S, True), "variant": F((S, NUL)), "assessment": F(A), "confidence": F((N, NUL)),
               "confirmed": F(B, True), "at": F(S, True), "where": F(S), "likely_cause": F(S)}
ANALYSIS = {"claim": F(S, True), "provenance": F(S, True, PROVENANCES), "at": F((S, NUL)), "evidence": F(A)}
APPROVAL = {"build_id": F(S, True), "artifact_sha256": F((S, NUL), True), "approved_reasons": F(L, True),
            "by": F(S, True, ("owner",)), "at": F(S, True), "reason": F(S, True)}
EXPERIMENT = {
    "schema": F(int, True, (1,)), "record_type": F(S, True), "id": F(S, True), "project": F(S, True),
    "question": F(S, True), "provenance": F(S, True, PROVENANCES), "question_text": F(S, True),
    "hypothesis": F(S, True), "prediction": F(S, True), "why_this_test": F(S), "test_kind": F(S, True),
    "factor": F(D, True), "factor_scope": F(S, choices=("specific", "bundle")), "bundle_differences": F(L),
    "controlled": F(D), "dependent_adjustments": F(D), "baseline": F(D), "findings": F(L),
    "judge_on": F((S, NUL)), "expect": F((D, NUL)), "derived_from_artifact": F(L), "derived_from_result": F(L),
    "controls": F(D), "reference_variants": F(L), "build_spec": F((D, NUL)), "status": F(S, True, STATUSES),
    "abandoned_reason": F((S, NUL)), "variants": F(L, True, each=F(D, fields=VARIANT)),
    "builds": F(L, each=F(D, fields=BUILD)), "approval": F((D, NUL), fields=APPROVAL),
    "print_runs": F(L, each=F(D, fields=RUN)), "owner_verdict": F((D, NUL), fields=VERDICT),
    "superseded_verdicts": F(L), "anchors": F(L, each=F(D, fields=ANCHOR)),
    "ai_observations": F(L, each=F(D, fields=OBSERVATION)), "comparison_validity": F((D, NUL)),
    "prediction_outcome": F((S, NUL), choices=OUTCOMES + (None,)), "analysis": F(L, each=F(D, fields=ANALYSIS)),
    "criteria": F(L, each=F(D, fields=CRITERION)), "legacy": F(A)}
STOP = {"reason": F(S, True), "at": F(S, True), "resumed_at": F((S, NUL)), "resume": F((D, NUL)),
        "auto_code": F((S, NUL))}
PLAN = {"id": F(S, True), "after": F((S, NUL)), "if": F(S, True), "next": F(S, True), "status": F(S)}
QUESTION = {"schema": F(int, True, (1,)), "record_type": F(S, True), "id": F(S, True), "project": F(S, True),
            "question": F(S, True), "status": F(S, True, ("active", "closed")), "autonomy_level": F(int, True,
                                                                                                    (0, 1, 2, 3, 4)),
            "budget": F(D, True), "experiments": F(L, True), "plans": F(L, each=F(D, fields=PLAN)),
            "stops": F(L, True, each=F(D, fields=STOP))}
SETUP_EVENT = {"schema": F(int, True, (1,)), "record_type": F(S, True), "id": F(S, True), "kind": F(S, True),
               "at": F(S, True), "supersedes": F(S), "replacement": F(D), "fields": F(D), "note": F((S, NUL))}
SETUP_REPAIR = {"schema": F(int, True, (1,)), "record_type": F(S, True), "repair_id": F(S, True),
                "source_line": F(int, True), "source_sha256": F(S, True), "replacement_event": F(D, True),
                "reason": F(S, True), "at": F(S)}
TABLES = {"question": QUESTION, "experiment": EXPERIMENT, "setup_event": SETUP_EVENT, "setup_repair": SETUP_REPAIR}


def _check(value, rule, where, path):
    if not isinstance(value, rule["types"]) or (isinstance(value, bool) and bool not in rule["types"]
                                                and value is not None):
        names = "/".join("null" if t is NUL else getattr(t, "__name__", "number") for t in rule["types"])
        raise RecordError(path, where, f"expected {names}, found {type(value).__name__} {value!r}")
    if rule["choices"] is not None and value not in rule["choices"]:
        raise RecordError(path, where, f"{value!r} isn't one of {', '.join(map(repr, rule['choices']))}")
    if rule["each"] is not None:
        for i, item in enumerate(value):
            _check(item, rule["each"], f"{where}[{i}]", path)
    if rule["fields"] is not None and isinstance(value, dict):
        _fields(value, rule["fields"], where, path)


def _fields(obj: dict, table: dict, prefix: str, path):
    for k in obj:
        if k not in table:
            raise RecordError(path, f"{prefix}.{k}" if prefix else k, f"unknown field '{k}'")
    for k, rule in table.items():
        where = f"{prefix}.{k}" if prefix else k
        if k not in obj:
            if rule["required"]:
                raise RecordError(path, where, "missing")
            continue
        _check(obj[k], rule, where, path)


def validate(record: dict, record_type: str, path: Path) -> dict:
    if not isinstance(record, dict):
        raise RecordError(path, None, "isn't a JSON object")
    got = record.get("record_type")
    if got != record_type:
        art = "an" if record_type[0] in "aeiou" else "a"
        raise RecordError(path, "record_type", f"is a {got} record, not {art} {record_type}" if got
                          else f"has no record_type; expected {record_type}")
    _fields(record, TABLES[record_type], "", path)
    if record_type == "question":
        for i, s in enumerate(record["stops"]):
            if s.get("resumed_at") and not s.get("resume"):
                raise RecordError(path, f"stops[{i}].resume", "a resumed stop needs its resume entry")
    return record


def load(path: Path, record_type: str) -> dict:
    return validate(read_json(path), record_type, path)
