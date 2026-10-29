import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from frame_budget import analyze, load_capture, percentile, render_html, validate


def frames(values, scene='plaza'):
    return validate({'frames': [{'scene': scene, 'ms': v} for v in values]})


class FrameTests(unittest.TestCase):
    def test_nearest_rank(self):
        self.assertEqual(percentile(list(range(1, 21)), 95), 19)
        self.assertEqual(percentile([7], 99), 7)

    def test_effective_fps_uses_total_time(self):
        m = analyze(frames([10, 30]), 50)['current']['overall']
        self.assertEqual(m['duration_ms'], 40)
        self.assertEqual(m['effective_fps'], 50)
        self.assertEqual(m['over_budget_pct'], 50)

    def test_strict_budget_boundaries(self):
        m = analyze(frames([20, 40, 41]), 50)['current']['overall']
        self.assertEqual(m['over_budget_frames'], 2)
        self.assertEqual(m['over_2x_budget_frames'], 1)

    def test_run_ends_on_fast_frame(self):
        m = analyze(frames([30, 30, 10, 30]), 50)['current']['overall']
        self.assertEqual(m['longest_over_budget_run'], 2)

    def test_scene_revisit_does_not_join_runs(self):
        f = frames([30, 30], 'a') + frames([30], 'b') + frames([30, 30, 30], 'a')
        r = analyze(f, 50)['current']
        self.assertEqual(r['overall']['longest_over_budget_run'], 3)
        self.assertEqual(r['scenes']['a']['longest_over_budget_run'], 3)
        self.assertEqual(r['scenes']['a']['frames'], 5)

    def test_slowest_percent(self):
        m = analyze(frames([10] * 99 + [100]))['current']['overall']
        self.assertEqual(m['slowest_1pct_mean_fps'], 10)
        self.assertFalse(m['small_sample'])
        self.assertTrue(analyze(frames([10]))['current']['overall']['small_sample'])

    def test_comparison_sign_and_units(self):
        r = analyze(frames([10, 30]), 50, frames([10, 10]))['comparison']['plaza']
        self.assertEqual(r['p95_delta_ms'], 20)
        self.assertEqual(r['over_budget_delta_pp'], 50)

    def test_missing_scenes(self):
        r = analyze(frames([10], 'new'), 60, frames([20], 'old'))['comparison']
        self.assertEqual(r['new']['status'], 'added')
        self.assertEqual(r['old']['status'], 'removed')

    def test_invalid_measurements(self):
        for v in (True, 0, -1, float('nan'), float('inf'), 60001, '12'):
            with self.subTest(value=v), self.assertRaises(ValueError):
                frames([v])

    def test_empty_and_invalid_scene(self):
        for d in ({'frames': []}, {'frames': [{'scene': ' ', 'ms': 12}]}, {'frames': [None]}, []):
            with self.assertRaises(ValueError):
                validate(d)

    def test_invalid_fps(self):
        for v in (0, True, 1001, float('nan')):
            with self.assertRaises(ValueError):
                analyze(frames([10]), v)

    def test_html_escapes_scene(self):
        markup = render_html(analyze(frames([12], '<script>alert(1)</script>')))
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)

    def test_duplicate_json_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.json'
            for text in ('{"frames":[],"frames":[]}', '{"frames":[{"scene":"a","ms":NaN}]}'):
                p.write_text(text)
                with self.assertRaises(ValueError):
                    load_capture(p)

    def test_cli_exports_and_protects_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, j, h = [Path(tmp) / n for n in ('in.json', 'out.json', 'out.html')]
            original = json.dumps({'frames': [{'scene': 'a', 'ms': 12}]})
            p.write_text(original)
            base = [sys.executable, str(Path(__file__).with_name('frame_budget.py')), str(p)]
            r = subprocess.run(base + ['--json', str(j), '--html', str(h)], capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(j.read_text())['current']['overall']['frames'], 1)
            self.assertIn('<table>', h.read_text())
            self.assertEqual(subprocess.run(base + ['--json', str(p)], capture_output=True).returncode, 2)
            self.assertEqual(subprocess.run(base + ['--json', str(j), '--html', str(j)], capture_output=True).returncode, 2)
            self.assertEqual(p.read_text(), original)


if __name__ == '__main__':
    unittest.main()
