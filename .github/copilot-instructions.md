The repository is a Blender add-on (Python) that automates photogrammetry workflows: LOD generation, baking, and exporting to Substance Painter.

Keep changes small and Blender-aware: this codebase registers Blender UI panels, PropertyGroups, and Operators. Files to inspect for patterns:
- `vivid_arts_toolbox/__init__.py` — addon register/unregister flow and what classes self-register vs. require `bpy.utils.register_class`.
- `vivid_arts_toolbox/panel.py` — UI layout and how operators are exposed (e.g. `vivid.generate_asset`, `vivid.setup_lods`). Use these ids when creating tests or calling ops.
- `vivid_arts_toolbox/preferences.py` — exact preference names used by runtime code (e.g. `painter_exe_path`, `texture_export_dir`, `meshlab_executable_path`, `enable_pymeshlab_automation`).
- `vivid_arts_toolbox/properties.py` — PropertyGroup names and fields (e.g. `VIVID_PG_BakeProperties`, `vivid_lod_props`) that are attached to `bpy.types.Scene`.
- DEPRECATED: `vivid_arts_toolbox/vivid_painter_export.py` — superseded by `vivid_arts_toolbox/export_to_painter.py` which now contains the UI and backend (`run_export`, `_find_optimized_obj`, `_proj_dirs`). Use `export_to_painter.run_export` in any scripts or tests.
- `vivid_arts_toolbox/utils.py` and `operators/*` — LOD and baking helpers that call external tools (meshlabserver, PyMeshLab, Substance baker, external Blender invocation).

Quick rules for edits
- Don't change Blender API ids (operator `bl_idname`, property names, or preference keys) without updating `__init__.py`, `panel.py`, and any UI code that references them.
- Operators expect specific scene structure and naming conventions (e.g. objects suffixed `_Optimized`, LOD naming `_LOD0`). Preserve these conventions or update callers.
- External tools are optional: code checks prefs before calling (see `preferences.py`). When modifying external-integration code, add clear fallbacks and messages (use `self.report` or raise RuntimeError where the calling code expects it).

Developer workflows & testing notes
- This is a Blender add-on — run and test inside Blender (not plain Python). To load for development:
  1) Install (or load) the folder as an add-on in Blender's Preferences -> Add-ons, or run `bpy.ops.wm.addon_install` programmatically.
  2) Enable the add-on and open the 3D Viewport -> N Panel -> "VIVID Arts Toolbox".
- Many functions require a saved .blend file and scene objects; to test `export_to_painter.run_export` run inside Blender with an active object named `*_Optimized` and a saved .blend (see `_proj_dirs`).
- PyMeshLab automation: preferences flag `enable_pymeshlab_automation` controls usage. If enabled, the README UI shows how to pip-install into Blender's Python; prefer detection and helpful error messages rather than silent failures.

Conventions and patterns to follow in PRs
- Registration: modules with `register()`/`unregister()` (e.g., `operators/*.py`) should be imported in `__init__.py` and wired in the top-level `register()`/`unregister()` order. Note: `vivid_painter_export.py` is deprecated; `export_to_painter.py` self-registers via top-level functions and is imported in `__init__.py`.
- UI foldouts and properties: many panels create/ensure WindowManager or Scene props at runtime (`_ensure_wm_props`, `bake_textures.register_designer_bake`, `bpy.types.Scene.vivid_lod_props`). Use the same helper pattern when adding new UI props.
- Reporting and errors: Use `self.report({'INFO'|'ERROR'|'WARNING'}, ...)` inside Operators and `operator.report` or `context.report` in helpers so Blender surfaces messages correctly.

Examples to reference when implementing features
- To add a new operator: see `operators/export_asset.py` — define `bl_idname` and `execute()`, then add the class to `_classes` in `__init__.py` or provide a `register()` wrapper.
- To read preferences: in an Operator use `prefs = context.preferences.addons[PACKAGE].preferences` (pattern used in `export_to_painter.py`).
- To copy packaged templates: use `_addon_dir()` helper (see `export_to_painter._addon_dir`) and `Path` operations to keep OS-safe file handling.

What not to assume
- This repo is not a standalone CLI tool — most code runs inside Blender's embedded Python and relies on Blender data (bpy). Don't run modules with plain Python without the Blender environment.
- Paths in preferences may be empty — always check before invoking external binaries.

If anything in these instructions is unclear or you need more details (e.g., example test harness that runs operator code headlessly), tell me what to expand and I will iterate.
