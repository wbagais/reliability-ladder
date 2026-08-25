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
    except ENVIRONMENT as exc:
        pytest.skip(f"{name}: environment, not code — {type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, DEFECT):
            raise
        pytest.skip(f"{name}: needs a live environment — {type(exc).__name__}: {exc}")
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
