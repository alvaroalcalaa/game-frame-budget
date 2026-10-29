"""Analyze frame-time captures locally. Python standard library only."""
import argparse
from collections import defaultdict
import html
import json
import math
from pathlib import Path
import statistics
import sys


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Clave JSON repetida: ' + key)
        obj[key] = value
    return obj


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get('frames'), list):
        raise ValueError('Se requiere un objeto con lista frames')
    if not 1 <= len(data['frames']) <= 200000:
        raise ValueError('Se requieren entre 1 y 200000 fotogramas')
    frames = []
    scenes = set()
    for frame in data['frames']:
        if not isinstance(frame, dict):
            raise ValueError('Fotograma no válido')
        scene, ms = frame.get('scene'), frame.get('ms')
        if not isinstance(scene, str) or not scene.strip() or len(scene) > 120:
            raise ValueError('scene debe ser texto no vacío de hasta 120 caracteres')
        if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not math.isfinite(ms) or not 0 < ms <= 60000:
            raise ValueError('ms debe ser un número finito en (0, 60000]')
        scenes.add(scene)
        if len(scenes) > 200:
            raise ValueError('Máximo 200 escenas')
        frames.append({'scene': scene, 'ms': float(ms)})
    return frames


def load_capture(path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('La captura supera 16 MiB')
    data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Número no finito')))
    return validate(data)


def percentile(values, percent):
    """Nearest-rank percentile: sorted[ceil(p*n)-1]."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percent * len(ordered) / 100) - 1)]


def metrics(frames, budget):
    values = [f['ms'] for f in frames]
    longest = run = 0
    previous_scene = None
    for f in frames:
        # Scene transitions always terminate consecutive runs.
        if f['scene'] != previous_scene:
            run = 0
        run = run + 1 if f['ms'] > budget else 0
        longest = max(longest, run)
        previous_scene = f['scene']
    slow_count = max(1, math.ceil(len(values) * .01))
    slowest = sorted(values, reverse=True)[:slow_count]
    return {'frames': len(values), 'duration_ms': sum(values),
            'mean_ms': statistics.mean(values),
            'effective_fps': 1000 / statistics.mean(values),
            'p50_ms': percentile(values, 50), 'p95_ms': percentile(values, 95),
            'p99_ms': percentile(values, 99),
            'slowest_1pct_mean_fps': 1000 / statistics.mean(slowest),
            'over_budget_frames': sum(x > budget for x in values),
            'over_budget_pct': 100 * sum(x > budget for x in values) / len(values),
            'over_2x_budget_frames': sum(x > 2 * budget for x in values),
            'longest_over_budget_run': longest,
            'small_sample': len(values) < 100}


def summarize(frames, budget):
    grouped = defaultdict(list)
    # Preserve transitions so runs do not join separate visits to a scene.
    segments = defaultdict(list)
    previous = None
    for frame in frames:
        scene = frame['scene']
        if scene != previous and grouped[scene]:
            segments[scene].append(len(grouped[scene]))
        grouped[scene].append(frame)
        previous = scene
    result = {}
    for scene in sorted(grouped):
        result[scene] = metrics(grouped[scene], budget)
        longest = 0
        start = 0
        for end in segments[scene] + [len(grouped[scene])]:
            longest = max(longest, metrics(grouped[scene][start:end], budget)['longest_over_budget_run'])
            start = end
        result[scene]['longest_over_budget_run'] = longest
    return {'overall': metrics(frames, budget), 'scenes': result}


def analyze(frames, target_fps=60, baseline=None):
    if isinstance(target_fps, bool) or not isinstance(target_fps, (int, float)) or not math.isfinite(target_fps) or not 1 <= target_fps <= 1000:
        raise ValueError('target-fps debe estar entre 1 y 1000')
    budget = 1000 / target_fps
    current = summarize(frames, budget)
    report = {'target_fps': target_fps, 'budget_ms': budget, 'current': current,
              'notice': 'Métricas de capturas suministradas; no identifica causas ni mide el motor del juego.'}
    if baseline is not None:
        old = summarize(baseline, budget)
        comparison = {}
        for scene in sorted(current['scenes'].keys() | old['scenes'].keys()):
            if scene not in old['scenes']:
                comparison[scene] = {'status': 'added'}
            elif scene not in current['scenes']:
                comparison[scene] = {'status': 'removed'}
            else:
                a, b = old['scenes'][scene], current['scenes'][scene]
                comparison[scene] = {'status': 'matched', 'baseline_frames': a['frames'],
                    'current_frames': b['frames'], 'p95_delta_ms': b['p95_ms'] - a['p95_ms'],
                    'over_budget_delta_pp': b['over_budget_pct'] - a['over_budget_pct']}
        report.update(baseline=old, comparison=comparison)
    return report


def render_html(report):
    rows = []
    for scene, m in report['current']['scenes'].items():
        rows.append('<tr><td>' + html.escape(scene) + '</td>' + ''.join(
            '<td>' + str(value) + '</td>' for value in
            (m['frames'], round(m['p95_ms'], 3), round(m['over_budget_pct'], 2), m['longest_over_budget_run'])) + '</tr>')
    comparison = ''
    if 'comparison' in report:
        comparison = '<h2>Comparación (actual − base)</h2><pre>' + html.escape(
            json.dumps(report['comparison'], ensure_ascii=False, indent=2)) + '</pre>'
    return ('<!doctype html><html lang="es"><meta charset="utf-8"><title>Game Frame Budget</title>'
            '<style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px;background:#101827;color:#eef3fc}'
            'table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #51617a}pre{white-space:pre-wrap}</style>'
            '<h1>Game Frame Budget</h1><p>Objetivo: ' + str(report['target_fps']) + ' FPS · Presupuesto: '
            + str(round(report['budget_ms'], 3)) + ' ms</p><p>' + html.escape(report['notice'])
            + '</p><table><tr><th>Escena</th><th>Frames</th><th>p95 ms</th><th>Fuera de presupuesto %</th><th>Racha máxima</th></tr>'
            + ''.join(rows) + '</table><p>Con menos de 100 frames los percentiles altos son poco representativos. '
            'Consulta el JSON para todas las métricas y el indicador small_sample.</p>' + comparison + '</html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--target-fps', type=float, default=60)
    parser.add_argument('--json', dest='json_path', type=Path)
    parser.add_argument('--html', dest='html_path', type=Path)
    args = parser.parse_args(argv)
    try:
        inputs = {p.resolve() for p in (args.capture, args.baseline) if p}
        outputs = [p.resolve() for p in (args.json_path, args.html_path) if p]
        if any(p in inputs for p in outputs) or len(set(outputs)) != len(outputs):
            raise ValueError('Las salidas deben ser distintas y no sobrescribir entradas')
        report = analyze(load_capture(args.capture), args.target_fps,
                         load_capture(args.baseline) if args.baseline else None)
        encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.json_path:
            args.json_path.write_text(encoded, encoding='utf-8')
        if args.html_path:
            args.html_path.write_text(render_html(report), encoding='utf-8')
        print(encoded, end='')
        return 0
    except (OSError, ValueError, RecursionError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
