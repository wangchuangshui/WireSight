"""Replay actual saved visual decisions on the shipped raw ROI, no model/GT."""
import argparse
from pathlib import Path
import json
from visual_annotation_v3.replay import replay
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',default='replay-output',help='A new output directory')
a=p.parse_args()
source=Path(__file__).resolve().parents[1]/'examples/recorded_roi'
print(json.dumps(replay(source,Path(a.out)),indent=2))
