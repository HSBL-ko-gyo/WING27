#!/usr/bin/python3
"""Import the original P2 SVG boundary geometry on KiCad User.1, at 1:1.

The SVG is a top-left-origin front view, while the 60-key CSV uses bottom-left
coordinates. Thus SVG (u,v) -> PCB (20+u,20+v) mm, equivalent to the locked CSV
mapping (x,y) -> PCB (20+x,78-y). No geometry is inferred from the switch array.
The opaque print cross remains at source (103,29); the panel centre is (104,29).

Import deliberately uses unfilled boundaries on a non-fabrication layer: KiCad
user layers cannot reproduce the SVG's black/white/gray printing semantics.
Every existing M/L/H/V/Z boundary vertex is preserved (no resampling; only
zero-length consecutive duplicates are omitted by KiCad), including
legend holes. Rounded key rectangles become four lines and four native arcs.
The source artwork's sampled R2 panel boundary stays as supplied; it is never
promoted to Edge.Cuts. Unsupported SVG geometry is rejected, not approximated.

Integration: report = import_panel_svg(board)
CLI (audit only unless --output is given):
  /usr/bin/python3 scripts/import_panel_svg.py --board WING27.kicad_pcb \
      --output /tmp/WING27-overlay.kicad_pcb --report validation/panel_svg.json \
      --overlay /tmp/WING27-overlay.svg
Only the named import group is replaced, so unrelated User.1 content survives.
"""
from __future__ import annotations

import argparse
import copy
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "reference" / "P2"
APPEARANCE = "01_APPEARANCE_REFERENCE.svg"
BOUNDARIES = "05_EMBOSS_KEY_BOUNDARIES_REFERENCE.svg"
PROVISIONAL = "06_OUTER_CUT_PROVISIONAL.svg"
CSV_FILE = "Wing27_P2_60_key_center_coordinates_mm.csv"
LAYOUT_FILE = "key_layout_P2.json"
GROUP_NAME = "P2_SOURCE_SVG_1_TO_1_REFERENCE_ONLY"
NAMESPACE = uuid.UUID("be0c37a5-c4dc-526b-aef5-80e00a94da6b")
IDENTITY = (1., 0., 0., 1., 0., 0.)
NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def matmul(a, b):
    """SVG affine composition a(b(point))."""
    x, y, z, w, u, v = a
    A, B, C, D, E, F = b
    return (x*A+z*B, y*A+w*B, x*C+z*D, y*C+w*D,
            x*E+z*F+u, y*E+w*F+v)


def apply(m, p):
    x, y = p
    a, b, c, d, e, f = m
    return (a*x+c*y+e, b*x+d*y+f)


def numbers(text):
    tokens = re.findall(NUMBER, text)
    if re.sub(NUMBER, "", text).strip(" ,\t\r\n"):
        raise ValueError(f"Malformed SVG numbers: {text[:100]}")
    return [float(t) for t in tokens]


def transform(text):
    result = IDENTITY
    remaining = re.sub(r"([A-Za-z]+)\s*\(([^)]*)\)", "", text)
    if remaining.strip(" ,\t\r\n"):
        raise ValueError(f"Malformed transform: {text}")
    for name, args in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", text):
        n = numbers(args)
        if name == "matrix" and len(n) == 6:
            op = tuple(n)
        elif name == "translate" and len(n) in (1, 2):
            op = (1, 0, 0, 1, n[0], n[1] if len(n) == 2 else 0)
        elif name == "scale" and len(n) in (1, 2):
            op = (n[0], 0, 0, n[-1], 0, 0)
        elif name == "rotate" and len(n) in (1, 3):
            c, s = math.cos(math.radians(n[0])), math.sin(math.radians(n[0]))
            op = (c, s, -s, c, 0, 0)
            if len(n) == 3:
                op = matmul(matmul((1, 0, 0, 1, n[1], n[2]), op),
                            (1, 0, 0, 1, -n[1], -n[2]))
        elif name in ("skewX", "skewY") and len(n) == 1:
            t = math.tan(math.radians(n[0]))
            op = (1, 0, t, 1, 0, 0) if name == "skewX" else (1, t, 0, 1, 0, 0)
        else:
            raise ValueError(f"Unsupported transform: {name}({args})")
        result = matmul(result, op)
    return result


