# vivid_arts_toolbox/operators/shadowproxy_correction.py

bl_info = {
    "name": "VIVID • Shadow Proxy Correction",
    "author": "Christopher Fantauzzo + ChatGPT",
    "version": (1, 8, 0),
    "blender": (4, 3, 0),
    "location": "3D Viewport > Sidebar (N) > VIVID Arts Toolbox > ShadowProxy Correction",
    "description": "Fits ShadowProxy meshes inside their LODs. Applies Decimate, dense sampling, multi-pass, vertex cleanup. Tokenized+tolerant name pairing with diagnostics. Includes Max Push limit.",
    "category": "Object",
}

import bpy, bmesh, re
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy.props import (
    BoolProperty, FloatProperty, IntProperty, StringProperty
)

# =========================================================
# Core helpers
# =========================================================

def _to_world_point(M, p): return M @ p
def _to_world_normal(M, n): return (M.to_3x3().inverted().transposed() @ n).normalized()

def _build_bvh_from_evaluated(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    eobj = obj.evaluated_get(dg)
    emesh = eobj.to_mesh()
    bm = bmesh.new(); bm.from_mesh(emesh); bm.normal_update()
    bvh = BVHTree.FromBMesh(bm)
    bm.free(); eobj.to_mesh_clear()
    return bvh

def _tri_fan(verts):
    if len(verts) < 3: return []
    a = verts[0]; return [(a, verts[i], verts[i+1]) for i in range(1, len(verts)-1)]

def _face_samples_dense(face, grid=3, edge_samples=0):
    pts, verts = [], [v.co.copy() for v in face.verts]
    if verts: pts.append(sum(verts, Vector()) / len(verts))
    tris = _tri_fan(verts); k = max(1, int(grid))
    for a,b,c in tris:
        for i in range(k):
            for j in range(k-i):
                u=(i+0.5)/k; v=(j+0.5)/k; w=1.0-u-v
                pts.append(a*w+b*u+c*v)
    if edge_samples and len(verts)>=2:
        n=len(verts)
        for i in range(n):
            p0,p1=verts[i],verts[(i+1)%n]
            for t in range(edge_samples):
                pts.append(p0.lerp(p1,(t+0.5)/edge_samples))
    return pts

def _solve_face_move(samples_world, n_face_in_world, bvh, margin):
    # Nearest-normal signed offset; adaptive inward direction
    outside=[]
    for pw in samples_world:
        loc,normal,_,_=bvh.find_nearest(pw)
        if not loc or not normal: continue
        s=(pw-loc).dot(normal)
        if s>-margin: outside.append((s,normal))
    if not outside: return None
    dir_world, max_need = Vector((0,0,0)), 0.0
    for (s,n_base) in outside:
        dir_world+=(-n_base); max_need=max(max_need,s+margin)
    if dir_world.length_squared==0: return None
    dir_world.normalize(); return dir_world*max_need

def _clamp_move(move_world: Vector, max_push: float) -> Vector:
    if max_push is None or max_push <= 0.0:
        return move_world
    length = move_world.length
    if length <= max_push or length == 0.0:
        return move_world
    return move_world.normalized() * max_push

def _vertex_fixup(shadow_obj, bvh, *, margin=0.003, v_passes=2, max_push=0.02):
    me=shadow_obj.data; bm=bmesh.new(); bm.from_mesh(me)
    bm.verts.ensure_lookup_table(); bm.normal_update()
    Ms=shadow_obj.matrix_world; Ms_inv=Ms.inverted()
    total=0
    for _ in range(v_passes):
        moved=0; bm.normal_update()
        for v in bm.verts:
            pw=Ms@v.co
            # inward is opposite of transformed vertex normal
            n_in=-(Ms.to_3x3().inverted().transposed()@v.normal).normalized()
            loc,normal,_,_=bvh.find_nearest(pw)
            if not loc or not normal: continue
            s=(pw-loc).dot(normal)
            if s<=-margin: continue
            need=s+margin
            # Prefer vertex inward if it helps, else base inward
            align = n_in.dot(normal)
            if align > 1e-4:
                move_world = n_in * (need / align)
            else:
                move_world = (-normal).normalized() * need
            move_world = _clamp_move(move_world, max_push)
            v.co=Ms_inv@(pw+move_world); moved+=1
        if not moved: break
        total+=moved; bm.normal_update()
    if total: bm.to_mesh(me); me.update()
    bm.free(); return total

def _apply_decimate_mods(obj):
    # Apply all Decimate modifiers before correction
    for mod in [m for m in obj.modifiers if m.type=="DECIMATE"]:
        print(f"[ShadowProxyFit] Applying Decimate modifier on {obj.name}: {mod.name}")
        bpy.context.view_layer.objects.active=obj
        try: bpy.ops.object.modifier_apply(modifier=mod.name)
        except Exception as e:
            print(f"[ShadowProxyFit] WARN: Could not apply {mod.name} on {obj.name}: {e}")

def _process_pair(shadow_obj,lod_obj,*,margin=0.003,grid=5,edge_samples=4,passes=2,v_passes=2,max_push=0.02):
    _apply_decimate_mods(shadow_obj)
    print(f"[ShadowProxyFit] Processing: {shadow_obj.name}  ->  {lod_obj.name}")
    bvh=_build_bvh_from_evaluated(lod_obj)

    me=shadow_obj.data; bm=bmesh.new(); bm.from_mesh(me)
    bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table(); bm.normal_update()
    Ms,Ms_inv=shadow_obj.matrix_world,shadow_obj.matrix_world.inverted()
    moved_faces=0

    for _ in range(passes):
        moved_this=0
        for face in bm.faces:
            n_face_in_world=-_to_world_normal(Ms,face.normal)
            samples_world=[_to_world_point(Ms,q) for q in _face_samples_dense(face,grid,edge_samples)]
            move_world=_solve_face_move(samples_world,n_face_in_world,bvh,margin)
            if not move_world: continue
            move_world = _clamp_move(move_world, max_push)
            if move_world.length == 0.0:
                continue
            for v in face.verts:
                v.co=Ms_inv@((_to_world_point(Ms,v.co))+move_world)
            moved_this+=1
        if moved_this: moved_faces+=moved_this; bm.normal_update()
        if not moved_this: break

    if moved_faces: bm.to_mesh(me); me.update()
    bm.free()

    moved_verts=_vertex_fixup(shadow_obj,bvh,margin=margin,v_passes=v_passes,max_push=max_push)
    print(f"[ShadowProxyFit] Faces moved: {moved_faces}; Vertices moved: {moved_verts}")
    return moved_faces+moved_verts

# =========================================================
# Pair finding (proxy-priority tolerant)
# =========================================================

def _norm_name(s): return re.sub(r"\.\d+$","",s).strip()
def _split_digits_at_end(text):
    i=len(text)-1
    while i>=0 and text[i].isdigit(): i-=1
    if i==len(text)-1: return text,None
    return text[:i+1],text[i+1:]

def find_pairs(verbose=False):
    sc=bpy.context.scene; LOD=getattr(sc,"sp_token_lod","LOD"); PROXY=getattr(sc,"sp_token_proxy","ShadowProxy")
    lod_rx=re.compile(rf"^(.+?)_{re.escape(LOD)}(\d+)$",re.IGNORECASE)
    prox_infx=re.compile(rf"^(.+?)_{re.escape(PROXY)}_{re.escape(LOD)}(\d+)$",re.IGNORECASE)
    prox_pfx=re.compile(rf"^{re.escape(PROXY)}_(.+?)_{re.escape(LOD)}(\d+)$",re.IGNORECASE)
    LOD_lower,PROXY_lower=LOD.lower(),PROXY.lower()

    def parse_proxy_tolerant(name):
        low=name.lower(); idx=low.rfind("_"+LOD_lower)
        if idx==-1: return None
        tail=name[idx+1:]; prefix, digits=_split_digits_at_end(tail)
        if not digits or prefix.lower()!=LOD_lower: return None
        left=name[:idx]; low_left=left.lower()
        if low_left.startswith(PROXY_lower+"_"):
            base=left[len(PROXY):]
            return (_norm_name(base.lstrip("_")),digits)
        pos=low_left.rfind("_"+PROXY_lower)
        if pos!=-1:
            return (_norm_name(left[:pos]),digits)
        return None

    lod_map, proxies = {}, []
    for obj in bpy.data.objects:
        if obj.type!="MESH":
            continue
        name=_norm_name(obj.name); low=name.lower()

        # Prioritize proxy classification
        if PROXY_lower in low:
            m=prox_infx.match(name)
            if m:
                base,lod=_norm_name(m.group(1)),m.group(2); proxies.append((base,lod,obj))
                continue
            m=prox_pfx.match(name)
            if m:
                base,lod=_norm_name(m.group(1)),m.group(2); proxies.append((base,lod,obj))
                continue
            tol=parse_proxy_tolerant(name)
            if tol:
                base,lod=tol; proxies.append((base,lod,obj))
                continue
            continue

        m=lod_rx.match(name)
        if m:
            base,lod=_norm_name(m.group(1)),m.group(2); lod_map[(base,lod)]=obj
            continue

    pairs=[]
    for base,lod,shp in proxies:
        lod_obj=lod_map.get((base,lod))
        if lod_obj:
            pairs.append((shp,lod_obj))
        else:
            print(f"[ShadowProxyFit] WARN: No matching LOD for '{shp.name}' (expected '{base}_{LOD}{lod}')")

    print(f"[ShadowProxyFit] Pairs found: {len(pairs)}")
    for shp,lod in pairs: print(f"  - {shp.name} -> {lod.name}")
    return pairs

# =========================================================
# Operators
# =========================================================

class OBJECT_OT_shadowproxy_fit_all_pairs(bpy.types.Operator):
    """Fit all ShadowProxy meshes inside their matching LODs (by name)."""
    bl_idname="object.shadowproxy_fit_all_pairs"
    bl_label="Fit Shadow Proxies"
    bl_options={'REGISTER','UNDO'}

    margin:FloatProperty(name="Inside Margin",default=0.003,min=0.0,soft_max=0.05)
    grid:IntProperty(name="Grid Samples",default=5,min=1,max=12)
    edge_samples:IntProperty(name="Edge Samples",default=4,min=0,max=24)
    passes:IntProperty(name="Face Passes",default=2,min=1,max=10)
    v_passes:IntProperty(name="Vertex Passes",default=2,min=1,max=10)
    max_push:FloatProperty(name="Max Push",default=0.02,min=0.0,soft_max=0.1,description="Max distance (meters) any face/vertex can move per step. Set 0 to disable.")
    only_selected:BoolProperty(name="Only Selected ShadowProxies",default=False)

    def execute(self,context):
        bpy.ops.object.mode_set(mode='OBJECT',toggle=False)
        pairs=find_pairs()
        if not pairs:
            self.report({'WARNING'},"No ShadowProxy/LOD pairs found.")
            return {'CANCELLED'}
        sel_names={o.name for o in context.selected_objects} if self.only_selected else None
        total,processed=0,0
        for shp,lod in pairs:
            if sel_names and shp.name not in sel_names: continue
            total+=_process_pair(
                shp,lod,
                margin=self.margin,grid=self.grid,edge_samples=self.edge_samples,
                passes=self.passes,v_passes=self.v_passes,max_push=self.max_push
            )
            processed+=1
        self.report({'INFO'},f"Processed {processed} proxies; moved {total} elements.")
        return {'FINISHED'}

class OBJECT_OT_shadowproxy_list_pairs(bpy.types.Operator):
    bl_idname="object.shadowproxy_list_pairs"
    bl_label="List Pairs"; bl_options={'INTERNAL'}
    def execute(self,context):
        find_pairs(verbose=True)
        return {'FINISHED'}

# =========================================================
# Panel (now under the same tab + parent as other foldouts)
# =========================================================

class VIEW3D_PT_shadowproxy_correction(bpy.types.Panel):
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category  = "VIVID Arts Toolbox"   # SAME TAB as others
    bl_parent_id = "VIVID_PT_main_panel"  # CHILD FOLDOUT under main toolbox panel
    bl_label     = "ShadowProxy Correction"
    bl_options   = {'DEFAULT_CLOSED'}
    bl_order     = 40                      # Above Export Asset (which is 50)

    def draw(self,context):
        s=context.scene; layout=self.layout
        box=layout.box(); box.label(text="Solve Settings",icon='MOD_SHRINKWRAP')
        box.prop(s,"sp_margin")
        box.prop(s,"sp_grid")
        box.prop(s,"sp_edge_samples")
        row = box.row(align=True)
        row.prop(s,"sp_passes")
        row.prop(s,"sp_v_passes")
        box.prop(s,"sp_max_push")
        row=box.row(align=True); row.prop(s,"sp_token_lod"); row.prop(s,"sp_token_proxy")

        layout.separator()
        col=layout.column(align=True)
        op=col.operator(OBJECT_OT_shadowproxy_fit_all_pairs.bl_idname,text="Fit Shadow Proxies",icon='MOD_SHRINKWRAP')
        op.margin=s.sp_margin; op.grid=s.sp_grid; op.edge_samples=s.sp_edge_samples
        op.passes=s.sp_passes; op.v_passes=s.sp_v_passes; op.max_push=s.sp_max_push
        op.only_selected=s.sp_only_selected_pairs
        col.prop(s,"sp_only_selected_pairs")
        col.operator(OBJECT_OT_shadowproxy_list_pairs.bl_idname,text="List Pairs",icon='INFO')

# =========================================================
# Scene props
# =========================================================

def _ensure_scene_props():
    sc=bpy.types.Scene
    if not hasattr(sc,"sp_margin"): sc.sp_margin=FloatProperty(name="Inside Margin",default=0.003,min=0.0,soft_max=0.05)
    if not hasattr(sc,"sp_grid"): sc.sp_grid=IntProperty(name="Grid Samples",default=5,min=1,max=12)
    if not hasattr(sc,"sp_edge_samples"): sc.sp_edge_samples=IntProperty(name="Edge Samples",default=4,min=0,max=24)
    if not hasattr(sc,"sp_passes"): sc.sp_passes=IntProperty(name="Face Passes",default=2,min=1,max=10)
    if not hasattr(sc,"sp_v_passes"): sc.sp_v_passes=IntProperty(name="Vertex Passes",default=2,min=1,max=10)
    if not hasattr(sc,"sp_max_push"): sc.sp_max_push=FloatProperty(name="Max Push",default=0.02,min=0.0,soft_max=0.1,description="Max distance (meters) any face/vertex can move per step. Set 0 to disable.")
    if not hasattr(sc,"sp_only_selected_pairs"): sc.sp_only_selected_pairs=BoolProperty(name="Only Selected ShadowProxies",default=False)
    if not hasattr(sc,"sp_token_lod"): sc.sp_token_lod=StringProperty(name="LOD Token",default="LOD")
    if not hasattr(sc,"sp_token_proxy"): sc.sp_token_proxy=StringProperty(name="Proxy Token",default="ShadowProxy")

# =========================================================
# Register
# =========================================================

_classes=(OBJECT_OT_shadowproxy_fit_all_pairs,OBJECT_OT_shadowproxy_list_pairs,VIEW3D_PT_shadowproxy_correction)

def register():
    for c in _classes:
        bpy.utils.register_class(c)
    _ensure_scene_props()

def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)

if __name__=="__main__":
    register()

