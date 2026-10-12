"""Compose frozen visual annotations by raw record ID, without reading labels.

This is a union of reviewed instances, never an inference or instance merger.
Inputs must have the same source and disjoint confirmed points. Evidence remains
in its original camera frame and is linked explicitly to its source session.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
from datetime import datetime, timezone
import numpy as np
from .scene import Scene, digest, save_archive


def _read(path):
    scene = Scene(path)
    state = json.loads((scene.path / 'state.json').read_text())
    annotation = scene.path / 'annotation.npz'
    if not state['finished'] or digest(annotation) != state['annotation_sha256']:
        raise ValueError('composition requires frozen, intact annotations')
    with np.load(annotation) as a:
        ids, labels = a['record_ids'], a['instance_ids']
    if not np.array_equal(ids, scene.record_ids) or labels.shape != ids.shape:
        raise ValueError('annotation raw IDs do not match geometry')
    reconstructed = np.zeros(len(ids), np.int32)
    for number, name in enumerate(sorted(state['instances']), 1):
        instance = state['instances'][name]
        candidate = state['candidates'][instance['candidate_id']]
        indices = np.load(scene.path / 'candidates' / (instance['candidate_id'] + '.npy'))
        if indices.ndim != 1 or not np.issubdtype(indices.dtype, np.integer):
            raise ValueError('invalid candidate indices')
        if np.any(indices < 0) or np.any(indices >= len(ids)) or len(np.unique(indices)) != len(indices):
            raise ValueError('invalid candidate indices')
        point_hash = hashlib.sha256(ids[indices].tobytes()).hexdigest()
        if candidate['status'] != 'CONFIRMED' or point_hash != instance['point_sha256'] or point_hash != candidate['point_sha256']:
            raise ValueError('confirmed candidate changed')
        if np.any(reconstructed[indices]):
            raise ValueError('overlapping source instances')
        reconstructed[indices] = number
    if not np.array_equal(reconstructed, labels):
        raise ValueError('annotation differs from reviewed candidates')
    return scene, state, labels


def compose(base, refinements, destination, development_note):
    out = Path(destination).resolve()
    if out.exists():
        raise ValueError('choose a fresh output directory')
    base_scene, _, _ = _read(base)
    sources = [Path(base).resolve()] + [Path(p).resolve() for p in refinements]
    if len(set(sources)) != len(sources):
        raise ValueError('duplicate source')
    entries, unknown, manifests = {}, [], []
    occupied = np.zeros(len(base_scene.record_ids), bool)
    identity = ['source_las', 'source_size', 'source_mtime_ns', 'scene_total_points']
    for source_number, source in enumerate(sources):
        scene, state, labels = _read(source)
        if any(scene.meta[k] != base_scene.meta[k] for k in identity):
            raise ValueError('source LAS identity mismatch')
        indices = np.flatnonzero(labels > 0)
        target = np.searchsorted(base_scene.record_ids, scene.record_ids[indices])
        if np.any(target >= len(base_scene.record_ids)) or not np.array_equal(base_scene.record_ids[target], scene.record_ids[indices]):
            raise ValueError('refinement outside base raw record coverage')
        if not np.array_equal(base_scene.coords[target], scene.coords[indices]):
            raise ValueError('refinement geometry mismatch')
        if np.any(occupied[target]):
            raise ValueError('overlap requires explicit visual association; union rejected')
        occupied[target] = True
        prefix = f's{source_number:02d}__'
        for number, name in enumerate(sorted(state['instances']), 1):
            instance = copy.deepcopy(state['instances'][name])
            candidate = copy.deepcopy(state['candidates'][instance['candidate_id']])
            local = np.flatnonzero(labels == number)
            mapped = np.searchsorted(base_scene.record_ids, scene.record_ids[local])
            merged_name = prefix + name
            instance['candidate_id'] = merged_name
            candidate['evidence_session'] = str(source)
            candidate['selection_coordinates_belong_to'] = str(source)
            candidate['source_candidate_id'] = state['instances'][name]['candidate_id']
            entries[merged_name] = (instance, candidate, mapped, source)
        unknown.extend([{**u, 'evidence_session': str(source)} for u in state['unknown']])
        manifests.append({'path': str(source), 'annotation_sha256': state['annotation_sha256'],
                          'geometry_sha256': scene.meta['geometry_sha256'],
                          'state_sha256': digest(source / 'state.json'),
                          'actions_sha256': digest(source / 'actions.jsonl')})
    out.mkdir(parents=True)
    (out / 'candidates').mkdir()
    # Immutable inputs are hash-checked on every load. Hard links avoid copying
    # the large full-scene geometry; this module never modifies source files.
    os.link(base_scene.path / 'geometry.npz', out / 'geometry.npz')
    shutil.copy2(base_scene.path / 'scene.json', out / 'scene.json')
    shutil.copytree(base_scene.path / 'views', out / 'views')
    state = {'instances': {}, 'candidates': {}, 'unknown': unknown, 'finished': True,
             'composition': {'sources': manifests, 'development_note': development_note,
                             'ground_truth_read': False, 'instance_association': 'disjoint instances only'}}
    labels = np.zeros(len(base_scene.record_ids), np.int32)
    for number, name in enumerate(sorted(entries), 1):
        instance, candidate, mapped, source = entries[name]
        np.save(out / 'candidates' / (name + '.npy'), mapped)
        overlays = []
        for i, original in enumerate(candidate['overlays']):
            src = source / 'candidates' / Path(original).name
            dst = out / 'candidates' / f'{name}_evidence_{i}.png'
            shutil.copy2(src, dst)
            overlays.append(str(dst))
        candidate['overlays'] = overlays
        state['instances'][name] = instance
        state['candidates'][name] = candidate
        labels[mapped] = number
    save_archive(out / 'annotation.npz', record_ids=base_scene.record_ids, instance_ids=labels)
    state['annotation_sha256'] = digest(out / 'annotation.npz')
    (out / 'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))
    action = {'action': 'COMPOSE', 'observer': 'frozen_annotation_executor',
              'reason': development_note, 'sources': manifests}
    result = {'instances': len(entries), 'selected_points': int(occupied.sum()),
              'annotation_sha256': state['annotation_sha256'], 'ground_truth_read': False}
    (out / 'actions.jsonl').write_text(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(),
                                                 'action': action, 'result': result}, ensure_ascii=False) + '\n')
    return result


def verify(path):
    scene, state, actual = _read(path)
    expected = np.zeros(len(scene.record_ids), np.int32)
    number = 0
    for manifest in state['composition']['sources']:
        source = Path(manifest['path'])
        for name, field in [('annotation.npz', 'annotation_sha256'), ('geometry.npz', 'geometry_sha256'),
                            ('state.json', 'state_sha256'), ('actions.jsonl', 'actions_sha256')]:
            if digest(source / name) != manifest[field]:
                raise ValueError('composition source changed')
        child, child_state, labels = _read(source)
        for local_number, _ in enumerate(sorted(child_state['instances']), 1):
            number += 1
            selected = labels == local_number
            mapped = np.searchsorted(scene.record_ids, child.record_ids[selected])
            if np.any(mapped >= len(expected)) or not np.array_equal(scene.record_ids[mapped], child.record_ids[selected]):
                raise ValueError('source record mismatch')
            if np.any(expected[mapped]):
                raise ValueError('composition overlaps')
            expected[mapped] = number
    if not np.array_equal(expected, actual):
        raise ValueError('composition labels changed')
    result = {'point_labels_identical': True, 'sources': len(state['composition']['sources']),
              'ground_truth_read': False, 'model_invoked': False,
              'meaning': 'exact frozen-source union verification, not a new model run'}
    (Path(path) / 'composition_verification.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('base'); p.add_argument('--out'); p.add_argument('--refinements', nargs='*', default=[])
    p.add_argument('--development-note'); p.add_argument('--verify', action='store_true')
    a = p.parse_args()
    if not a.verify and (not a.out or not a.development_note):
        p.error('--out and --development-note are required for composition')
    print(json.dumps(verify(a.base) if a.verify else compose(a.base, a.refinements, a.out, a.development_note), ensure_ascii=False, indent=2))