def length_mm(value):
    match = re.fullmatch(rf"\s*({NUMBER})\s*(mm|cm|in|pt|pc|px)?\s*", value)
    if not match:
        raise ValueError(f"Unsupported physical SVG length: {value}")
    scale = {"mm": 1, "cm": 10, "in": 25.4, "pt": 25.4/72,
             "pc": 25.4/6, "px": 25.4/96, None: 25.4/96}
    return float(match[1])*scale[match[2]]


def viewport(root):
    width, height = length_mm(root.attrib["width"]), length_mm(root.attrib["height"])
    v = numbers(root.attrib.get("viewBox", f"0 0 {width*96/25.4} {height*96/25.4}"))
    if len(v) != 4 or min(v[2:]) <= 0 or min(width, height) <= 0:
        raise ValueError("SVG viewBox/physical size must be positive")
    x, y, w, h = v
    sx, sy = width/w, height/h
    par = root.get("preserveAspectRatio", "xMidYMid meet").split()
    if par[0] == "defer":
        par = par[1:]
    if par[0] == "none":
        tx, ty = 0, 0
    else:
        if not re.fullmatch(r"x(Min|Mid|Max)Y(Min|Mid|Max)", par[0]):
            raise ValueError(f"Unsupported preserveAspectRatio: {par}")
        mode = par[1] if len(par) > 1 else "meet"
        if mode not in ("meet", "slice"):
            raise ValueError(f"Unsupported preserveAspectRatio: {par}")
        sx = sy = min(sx, sy) if mode == "meet" else max(sx, sy)
        weight = {"Min": 0, "Mid": .5, "Max": 1}
        tx, ty = (width-w*sx)*weight[par[0][1:4]], (height-h*sy)*weight[par[0][5:8]]
    return (width, height), (sx, 0, 0, sy, tx-x*sx, ty-y*sy)


def path_contours(data):
    """Parse original linear path commands; reject curves instead of flattening."""
    tokens = re.findall(rf"[A-Za-z]|{NUMBER}", data)
    if re.sub(rf"[A-Za-z]|{NUMBER}", "", data).strip(" ,\t\r\n"):
        raise ValueError("Malformed SVG path")
    contours, points, cursor, start = [], [], (0., 0.), None
    i, command = 0, None
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
        if command is None or command.upper() not in "MLHVZ":
            raise ValueError(f"Unsupported SVG command {command}; source must be preserved")
        upper, relative = command.upper(), command.islower()
        if upper == "Z":
            if not points:
                raise ValueError("Close without a path")
            if points[-1] == points[0]:
                points.pop()
            contours.append((points, True))
            points, cursor, command = [], start, None
            continue
        count = 1 if upper in "HV" else 2
        if i+count > len(tokens) or any(t.isalpha() for t in tokens[i:i+count]):
            raise ValueError(f"Missing coordinates for {command}")
        n = list(map(float, tokens[i:i+count]))
        i += count
        if upper in "ML":
            p = (n[0]+(cursor[0] if relative else 0), n[1]+(cursor[1] if relative else 0))
        elif upper == "H":
            p = (n[0]+(cursor[0] if relative else 0), cursor[1])
        else:
            p = (cursor[0], n[0]+(cursor[1] if relative else 0))
        if upper == "M":
            if points:
                contours.append((points, False))
            points, start = [], p
            command = "l" if relative else "L"
        points.append(p)
        cursor = p
    if points:
        contours.append((points, False))
    return contours


@dataclass
class Primitive:
    source: str
    element: str
    part: int
    kind: str
    points: list
    closed: bool = False
    width: float = .04

    @property
    def identity(self):
        return f"{self.source}:{self.element}:{self.part}:{self.kind}"


