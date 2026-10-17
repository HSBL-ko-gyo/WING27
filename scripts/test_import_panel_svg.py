#!/usr/bin/python3
"""Regression checks for source SVG import; never modify the project PCB."""
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import pcbnew
import import_panel_svg as panel


class SvgCoordinateTests(unittest.TestCase):
    def test_scaled_offset_viewbox(self):
        root = ET.fromstring('<svg width="208mm" height="58mm" viewBox="10 20 416 116"/>')
        size, matrix = panel.viewport(root)
        self.assertEqual(size,(208,58))
        self.assertEqual(panel.apply(matrix,(26,38)),(8,9))
        self.assertEqual(panel.apply(matrix,(426,136)),(208,58))

    def test_aspect_ratio_alignment(self):
        root = ET.fromstring('<svg width="208mm" height="58mm" viewBox="0 0 100 10"/>')
        _,matrix = panel.viewport(root)
        self.assertEqual(panel.apply(matrix,(50,5)),(104,29))
        root.set('preserveAspectRatio','none')
        _,matrix = panel.viewport(root)
        self.assertEqual(panel.apply(matrix,(100,10)),(208,58))

    def test_transform_order(self):
        matrix = panel.transform('translate(10,20) scale(2) rotate(90)')
        actual = panel.apply(matrix,(1,2))
        self.assertAlmostEqual(actual[0],6)
        self.assertAlmostEqual(actual[1],22)
        matrix = panel.transform('rotate(180 10 20)')
        self.assertLess(math.dist(panel.apply(matrix,(11,21)),(9,19)),1e-12)

    def test_relative_path_and_subpaths(self):
        contours = panel.path_contours('M1,2 l3,0 v4 h-3 z m9,8 l2,0 0,2 z')
        self.assertEqual(contours,[([(1.,2.),(4.,2.),(4.,6.),(1.,6.)],True),
                                   ([(10.,10.),(12.,10.),(12.,12.)],True)])

    def test_curves_fail_loudly(self):
        with self.assertRaisesRegex(ValueError,'Unsupported SVG command'):
            panel.path_contours('M0,0 C1,0 1,1 0,1 Z')

    def test_nested_transform_and_viewbox(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'scaled.svg'
            source.write_text('<svg width="208mm" height="58mm" viewBox="10 20 416 116">'
                              '<g transform="translate(10,20) scale(2)">'
                              '<rect id="key-test" x="5" y="5" width="6" height="8" rx="1.5"/>'
                              '</g></svg>')
            result = panel.read_svg(source)
            self.assertEqual(result['rectangles']['key-test']['center'],(8,9))
            self.assertEqual(len(result['primitives']),8)


class NativeImportTests(unittest.TestCase):
    def setUp(self):
        self.board = pcbnew.LoadBoard(str(panel.ROOT/'WING27.kicad_pcb'))

    def test_actual_source_and_cross(self):
        _,_,report = panel.audit_sources(self.board)
        self.assertEqual(report['key_count'],60)
        self.assertEqual(report['svg_vs_actual_switch_max_error_mm'],0)
        self.assertEqual(report['cross_minus_panel_center_mm'],[-1,0])

    def test_wrong_actual_switch_is_rejected(self):
        switch = self.board.FindFootprintByReference('SW1')
        position = switch.GetPosition()
        switch.SetPosition(pcbnew.VECTOR2I(position.x+10000,position.y))
        with self.assertRaisesRegex(ValueError,'Key source/placement mismatch'):
            panel.audit_sources(self.board)

    def test_round_trip_idempotence_and_no_collateral_change(self):
        footprints_before = [(f.GetReference(),f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees())
                             for f in self.board.GetFootprints()]
        other = pcbnew.PCB_SHAPE(self.board)
        other.SetLayer(pcbnew.User_1)
        other.SetShape(pcbnew.SHAPE_T_SEGMENT)
        other.SetStart(pcbnew.VECTOR2I(1,2)); other.SetEnd(pcbnew.VECTOR2I(3,4))
        self.board.Add(other)
        other_uuid = other.m_Uuid.AsString()
        original_ids = {s.m_Uuid.AsString() for s in self.board.GetDrawings()
                        if not s.GetParentGroup() or s.GetParentGroup().GetName()!=panel.GROUP_NAME}
        report = panel.import_panel_svg(self.board)
        count = len(self.board.GetDrawings())
        second = panel.import_panel_svg(self.board)
        self.assertEqual(report['imported_shapes'],634)
        self.assertEqual(len(self.board.GetDrawings()),count)
        self.assertEqual(second['native_geometry_max_point_error_mm'],report['native_geometry_max_point_error_mm'])
        self.assertEqual(original_ids,{s.m_Uuid.AsString() for s in self.board.GetDrawings()
                                      if not s.GetParentGroup() or s.GetParentGroup().GetName()!=panel.GROUP_NAME})
        self.assertIn(other_uuid,original_ids)
        self.assertEqual(footprints_before,[(f.GetReference(),f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees())
                                           for f in self.board.GetFootprints()])
        self.assertFalse(any(s.GetLayer()==pcbnew.Edge_Cuts for s in self.board.GetDrawings()))
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory)/'overlay.kicad_pcb')
            pcbnew.SaveBoard(output,self.board)
            board = pcbnew.LoadBoard(output)
            sources,_,_ = panel.audit_sources(board)
            result = panel.verify_imported_geometry(board,sources)
            self.assertLess(result['native_geometry_max_point_error_mm'],1e-6)
            parsed_count = len(board.GetDrawings())
            panel.import_panel_svg(board)
            self.assertEqual(len(board.GetDrawings()),parsed_count)


if __name__ == '__main__':
    unittest.main(verbosity=2)
