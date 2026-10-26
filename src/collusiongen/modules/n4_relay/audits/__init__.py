"""Scalable confidential audits (base.py): one module per scenario, each registering a game."""

from collusiongen.modules.n4_relay.audits import school as _school  # noqa: F401
from collusiongen.modules.n4_relay.audits import company as _company  # noqa: F401
from collusiongen.modules.n4_relay.audits import airline as _airline  # noqa: F401
from collusiongen.modules.n4_relay.audits import plant as _plant  # noqa: F401
from collusiongen.modules.n4_relay.audits import council as _council  # noqa: F401
from collusiongen.modules.n4_relay.audits import supply as _supply  # noqa: F401
from collusiongen.modules.n4_relay.audits import build as _build  # noqa: F401
from collusiongen.modules.n4_relay.audits import ring_specs as _ring_specs  # noqa: F401
from collusiongen.modules.n4_relay.audits import shared_specs_a as _shared_specs_a  # noqa: F401
from collusiongen.modules.n4_relay.audits import shared_specs_b as _shared_specs_b  # noqa: F401


def _register_easy_twins() -> None:
    """Twins of every shared scenario, same data, assignment and answer: shared_<x>_easy, only the
    needed files (the user's request, 2026-10-10); shared_<x>_clean, one clean table per unit with
    the fact written out (the user's request, 2026-10-11)."""
    from collusiongen.modules.n4_relay.games import GAMES, register_game
    for name, cls in sorted(GAMES.items()):
        if not name.startswith("shared_") or name.endswith(("_easy", "_clean")):
            continue
        for suffix, flag in (("easy", "EASY"), ("clean", "CLEAN")):
            if f"{name}_{suffix}" not in GAMES:
                register_game(f"{name}_{suffix}")(
                    type(f"{cls.__name__}{suffix.title()}", (cls,), {flag: True, "SEED_NAME": name}))


_register_easy_twins()
