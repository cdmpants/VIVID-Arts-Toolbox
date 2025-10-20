import bpy, json, os, datetime
from bpy.types import PropertyGroup, Operator
from bpy.props import (
    StringProperty,
    EnumProperty,
    PointerProperty,
    CollectionProperty,
    IntProperty,
)

def _blend_dir():
    return bpy.path.abspath("//")

def _blend_basename_noext():
    p = bpy.data.filepath
    if not p:
        return "untitled"
    return os.path.splitext(os.path.basename(p))[0]

def _load_options():
    try:
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        pkg_dir = os.path.dirname(__file__)
    path = os.path.join(pkg_dir, "MetadataOptions.json")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

# Cache options on import/registration
_OPTIONS = _load_options()


class VIVID_Metadata(PropertyGroup):
    pass


class VIVID_LabelItem(PropertyGroup):
    # Properties are defined at register() time to avoid static typing issues
    pass


def _label_items_cb(self, context):
    labels = _OPTIONS.get('Labels', [])
    if not labels:
        labels = ["unspecified"]
    return [(l, l, "") for l in labels]


class VIVID_OT_label_add(Operator):
    bl_idname = "vivid.label_add"
    bl_label = "Add Label"

    def execute(self, context):
        s = getattr(context.scene, 'vivid_metadata', None)
        if not s:
            self.report({'ERROR'}, 'Metadata settings missing')
            return {'CANCELLED'}
        it = s.labels_coll.add()
        # Default to first option
        try:
            first = _OPTIONS.get('Labels', [])
            it.value = first[0] if first else 'unspecified'
        except Exception:
            it.value = 'unspecified'
        s.labels_index = len(s.labels_coll) - 1
        return {'FINISHED'}


class VIVID_OT_label_remove(Operator):
    bl_idname = "vivid.label_remove"
    bl_label = "Remove Label"

    def execute(self, context):
        s = getattr(context.scene, 'vivid_metadata', None)
        if not s:
            self.report({'ERROR'}, 'Metadata settings missing')
            return {'CANCELLED'}
        idx = getattr(s, 'labels_index', -1)
        if 0 <= idx < len(s.labels_coll):
            s.labels_coll.remove(idx)
            s.labels_index = min(idx, len(s.labels_coll) - 1)
        return {'FINISHED'}


def _collect_dimensions(context, asset_type: str):
    dims = {}
    if asset_type == 'Model':
        # Priority: Cinema, Optimized, LOD0
        candidates = ['Cinema', 'Optimized', 'LOD0']
        for name in candidates:
            obj = bpy.data.objects.get(name) or next((o for o in bpy.data.objects if o.name.endswith(f"_{name}")), None)
            if obj and obj.type == 'MESH':
                bb = obj.dimensions
                dims = {"X": round(float(bb.x), 4), "Y": round(float(bb.y), 4), "Z": round(float(bb.z), 4)}
                break
        if not dims:
            dims = "Unknown"
    else:
        # Surface: take from Scene controls
        sx = getattr(context.scene, 'vivid_surface_dim_x', 0.0)
        sy = getattr(context.scene, 'vivid_surface_dim_y', 0.0)
        dims = {"X": round(float(sx), 4), "Y": round(float(sy), 4)}
    return dims


class VIVID_OT_export_metadata_json(Operator):
    bl_idname = "vivid.export_metadata_json"
    bl_label = "Export Metadata JSON"

    def execute(self, context):
        s = getattr(context.scene, 'vivid_metadata', None)
        if not s:
            self.report({'ERROR'}, 'Metadata settings missing')
            return {'CANCELLED'}
        base = _blend_basename_noext()
        out_dir = _blend_dir()
        out_path = os.path.join(out_dir, f"{base}_meta.json")

        now = datetime.datetime.now().strftime('%Y-%m-%d')
        data = {
            "Main": {
                "AssetID": s.asset_id or base,
                "DisplayName": s.display_name or base,
                "AssetType": s.asset_type,
                "Biome": s.biome,
                "Country": s.country,
                "Region": s.region,
                "Location": s.location,
                "Category": s.category,
                "Dimensions": _collect_dimensions(context, s.asset_type),
                "Size": s.size,
                "Date Captured": s.date_captured or "Unknown",
                "Last Updated": now,
                "Version": s.version or "1.0",
            },
            "Polycounts": {
                "Cinema": s.poly_cinema or None,
                "LOD0": s.poly_lod0 or None,
                "LOD1": s.poly_lod1 or None,
                "LOD2": s.poly_lod2 or None,
                "LOD3": s.poly_lod3 or None,
            },
            "Source": {
                "Source Name": s.source_name or "",
                "Capture Device": s.capture_device,
                "Notes": s.source_notes or "",
            },
            "Importer": {
                "Allow UDIM Merge": s.importer_allow_udim_merge,
                "Allow Tessellation": s.importer_allow_tessellation,
                "Has Collision": s.importer_has_collision,
                "Static": s.importer_static,
            },
            "Labels": ([it.value for it in s.labels_coll] if getattr(s, 'labels_coll', None) and len(s.labels_coll) > 0 else [lbl.strip() for lbl in (s.labels or '').split(',') if lbl.strip()]),
            # "Textures": to be filled later
        }

        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.report({'ERROR'}, f'Failed to write JSON: {e}')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Exported metadata: {out_path}')
        return {'FINISHED'}