def read_svg(path):
    root = ET.parse(path).getroot()
    size, root_matrix = viewport(root)
    primitives, rectangles, groups = [], {}, {}
    duplicate_vertices = 0
    serial = 0

    def visit(element, parent_matrix, ancestors):
        nonlocal serial, duplicate_vertices
        tag = element.tag.split("}")[-1]
        matrix = matmul(parent_matrix, transform(element.get("transform", "")))
        ancestry = ancestors + ([element.get("id")] if element.get("id") else [])
        if tag in ("title", "desc", "metadata"):
            return
        if tag in ("svg", "g"):
            for node in element:
                visit(node, matrix, ancestry)
            return
        serial += 1
        name = element.get("id") or "/".join(ancestry + [f"{tag}-{serial}"])
        produced = []
        if tag == "path":
            for part, (points, closed) in enumerate(path_contours(element.attrib["d"])):
                normalized = [p for i,p in enumerate(points) if i == 0 or p != points[i-1]]
                duplicate_vertices += len(points)-len(normalized)
                produced.append(Primitive(path.name, name, part, "poly", [apply(matrix, p) for p in normalized], closed))
        elif tag == "rect":
            x, y = float(element.get("x", 0)), float(element.get("y", 0))
            w, h = float(element.attrib["width"]), float(element.attrib["height"])
            if min(w, h) <= 0:
                raise ValueError(f"Invalid rectangle {name}")
            rx = min(float(element.get("rx", element.get("ry", 0))), w/2)
            ry = min(float(element.get("ry", element.get("rx", 0))), h/2)
            if min(rx, ry) < 0:
                raise ValueError(f"Negative corner radius: {name}")
            rectangles[name] = {"center": apply(matrix, (x+w/2, y+h/2)),
                                "width": math.dist(apply(matrix, (x, y)), apply(matrix, (x+w, y))),
                                "height": math.dist(apply(matrix, (x, y)), apply(matrix, (x, y+h))),
                                "corner_radii": (rx*math.hypot(matrix[0],matrix[1]),ry*math.hypot(matrix[2],matrix[3])),
                                "corners": [apply(matrix,p) for p in ((x,y),(x+w,y),(x+w,y+h),(x,y+h))]}
            if rx == 0 or ry == 0:
                produced.append(Primitive(path.name, name, 0, "poly", [apply(matrix, p) for p in [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]], True, .15))
            else:
                a,b,c,d,_,_ = matrix
                # Native circular arcs are exact only when transformed ellipse axes
                # are perpendicular and equal. Never silently change an ellipse.
                if abs((a*c+b*d)*rx*ry) > 1e-9 or abs(math.hypot(a,b)*rx-math.hypot(c,d)*ry) > 1e-9:
                    raise ValueError(f"Noncircular transformed rectangle {name} requires explicit support")
                segments = [((x+rx,y),(x+w-rx,y)),((x+w,y+ry),(x+w,y+h-ry)),
                            ((x+w-rx,y+h),(x+rx,y+h)),((x,y+h-ry),(x,y+ry))]
                for part, points in enumerate(segments):
                    produced.append(Primitive(path.name,name,part,"line",[apply(matrix,p) for p in points],width=.15))
                for part,(cx,cy,angle) in enumerate([(x+w-rx,y+ry,-90),(x+w-rx,y+h-ry,0),(x+rx,y+h-ry,90),(x+rx,y+ry,180)],4):
                    points = [(cx+rx*math.cos(math.radians(angle+t)),cy+ry*math.sin(math.radians(angle+t))) for t in (0,45,90)]
                    produced.append(Primitive(path.name,name,part,"arc",[apply(matrix,p) for p in points],width=.15))
        else:
            raise ValueError(f"Unsupported SVG element: {tag} in {path}")
        primitives.extend(produced)
        for group in ancestry:
            groups.setdefault(group, []).extend(p for item in produced for p in item.points)

    visit(root, root_matrix, [])
    return {"root": root, "size_mm": size, "viewbox_to_mm": root_matrix,
            "primitives": primitives, "rectangles": rectangles, "groups": groups,
            "duplicate_vertices_removed": duplicate_vertices}


def pcb_point(point):
    return (20+point[0], 20+point[1])


