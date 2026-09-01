"""Every script compiles, and imports or says why not.

A `NameError` in `scripts/full_run.py` survived the whole 2026-08-23 renumber
because nothing ever imported the module. This file is the cheapest thing that
closes that gap, and it found two more the moment it existed — see
`test_ladder_run_pairs_each_label_with_its_own_module` below.

TWO LAYERS, because the scripts are one-shot measurement programs whose top
level does work rather than defining it:

  1. `compile()` — always runs, needs no corpus, no index and no model. Catches
     a syntax error in a script nobody has run since the last edit.
  2. import — runs the top level, so it needs the environment. A missing
     corpus or an unreachable ollama SKIPS with the reason stated; a NameError
     or an AttributeError FAILS, because those are defects in the code and are
     true on every machine.

The distinction is the point. A suite that goes red when ollama is not running
stops being read, and a suite that skips a NameError never had a reason to
exist.
"""

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
SCRIPTS = sorted(
    p.stem for p in (ROOT / "scripts").glob("*.py") if not p.stem.startswith("_")
)

#: Raised when the machine lacks something, not when the code is wrong.
ENVIRONMENT = (FileNotFoundError, ImportError, ConnectionError, OSError, SystemExit)

#: Raised when the code is wrong, on every machine. Never skipped.
DEFECT = (NameError, AttributeError, SyntaxError, IndentationError, UnboundLocalError)


def test_there_are_scripts_to_check():
    """A glob that silently matched nothing would make every case below pass."""
    assert len(SCRIPTS) >= 5, SCRIPTS


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_compiles(name):
    """No environment needed. This one is never allowed to skip."""
    path = ROOT / "scripts" / f"{name}.py"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def skip_reason(name: str, exc: BaseException) -> str | None:
    """Why this machine could not run the script — or None, meaning it DID.

    EXIT 0 IS A PASS. `ENVIRONMENT` lists SystemExit, so a script that does its
    whole job at import and exits cleanly was reported as "environment, not
    code" and skipped: four of them were (port_prompts, port_prompt_constants,
    fix_tui_live, add_full_retrieval), which understated the coverage of the
    one test CLAUDE.md credits with catching two live bugs in ladder_run.py.
    A nonzero code is still a skip — a missing model, an argparse usage error —
    and the code is named so the reason stays diagnosable. DEFECT never reaches
    here; the caller re-raises it first.
    """
    if isinstance(exc, SystemExit) and exc.code in (0, None):
        return None
    if isinstance(exc, SystemExit):
        return f"{name}: environment, not code — SystemExit: {exc.code}"
    if isinstance(exc, ENVIRONMENT):
        return f"{name}: environment, not code — {type(exc).__name__}: {exc}"
    return f"{name}: needs a live environment — {type(exc).__name__}: {exc}"


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_imports_or_says_why_not(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    added = str(ROOT) not in sys.path
    if added:
        sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(mod)
    except DEFECT:
        raise
    # SystemExit is a BaseException, NOT an Exception — `except Exception`
    # does not catch it, and a script that exits at import would escape this
    # handler entirely. The old code caught it only because ENVIRONMENT named
    # it explicitly.
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        why = skip_reason(name, exc)
        if why:
            pytest.skip(why)
    finally:
        if added:
            sys.path.remove(str(ROOT))


# --- the renumber, in the one script that still had it wrong ----------------


def test_ladder_run_pairs_each_label_with_its_own_module():
    """Rung IDs were renumbered 2026-08-23 (old->new: 3->2, 5->3, 2->5) and the
    MODULES were renamed with them, so r2.py is self-correction and r3.py is
    voting. `ladder_run.py`'s diagnostic line kept the pre-renumber pairing:

        (("r2", r3), ("r4", r4), ("r3", r5), ("r5", r2))

    which printed each module's signature under a different rung's name. The
    body of the script was corrected in 9849c31; this line was missed, and it
    is the kind of thing that is only ever wrong in the output.
    """
    import ast

    path = ROOT / "scripts" / "ladder_run.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))

    # Read the AST, not the source text: the comment above the fix quotes the
    # wrong pairing verbatim so the next reader can see what it was, and a
    # substring check over the file would trip on the explanation.
    pairs = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
            continue
        label, mod = node.elts
        if (isinstance(label, ast.Constant) and isinstance(label.value, str)
                and label.value.startswith("r") and isinstance(mod, ast.Name)):
            pairs.append((label.value, mod.id))

    assert pairs, "no (label, module) pairs found — has the banner moved?"
    for label, mod in pairs:
        assert label == mod, f"{label} is printed against module {mod}"


# --- a script that exits 0 has RUN. It was being counted as unrunnable. ------


def test_a_clean_exit_is_a_pass_not_a_skip():
    """`ENVIRONMENT` includes SystemExit wholesale, so four scripts that do
    their whole job at import and exit 0 — port_prompts, port_prompt_constants,
    fix_tui_live, add_full_retrieval — were reported as "environment, not
    code" and skipped. Exit 0 is success: the script ran on this machine and
    did what it does. Counting it as unrunnable understates the coverage this
    smoke test actually has, in the one test CLAUDE.md credits with catching
    two live bugs in ladder_run.py."""
    assert skip_reason("x", SystemExit(0)) is None
    assert skip_reason("x", SystemExit()) is None


def test_a_nonzero_exit_is_still_a_skip():
    """A script that stops with a code is telling us it could not run here —
    a missing model, an argparse usage error. Still not a defect, still a
    skip, and the code is named so the reason is diagnosable."""
    why = skip_reason("x", SystemExit(2))
    assert why and "2" in why


def test_a_missing_build_artifact_is_still_environment():
    why = skip_reason("x", FileNotFoundError("ladder/cache/snomed.sqlite"))
    assert why and "environment, not code" in why
