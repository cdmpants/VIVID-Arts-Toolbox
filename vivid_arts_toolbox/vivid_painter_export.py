"""
Deprecated module: vivid_painter_export

This module has been superseded by 'vivid_arts_toolbox.export_to_painter'.
It remains only for backward compatibility with older scripts that imported
run_export directly from vivid_painter_export.

No UI classes or Blender registrations live here anymore to avoid duplicate
panels/operators. Use 'vivid_arts_toolbox.export_to_painter' instead.
"""

from .export_to_painter import run_export as run_export  # re-export for compatibility

import warnings as _warnings
_warnings.warn(
    "vivid_arts_toolbox.vivid_painter_export is deprecated. "
    "Use vivid_arts_toolbox.export_to_painter instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["run_export"]