def switch_centers(board):
    import pcbnew
    found = {}
    for footprint in board.GetFootprints():
        if not re.fullmatch(r"SW(?:[1-9]|[1-5][0-9]|60)", footprint.GetReference()):
            continue
        field = footprint.GetFieldByName("Key_ID")
        if not field or field.GetText() in found:
            raise ValueError(f"Missing/duplicate PCB Key_ID on {footprint.GetReference()}")
        p = footprint.GetPosition()
        found[field.GetText()] = {"reference": footprint.GetReference(),
                                 "pcb_mm": (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))}
    return found


def audit_sources(board, source_dir=SOURCE_DIR):
    source_dir = Path(source_dir)
    sources = {name: read_svg(source_dir/name) for name in (APPEARANCE, BOUNDARIES, PROVISIONAL)}
    for name, source in sources.items():
        if source["size_mm"] != (208., 58.):
            raise ValueError(f"Unexpected physical panel size in {name}: {source['size_mm']}")
    with (source_dir/CSV_FILE).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    keys = {row["key_id"]: row for row in rows}
    rects = {key.removeprefix("key-"): value for key, value in sources[BOUNDARIES]["rectangles"].items()}
    switches = switch_centers(board)
    if len(rows) != 60 or len(keys) != 60 or set(keys) != set(rects) or set(keys) != set(switches):
        raise ValueError("Expected the same 60 unique key IDs in SVG, CSV, and PCB")
    layout_keys = {key["id"]:key for key in json.loads((source_dir/LAYOUT_FILE).read_text())["keys"]}
    if set(layout_keys) != set(keys):
        raise ValueError("Source JSON key IDs differ from SVG/CSV/PCB")
    errors = {"svg_vs_csv_top_origin": [], "svg_vs_csv_bottom_origin": [],
              "layout_json_vs_csv": [], "layout_json_vs_svg": [],
              "svg_vs_actual_switch": [], "csv_vs_actual_switch": [], "key_size": []}
    for key, row in keys.items():
        center, fp = rects[key]["center"], switches[key]["pcb_mm"]
        csv_svg = (float(row["source_svg_center_x_mm"]),float(row["source_svg_center_y_mm"]))
        csv_xy = (float(row["center_x_mm"]),float(row["center_y_mm"]))
        layout_key = layout_keys[key]
        layout_center = (layout_key["x"]+layout_key["w"]/2,layout_key["y"]+layout_key["h"]/2)
        errors["layout_json_vs_csv"].append(math.dist(layout_center,csv_svg))
        errors["layout_json_vs_svg"].append(math.dist(layout_center,center))
        errors["svg_vs_csv_top_origin"].append(math.dist(center,csv_svg))
        errors["svg_vs_csv_bottom_origin"].append(math.dist((center[0],58-center[1]),csv_xy))
        errors["svg_vs_actual_switch"].append(math.dist(pcb_point(center),fp))
        errors["csv_vs_actual_switch"].append(math.dist((20+csv_xy[0],78-csv_xy[1]),fp))
        errors["key_size"].append(math.dist((rects[key]["width"],rects[key]["height"]),
                                          (float(row["source_key_width_mm"]),float(row["source_key_height_mm"]))))
    maxima = {key+"_max_error_mm": max(value) for key,value in errors.items()}
    if max(maxima.values()) > 1e-6:
        raise ValueError(f"Key source/placement mismatch: {maxima}")
    outer = sources[APPEARANCE]["primitives"][0].points
    bounds = [(min(p[i] for p in outer),max(p[i] for p in outer)) for i in (0,1)]
    panel_center = [(low+high)/2 for low,high in bounds]
    provisional_rects = list(sources[PROVISIONAL]["rectangles"].values())
    if bounds != [(0.,208.),(0.,58.)] or len(provisional_rects) != 1:
        raise ValueError("Unexpected source outer contour")
    provisional = provisional_rects[0]
    if provisional["center"] != (104.,29.) or provisional["width"] != 208. or provisional["height"] != 58. or provisional["corner_radii"] != (2.,2.):
        raise ValueError("Provisional outer contour differs from 208 x 58 mm R2")
    # 01 has the source author's linearized corner boundary; do not replace it
    # with 06's mathematically circular contour. Audit their geometric deviation.
    corner_errors = []
    for p,q in zip(outer,outer[1:]+outer[:1]):
        for t in (0,.25,.5,.75,1):
            x,y = (p[i]+t*(q[i]-p[i]) for i in (0,1))
            if (x < 2 or x > 206) and (y < 2 or y > 56):
                cx,cy = (2 if x < 2 else 206),(2 if y < 2 else 56)
                corner_errors.append(abs(math.hypot(x-cx,y-cy)-2))
    if max(corner_errors,default=0) > .001:
        raise ValueError("Appearance outline differs from provisional R2 beyond 1 um")
    cross = sources[APPEARANCE]["groups"]["OPAQUE_GRAY_CROSS"]
    cross_center = [(min(p[i] for p in cross)+max(p[i] for p in cross))/2 for i in (0,1)]
    if math.dist(cross_center,(103,29)) > 1e-6:
        raise ValueError(f"Unexpected print cross center: {cross_center}")
    report = {
        "status": "PASS: source geometry and independent 60-key alignment verified; reference only",
        "source_sha256": {name: hashlib.sha256((source_dir/name).read_bytes()).hexdigest() for name in (*sources,CSV_FILE,LAYOUT_FILE)},
        "source_roles": {APPEARANCE:"Original appearance: panel boundary, print cross, translucent legend boundaries",
                         BOUNDARIES:"60 emboss boundaries, explicitly NOT_PRINT_NOT_CUT",
                         PROVISIONAL:"Provisional panel contour, audited but not redundantly imported"},
        "fabrication_authority": "Source graphics retain their original provisional manufacturing annotations. Asset identity is verified separately; these annotations do not establish order status. This audit does not establish supplier final-proof approval.",
        "physical_size_mm": [208,58], "csv_to_pcb": "(20+x,78-y) mm",
        "svg_to_pcb": "SVG physical top-left coordinates (u,v) -> (20+u,20+v) mm",
        "source_viewbox_to_mm": {name:list(s["viewbox_to_mm"]) for name,s in sources.items()},
        "key_count":60, **maxima,
        "print_cross_center_source_mm":cross_center, "print_cross_center_pcb_mm":list(pcb_point(cross_center)),
        "panel_center_source_mm":panel_center, "panel_center_pcb_mm":list(pcb_point(panel_center)),
        "source_panel_boundary_bounds_mm":bounds,
        "source_sampled_R2_vs_provisional_exact_R2_max_error_mm":max(corner_errors,default=0),
        "source_sampled_R2_preserved":True,
        "cross_minus_panel_center_mm":[cross_center[0]-104,cross_center[1]-29],
        "layer":"User.1", "appearance":"Unfilled source boundaries; printing colors/fill semantics remain in original SVG",
        "edge_cuts_created":0,
        "provisional_outer_contour":"208 x 58 mm, R2; reference only, not a PCB outline",
    }
    provenance_path = ROOT/"validation"/"panel_source_provenance.json"
    if source_dir.resolve() == SOURCE_DIR.resolve() and provenance_path.exists():
        provenance = json.loads(provenance_path.read_text())
        for name,asset in provenance["repo_assets"].items():
            if report["source_sha256"].get(name) != asset["sha256"]:
                raise ValueError(f"Source differs from independently verified handoff archive: {name}")
        if report["source_sha256"][CSV_FILE] != provenance["csv_derivation_audit"]["sha256"]:
            raise ValueError("CSV differs from the independently verified source derivation")
        report["verified_handoff_archive"] = provenance["source_archive"]
        report["handoff_archive_byte_identical_assets"] = list(provenance["repo_assets"])
        report["csv_archive_relationship"] = provenance["csv_derivation_audit"]
    return sources, switches, report