class VIVID_OT_reload_local_json(Operator):
    bl_idname = "vivid.reload_local_json"
    bl_label = "Reload Local JSON"

    def execute(self, context):
        base = _blend_basename_noext()
        in_path = os.path.join(_blend_dir(), f"{base}_meta.json")
        try:
            with open(in_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f'Failed to read JSON: {e}')
            return {'CANCELLED'}
        s = getattr(context.scene, 'vivid_metadata', None)
        if not s:
            self.report({'ERROR'}, 'Metadata settings missing')
            return {'CANCELLED'}
        try:
            m = data.get('Main', {})
            s.asset_id = m.get('AssetID', '')
            s.display_name = m.get('DisplayName', '')
            s.asset_type = m.get('AssetType', 'Model')
            s.biome = m.get('Biome', 'Katlahraun')
            s.country = m.get('Country', 'Iceland')
            s.region = m.get('Region', 'Reykjanes')
            s.location = m.get('Location', 'Katlahraun')
            s.category = m.get('Category', 'Rock')
            s.size = m.get('Size', 'Medium')
            s.date_captured = m.get('Date Captured', '')
            s.version = m.get('Version', '1.0')
            p = data.get('Polycounts', {})
            s.poly_cinema = str(p.get('Cinema', '') or '')
            s.poly_lod0 = str(p.get('LOD0', '') or '')
            s.poly_lod1 = str(p.get('LOD1', '') or '')
            s.poly_lod2 = str(p.get('LOD2', '') or '')
            s.poly_lod3 = str(p.get('LOD3', '') or '')
            sc = data.get('Source', {})
            s.source_name = sc.get('Source Name', '')
            s.capture_device = sc.get('Capture Device', 'Nikon D5500')
            s.source_notes = sc.get('Notes', '')
            imp = data.get('Importer', {})
            s.importer_allow_udim_merge = 'True' if imp.get('Allow UDIM Merge', 'True') == True or imp.get('Allow UDIM Merge', 'True') == 'True' else 'False'
            s.importer_allow_tessellation = 'True' if imp.get('Allow Tessellation', 'True') == True or imp.get('Allow Tessellation', 'True') == 'True' else 'False'
            s.importer_has_collision = 'True' if imp.get('Has Collision', 'True') == True or imp.get('Has Collision', 'True') == 'True' else 'False'
            s.importer_static = 'True' if imp.get('Static', 'True') == True or imp.get('Static', 'True') == 'True' else 'False'
            lbls = data.get('Labels', [])
            # Populate both the collection and the legacy string for compatibility
            try:
                s.labels_coll.clear()
                for v in lbls:
                    it = s.labels_coll.add()
                    it.value = str(v)
            except Exception:
                pass
            s.labels = ", ".join([str(x) for x in lbls])
        except Exception as e:
            self.report({'ERROR'}, f'Failed to load into UI: {e}')
            return {'CANCELLED'}
        self.report({'INFO'}, 'Reloaded metadata from local JSON')
        return {'FINISHED'}


