"""Built-in modules. Importing this package registers them (see core.registry).

Only the card benchmark (n4_relay with cards/) is active; the earlier modules are in deprecated/.
"""

from collusiongen.modules.n4_relay import module as _n4  # noqa: F401