def import_panel_svg(board, source_dir=SOURCE_DIR):
    """Add exact source contours to a pcbnew.BOARD and return its verification report."""
    import pcbnew
    sources, _, report = audit_sources(board, source_dir)
    primitives = sources[APPEARANCE]["primitives"] + sources[BOUNDARIES]["primitives"]
    if any(p.kind == "poly" and not p.closed for p in primitives):
        raise ValueError("Open source contours require explicit support")
    for group in list(board.Groups()):
        if group.GetName() == GROUP_NAME:
            for item in list(group.GetItems()):
                group.RemoveItem(item)
                board.Delete(item)
            board.Delete(group)
    group = pcbnew.PCB_GROUP(board)
    group.SetName(GROUP_NAME)
    group.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(NAMESPACE,GROUP_NAME))))
    board.Add(group)
    counts = {}
    max_error = 0.
    points_verified = 0
    for primitive in primitives:
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetLayer(pcbnew.User_1)
        shape.SetLocked(True)
        shape.SetWidth(round(primitive.width*1e6))
        shape.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(NAMESPACE,primitive.identity))))
        coords = [pcb_point(point) for point in primitive.points]
        actual = [pcbnew.VECTOR2I(round(x*1e6),round(y*1e6)) for x,y in coords]
        if primitive.kind == "poly":
            if not primitive.closed:
                raise ValueError("Open source contours require explicit support")
            shape.SetShape(pcbnew.SHAPE_T_POLY)
            chain = pcbnew.SHAPE_LINE_CHAIN()
            for point in actual:
                chain.Append(point, True)
            chain.SetClosed(True)
            poly = pcbnew.SHAPE_POLY_SET()
            poly.AddOutline(chain)
            shape.SetPolyShape(poly)
            shape.SetFilled(False)
        elif primitive.kind == "arc":
            shape.SetShape(pcbnew.SHAPE_T_ARC)
            shape.SetArcGeometry(*actual)
        else:
            shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
            shape.SetStart(actual[0]); shape.SetEnd(actual[1])
        board.Add(shape); group.AddItem(shape)
        counts[primitive.kind] = counts.get(primitive.kind,0)+1
        for expected,point in zip(coords,actual):
            max_error = max(max_error,math.dist(expected,(point.x/1e6,point.y/1e6)))
            points_verified += 1
    group.SetLocked(True)
    report.update(imported_group=GROUP_NAME, imported_shapes=len(primitives),shape_counts=counts,
                  original_linear_path_contours=len(sources[APPEARANCE]["primitives"]),
                  original_path_vertices=sum(len(p.points) for p in sources[APPEARANCE]["primitives"]),
                  zero_length_duplicate_vertices_removed=sources[APPEARANCE]["duplicate_vertices_removed"],
                  original_path_vertex_resampling=False, native_rounded_rectangle_arcs=True,
                  coordinate_quantization_max_error_mm=max_error, source_points_verified=points_verified)
    report.update(verify_imported_geometry(board,sources))
    return report