class VIVID_OT_load_reference_json(Operator):
    bl_idname = "vivid.load_reference_json"
    bl_label = "Load Reference JSON"

    def execute(self, context):
        p = getattr(context.scene, 'vivid_metadata_reference_path', '')
        if not p:
            self.report({'ERROR'}, 'No reference file selected')
            return {'CANCELLED'}
        try:
            with open(bpy.path.abspath(p), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f'Failed to read reference: {e}')
            return {'CANCELLED'}
        s = getattr(context.scene, 'vivid_metadata', None)
        if not s:
            self.report({'ERROR'}, 'Metadata settings missing')
            return {'CANCELLED'}
        try:
            m = data.get('Main', {})
            s.display_name = m.get('DisplayName', s.display_name)
            s.biome = m.get('Biome', s.biome)
            s.country = m.get('Country', s.country)
            s.region = m.get('Region', s.region)
            s.location = m.get('Location', s.location)
            s.category = m.get('Category', s.category)
            s.size = m.get('Size', s.size)
            s.date_captured = m.get('Date Captured', s.date_captured)
            s.version = m.get('Version', s.version)
            sc = data.get('Source', {})
            s.source_name = sc.get('Source Name', s.source_name)
            s.capture_device = sc.get('Capture Device', s.capture_device)
            s.source_notes = sc.get('Notes', s.source_notes)
            imp = data.get('Importer', {})
            def coerce_tf(val, cur):
                return 'True' if (val == True or val == 'True') else ('False' if (val == False or val == 'False') else cur)
            s.importer_allow_udim_merge = coerce_tf(imp.get('Allow UDIM Merge', s.importer_allow_udim_merge), s.importer_allow_udim_merge)
            s.importer_allow_tessellation = coerce_tf(imp.get('Allow Tessellation', s.importer_allow_tessellation), s.importer_allow_tessellation)
            s.importer_has_collision = coerce_tf(imp.get('Has Collision', s.importer_has_collision), s.importer_has_collision)
            s.importer_static = coerce_tf(imp.get('Static', s.importer_static), s.importer_static)
            lbls = data.get('Labels', [])
            if isinstance(lbls, list):
                try:
                    s.labels_coll.clear()
                    for v in lbls:
                        it = s.labels_coll.add()
                        it.value = str(v)
                except Exception:
                    pass
                s.labels = ", ".join([str(x) for x in lbls])
        except Exception as e:
            self.report({'ERROR'}, f'Failed to apply reference: {e}')
            return {'CANCELLED'}
        self.report({'INFO'}, 'Loaded reference values (non-destructive)')
        return {'FINISHED'}


CLASSES = (
    VIVID_Metadata,
    VIVID_LabelItem,
    VIVID_OT_label_add,
    VIVID_OT_label_remove,
    VIVID_OT_export_metadata_json,
    VIVID_OT_reload_local_json,
    VIVID_OT_load_reference_json,
)

