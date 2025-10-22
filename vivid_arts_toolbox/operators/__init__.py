"""
This package groups all operator modules.

Note:
- The add-on's top-level __init__.py imports operator modules directly
	(e.g., `from .operators import export_to_painter`) and handles their
	register()/unregister() flows. We intentionally avoid re-exporting
	operator classes here to prevent drift when new operators are added.
"""