def verify_imported_geometry(board, sources):
    """Compare actual native KiCad geometry against every original source vertex."""
    import pcbnew
    group = next(g for g in board.Groups() if g.GetName() == GROUP_NAME)
    shapes = {str(item.m_Uuid.AsString()):item for item in group.GetItems()}
    expected = sources[APPEARANCE]["primitives"]+sources[BOUNDARIES]["primitives"]
    if len(shapes) != len(expected):
        raise ValueError("Import group shape count differs from source")
    errors, arc_radius_errors = [], []
    for primitive in expected:
        shape = shapes[str(uuid.uuid5(NAMESPACE,primitive.identity))]
        if shape.GetLayer() != pcbnew.User_1:
            raise ValueError("Source geometry escaped User.1")
        if primitive.kind == "poly":
            poly = shape.GetPolyShape()
            if poly.OutlineCount() != 1 or not poly.COutline(0).IsClosed():
                raise ValueError("Source contour topology changed")
            chain = poly.COutline(0)
            actual = [chain.CPoint(i) for i in range(chain.PointCount())]
        elif primitive.kind == "arc":
            actual = [shape.GetStart(),shape.GetArcMid(),shape.GetEnd()]
            # Compare the native arc radius to the source quarter-circle chord.
            radius = math.dist(primitive.points[0],primitive.points[2])/math.sqrt(2)
            arc_radius_errors.append(abs(shape.GetRadius()/1e6-radius))
        else:
            actual = [shape.GetStart(),shape.GetEnd()]
        if len(actual) != len(primitive.points):
            raise ValueError(f"Source vertex count changed: {primitive.identity} {len(primitive.points)} -> {len(actual)}")
        errors.extend(math.dist(pcb_point(p),(q.x/1e6,q.y/1e6)) for p,q in zip(primitive.points,actual))
    if max(errors) > 3e-6 or (arc_radius_errors and max(arc_radius_errors) > 3e-6):
        raise ValueError("KiCad geometry differs from source beyond 3 nm")
    return {"native_geometry_max_point_error_mm":max(errors),
            "native_arc_radius_max_error_mm":max(arc_radius_errors,default=0),
            "native_geometry_tolerance_mm":3e-6,
            "verification":"Every native polygon vertex, line endpoint and arc start/mid/end compared against original SVG; native arc radius checked"}