def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    # Define properties dynamically to avoid static typing false-positives
    VIVID_Metadata.asset_id = StringProperty(name="AssetID", description="Auto-filled from folder name")
    VIVID_Metadata.display_name = StringProperty(name="DisplayName")
    VIVID_Metadata.asset_type = EnumProperty(name="AssetType", items=[('Model','Model',''),('Surface','Surface','')], default='Model')
    # Build items lists from _OPTIONS with sensible fallbacks
    def _items_from(opt_key, fallbacks):
        seq = _OPTIONS.get(opt_key, fallbacks)
        if not seq:
            seq = fallbacks
        return [(v, v, "") for v in seq]
    VIVID_Metadata.biome = EnumProperty(name="Biome", items=_items_from('Biome', ['Katlahraun','Kleifarvatn']), default=_OPTIONS.get('Biome', ['Katlahraun'])[0] if _OPTIONS.get('Biome') else 'Katlahraun')
    VIVID_Metadata.country = EnumProperty(name="Country", items=_items_from('Country', ['Iceland','United States']), default=_OPTIONS.get('Country', ['Iceland'])[0] if _OPTIONS.get('Country') else 'Iceland')
    VIVID_Metadata.region = EnumProperty(name="Region", items=_items_from('Region', ['Reykjanes','Pennsylvania']), default=_OPTIONS.get('Region', ['Reykjanes'])[0] if _OPTIONS.get('Region') else 'Reykjanes')
    VIVID_Metadata.location = EnumProperty(name="Location", items=_items_from('Location', ['Katlahraun','Lancaster']), default=_OPTIONS.get('Location', ['Katlahraun'])[0] if _OPTIONS.get('Location') else 'Katlahraun')
    VIVID_Metadata.category = EnumProperty(name="Category", items=_items_from('Category', ['Rock','Concrete']), default=_OPTIONS.get('Category', ['Rock'])[0] if _OPTIONS.get('Category') else 'Rock')
    VIVID_Metadata.size = EnumProperty(name="Size", items=_items_from('Size', ['Tiny','Small','Medium','Big','Huge','Massive']), default=_OPTIONS.get('Size', ['Medium'])[0] if _OPTIONS.get('Size') else 'Medium')
    VIVID_Metadata.date_captured = StringProperty(name="Date Captured")
    VIVID_Metadata.version = StringProperty(name="Version", description="Version string", default="1.0")

    VIVID_Metadata.poly_cinema = StringProperty(name="Cinema")
    VIVID_Metadata.poly_lod0 = StringProperty(name="LOD0")
    VIVID_Metadata.poly_lod1 = StringProperty(name="LOD1")
    VIVID_Metadata.poly_lod2 = StringProperty(name="LOD2")
    VIVID_Metadata.poly_lod3 = StringProperty(name="LOD3")

    VIVID_Metadata.source_name = StringProperty(name="Source Name")
    VIVID_Metadata.capture_device = EnumProperty(name="Capture Device", items=_items_from('CaptureDevice', ['Nikon D5500','DJI Air 3']), default=_OPTIONS.get('CaptureDevice', ['DJI Air 3'])[0] if _OPTIONS.get('CaptureDevice') else 'DJI Air 3')
    VIVID_Metadata.source_notes = StringProperty(name="Notes")

    VIVID_Metadata.importer_allow_udim_merge = EnumProperty(name="Allow UDIM Merge", items=[('True','True',''),('False','False','')], default='True')
    VIVID_Metadata.importer_allow_tessellation = EnumProperty(name="Allow Tessellation", items=[('True','True',''),('False','False','')], default='True')
    VIVID_Metadata.importer_has_collision = EnumProperty(name="Has Collision", items=[('True','True',''),('False','False','')], default='True')
    VIVID_Metadata.importer_static = EnumProperty(name="Static", items=[('True','True',''),('False','False','')], default='True')

    # Labels: new collection-based UI; keep legacy string for backward compatibility/older JSONs
    VIVID_Metadata.labels = StringProperty(name="Labels", description="Comma-separated labels (legacy)")
    VIVID_Metadata.labels_coll = CollectionProperty(type=VIVID_LabelItem, name="Labels")
    VIVID_Metadata.labels_index = IntProperty(name="Label Index", default=-1)
    # Define label item properties now that class is registered
    VIVID_LabelItem.value = EnumProperty(name="Label", items=_label_items_cb)

    bpy.types.Scene.vivid_metadata = PointerProperty(type=VIVID_Metadata)
    # Autofill AssetID from parent folder (fallback to blend filename) when available
    def _ensure_asset_id(scene):
        try:
            s = getattr(scene, 'vivid_metadata', None)
            if not s:
                return
            fp = bpy.data.filepath
            base_noext = "untitled"
            if fp:
                # Prefer parent folder name
                try:
                    parent = os.path.basename(os.path.dirname(fp))
                    if parent:
                        base_noext = parent
                    else:
                        base = bpy.path.basename(fp)
                        base_noext = os.path.splitext(base)[0] if base else "untitled"
                except Exception:
                    base = bpy.path.basename(fp)
                    base_noext = os.path.splitext(base)[0] if base else "untitled"
            if not s.asset_id:
                s.asset_id = base_noext
        except Exception:
            pass
    def _on_load_post(dummy):
        for sc in bpy.data.scenes:
            _ensure_asset_id(sc)
    def _on_save_post(dummy):
        for sc in bpy.data.scenes:
            _ensure_asset_id(sc)
    try:
        bpy.app.handlers.load_post.append(_on_load_post)
    except Exception:
        pass
    try:
        bpy.app.handlers.save_post.append(_on_save_post)
    except Exception:
        pass

def unregister():
    if hasattr(bpy.types.Scene, 'vivid_metadata'):
        del bpy.types.Scene.vivid_metadata
    # Remove our handlers if present
    try:
        bpy.app.handlers.load_post = [h for h in bpy.app.handlers.load_post if getattr(h, '__name__', '') != '_on_load_post']
    except Exception:
        pass
    try:
        bpy.app.handlers.save_post = [h for h in bpy.app.handlers.save_post if getattr(h, '__name__', '') != '_on_save_post']
    except Exception:
        pass
    for c in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
