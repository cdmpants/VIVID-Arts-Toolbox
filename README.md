## VIVID Arts Toolbox — Photogrammetry LODs, Baking, and Export

Blender add-on to automate photogrammetry asset preparation: LOD generation, cages, per‑UDIM texture bakes via Substance Designer, and exports.

## Prerequisites

- Blender 4.3
- MeshLabServer 2020.06
- Adobe Substance 3D Designer (for headless baker)
- Optional: PyMeshLab (instead of MeshLabServer)

Notes:
- Save your .blend before running operators. The add-on writes working files next to your .blend.
- External tools are optional; when disabled, features depending on them are hidden or produce helpful errors.

## Install and enable

1) In Blender Preferences → Add-ons, install this folder as an add-on and enable “VIVID Arts Toolbox”.
2) Open the N‑panel in the 3D Viewport and select the “VIVID Arts Toolbox” tabs (Asset, LOD, etc.).

## Preferences you may need

- MeshLab Server path or enable PyMeshLab automation
- Substance Designer baker executable path (optional; defaults to the standard install path on Windows)
- Asset destination/export locations (used by export operators)

You can find preferences under Edit → Preferences → Add-ons → VIVID Arts Toolbox.

## Scene and naming conventions

- Source meshes for LODs live under a collection named “Cinema” (base) or “Cinema_Var#” (variants). Objects end with `_Cinema` or are named `Cinema`/`Cinema_Var#`.
- LODs are imported into a collection named “LOD” (or `LOD_Var#` for variants) as objects suffixed `_LOD0 … _LOD3`.
- Cages live in “LOD_Cage” as copies named `<LOD>_Cage`.
- Release mirror: The add-on reads/writes under a Release folder next to your .blend, e.g. `Release/Mesh`, `Release/Textures/LOD`.

## Panel overview (N‑panel → LOD)

- Generate LODs: compute and import LOD0–3, collider and shadow proxies (optional).
- LOD Textures:
	- Bake only LOD0 (default ON): restricts cage generation and baking to LOD0.
	- Merge UDIMs (default ON): after per‑UDIM bakes, tiles are composited into a single square texture per map and the originals are removed. While enabled, “essential only” is disabled.
	- Bake only essential textures (default ON): only bake Normal, BentNormal (all LODs) and Displacement (LOD0 only). Disabled when “Merge UDIMs” is ON.
	- Displace Modifier Strength (baseline) and per‑LOD overrides for LOD1–LOD3.
	- Generate LOD Cages (idempotent, respects “Bake only LOD0”).
	- Max Resolution (LOD0; lower LODs bake at 1/2, 1/4, 1/8).
	- Bake LOD Textures (per‑UDIM runs through Designer using `resources/bakeLOD_preset.json`).

## Quickstart workflow

1) Prepare your Cinema mesh(es) and save the .blend.
2) LODs → Generate LODs
	 - Set “LOD0 Target Tris”; LOD1–3 are ratios of LOD0.
	 - Data Transfer setup happens at the end, sourcing normals on LOD1–3 from LOD0.
3) LODs → LOD Textures
	 - Optionally “Generate LOD Cages” and adjust Displace strengths.
	 - Choose Max Resolution.
	 - “Bake only LOD0” (default ON) for quick iteration; uncheck to bake all LODs.
	 - “Bake only essential textures” (default ON) bakes Normal/BentNormal for all LODs and Displacement only for LOD0.
	 - Click “Bake LOD Textures”. Outputs go to `Release/Textures/LOD`.

## LOD generation details

- LOD0 is an explicit triangle target reduced directly from Cinema. LOD1–3 are computed as ratios of LOD0 but still reduced from Cinema for fidelity.
- Imported LODs are placed under “LOD”, re‑assigned materials by UDIM from the Cinema mesh, and unused material slots are pruned.
- At the end of setup, a Data Transfer modifier is added to LOD1–LOD3 (skipping LOD0) with the source set to LOD0. The mapping uses custom loop normals with `POLYINTERP_LNORPROJ`.
- Optional extras:
	- MeshCollider from LOD0 (decimated).
	- ShadowProxy meshes per LOD, with independent ratios.
- UV layers are renamed to `UVMap` (first) and `Lightmap` (second) when present.

## LOD cages

- “Generate LOD Cages” duplicates each LOD to “LOD_Cage”, adds a Displace modifier, and links only to the “LOD_Cage” collection.
- Idempotent: re‑running removes previous cages and recreates them. Robust duplication (no reliance on active object).
- Strength controls:
	- Global “Displace Modifier Strength” is the baseline (used for LOD0 and fallback for others).
	- Per‑LOD overrides exist for LOD1–LOD3. They’re hidden when “Bake only LOD0” is ON.
- When “Bake only LOD0” is ON, only an LOD0 cage is generated.

## LOD baking via Substance Designer

- Requirements per UDIM tile:
	- Always required: Normal
	- Required when “essential only” is OFF: BaseColor
	- Optional (warn only): BentNormal
- Source texture naming (under `Release/Textures`):
	- `<BaseName>_UDIM_Normal.*`
	- `<BaseName>_UDIM_BaseColor.*`
	- `<BaseName>_UDIM_BentNormal.*`
	- Example: `Rock_Cliff_1001_Normal.tif`
- The preset `resources/bakeLOD_preset.json` is patched per run:
	- TextureTransfer bakers get `source_texture_path` set per UDIM if found; otherwise they’re disabled (soft requirement) unless they’re hard‑required.
	- AO baker receives the Cinema Normal via `normal_map_path`.
	- When “Bake only essential textures” is ON:
		- Keep Normal and BentNormal for all LODs.
		- Keep Displacement only for LOD0.
		- Disable other bakers.
- Max Resolution sets LOD0 resolution; lower LODs bake at 1/2, 1/4, 1/8.
- Outputs: `Release/Textures/LOD`. The add‑on wipes only this subfolder before a bake.

### UDIM merge and export UV remap

- When “Merge UDIMs” is ON, the add‑on merges all UDIM tiles for each baked map into a single square texture per LOD (stored under `Release/Textures/LOD/<LOD>/`), named `<BaseName>_LOD#_<TextureType>.*` (e.g., `Rock_Cliff_LOD0_Normal.tif`).
- On export (Export LODs), UVs for LOD meshes are remapped non‑destructively into a square N×N grid matching the merge order (UDIM ascending, row‑major). The original UVs are restored immediately after export.
- Shadow proxies and colliders are exported without UV remapping.

## Troubleshooting

- “No *_Cinema.fbx found in Release/Mesh”: Ensure your Release mirror contains a `*_Cinema.fbx` under `Release/Mesh` (or Release root for legacy). The LOD bake operator needs it as the high source.
- Missing Normal/BaseColor: Check texture naming under `Release/Textures` and that each UDIM tile has a file. With “essential only” ON, BaseColor is not required.
- TIFF loading issues in Designer (FreeImage): If you see failures, re‑export textures as 24‑bit TIFF (no BigTIFF). The add‑on prints a helpful hint in Blender’s console/logs.
- “Save your .blend file first!”: Many operations mirror to a Release folder next to the .blend; unsaved files block the pipeline.

## Operator IDs (for scripting)

- Generate LODs: `vivid.setup_lods`
- Generate LOD Cages: `vivid.generate_lod_cages`
- Bake LOD Textures: `vivid.bake_lod_textures`

## Credits and licenses

See source headers and bundled resources under `vivid_arts_toolbox/resources`.