def write_overlay(board, output, source_dir=SOURCE_DIR):
    """Visual review uses original SVG plus actual KiCad switch positions."""
    sources, switches, _ = audit_sources(board,source_dir)
    root = copy.deepcopy(sources[APPEARANCE]["root"])
    # Each source may have its own viewBox and root transform. Convert physical
    # positions back into the appearance root's local coordinates before merging.
    appearance_matrix = matmul(sources[APPEARANCE]["viewbox_to_mm"],transform(root.get("transform","")))
    a,b,c,d,e,f = appearance_matrix
    det = a*d-b*c
    inverse = (d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det)
    boundary_root = sources[BOUNDARIES]["root"]
    boundary_matrix = matmul(sources[BOUNDARIES]["viewbox_to_mm"],transform(boundary_root.get("transform","")))
    local_matrix = matmul(inverse,boundary_matrix)
    boundary_group = ET.SubElement(root,f"{{{NS}}}g",{"transform":"matrix("+" ".join(map(str,local_matrix))+")"})
    for node in boundary_root:
        if node.tag.split("}")[-1] == "g":
            boundary_group.append(copy.deepcopy(node))
    group = ET.SubElement(root,f"{{{NS}}}g",{"id":"ACTUAL_PCB_SWITCH_CENTERS","fill":"none","stroke":"#00ffb2","stroke-width":"0.09"})
    for key, switch in sorted(switches.items()):
        px,py = switch["pcb_mm"]
        x,y = apply(inverse,(px-20,py-20))
        ET.SubElement(group,f"{{{NS}}}circle",{"cx":str(x),"cy":str(y),"r":"1.1"})
        ET.SubElement(group,f"{{{NS}}}path",{"d":f"M{x-1.4},{y}H{x+1.4}M{x},{y-1.4}V{y+1.4}"})
        title = ET.SubElement(group,f"{{{NS}}}title"); title.text=f"{switch['reference']} / {key}: actual PCB {px},{py} mm"
    root.set("data-review","Original source appearance and emboss geometry; green = actual PCB switch centers")
    ET.ElementTree(root).write(output,encoding="utf-8",xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board",type=Path,default=ROOT/"WING27.kicad_pcb")
    parser.add_argument("--source-dir",type=Path,default=SOURCE_DIR)
    parser.add_argument("--output",type=Path,help="Explicit PCB output; absent means audit only")
    parser.add_argument("--report",type=Path)
    parser.add_argument("--overlay",type=Path,help="Review SVG output, preferably outside repository")
    args = parser.parse_args()
    import pcbnew
    board = pcbnew.LoadBoard(str(args.board))
    if args.output:
        report = import_panel_svg(board,args.source_dir)
        pcbnew.SaveBoard(str(args.output),board)
        reread = pcbnew.LoadBoard(str(args.output))
        sources,_,_ = audit_sources(reread,args.source_dir)
        report.update(verify_imported_geometry(reread,sources))
        report["saved_board_round_trip_verified"] = True
    else:
        _,_,report = audit_sources(board,args.source_dir)
        if any(g.GetName() == GROUP_NAME for g in board.Groups()):
            sources,_,_ = audit_sources(board,args.source_dir)
            report.update(verify_imported_geometry(board,sources))
    if args.overlay:
        write_overlay(board,args.overlay,args.source_dir)
    if args.report:
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
