"""Generate the KiCad STEP model for the Kailh CMI627301D60 switch.

The model is based only on Kailh's CMI6273-series dimensional drawing: a 6.2 mm
square body, 7.3 mm free position, 5.0 mm pin pitch, and 3.0 mm actuator
diameter.  Undimensioned molded details are approximated from the drawing.
"""

from pathlib import Path
import os
import sys
import traceback

import cadquery as cq


CORNER_FEATURE_CENTER = 2.2


def centered_box(x: float, y: float, z: float, bottom: float) -> cq.Workplane:
    return cq.Workplane("XY").box(x, y, z).translate((0, 0, bottom + z / 2))


def notched_upper_cover() -> cq.Workplane:
    """Return the characteristic cross-shaped upper cover from the top view."""
    cover_bottom = 5.15
    cover_height = 1.4
    cover = centered_box(5.7, 5.7, cover_height, cover_bottom)

    # Four circular corner cut-outs form the rounded, concave shoulders around
    # the actuator.  These details are proportional estimates from the drawing.
    for x_pos in (-CORNER_FEATURE_CENTER, CORNER_FEATURE_CENTER):
        for y_pos in (-CORNER_FEATURE_CENTER, CORNER_FEATURE_CENTER):
            cutter = (
                cq.Workplane("XY")
                .center(x_pos, y_pos)
                .circle(1.2)
                .extrude(cover_height + 0.2)
                .translate((0, 0, cover_bottom - 0.1))
            )
            cover = cover.cut(cutter)

    return cover


def cover_plate() -> cq.Workplane:
    """Return the thin black cover plate with openings for the gray bosses."""
    plate_bottom = 4.85
    plate_height = 0.3
    plate = centered_box(6.2, 6.2, plate_height, plate_bottom)

    for x_pos in (-CORNER_FEATURE_CENTER, CORNER_FEATURE_CENTER):
        for y_pos in (-CORNER_FEATURE_CENTER, CORNER_FEATURE_CENTER):
            cutter = (
                cq.Workplane("XY")
                .center(x_pos, y_pos)
                .circle(0.73)
                .extrude(plate_height + 0.2)
                .translate((0, 0, plate_bottom - 0.1))
            )
            plate = plate.cut(cutter)

    return plate


def make_model(output_path: Path) -> None:
    assembly = cq.Assembly(name="Kailh_CMI627301D60")

    terminal_color = cq.Color(0.78, 0.80, 0.83)
    base_color = cq.Color(0.62, 0.64, 0.64)
    cover_color = cq.Color(0.08, 0.08, 0.075)
    actuator_color = cq.Color(0.68, 0.12, 0.08)

    # The PCB mounting plane is Z=0.  Terminals extend 3.3 mm below it.
    for index, x_pos in enumerate((-2.5, 2.5), start=1):
        terminal = centered_box(0.7, 0.25, 3.9, -3.3).translate((x_pos, 0, 0))
        assembly.add(terminal, name=f"Terminal_{index}", color=terminal_color)

    # Main molded housing.  The drawing identifies the 4.85 mm lower housing as
    # the gray base and the material above that seam as the black cover.
    assembly.add(centered_box(6.2, 6.2, 4.85, 0.0), name="Base", color=base_color)
    assembly.add(cover_plate(), name="Cover_Plate", color=cover_color)
    assembly.add(notched_upper_cover(), name="Cover_Upper_Cross", color=cover_color)

    # The four gray base bosses protrude through openings in the black plate.
    for x_pos in (-CORNER_FEATURE_CENTER, CORNER_FEATURE_CENTER):
        for y_pos in (-CORNER_FEATURE_CENTER, CORNER_FEATURE_CENTER):
            boss = (
                cq.Workplane("XY")
                .center(x_pos, y_pos)
                .circle(0.7)
                .extrude(0.45)
                .translate((0, 0, 4.85))
            )
            assembly.add(boss, name=f"Base_Boss_{x_pos}_{y_pos}", color=base_color)

    # The two concentric circles in the top view are the rounded top edge of
    # the single 3.0 mm actuator, not a separate flange around the button.
    actuator = cq.Workplane("XY").circle(1.5).extrude(0.75).translate((0, 0, 6.55))
    actuator = actuator.edges(">Z").fillet(0.08)
    assembly.add(actuator, name="Actuator", color=actuator_color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    assembly.save(str(output_path), exportType="STEP", mode="default")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: generate_kailh_cmi627301d60_3d.py OUTPUT.step")
        output = Path(sys.argv[1]).resolve()
        make_model(output)
        print(f"Generated {output}")
        sys.stdout.flush()
        sys.stderr.flush()
        # OCP 7.9 can fault during interpreter teardown on some Windows builds.
        # All STEP writers have completed at this point, so bypass finalizers.
        os._exit(0)
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
