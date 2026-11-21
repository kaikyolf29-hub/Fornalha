# HY-Motion de mentira: mesma linha de comando da inferência oficial; grava um
# .npz com poses SMPL (eixo-ângulo, 22 juntas) em que os braços descem da T-pose.
import argparse
import math
import os

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--model_path")
ap.add_argument("--input_text_dir")
ap.add_argument("--output_dir")
a = ap.parse_args()
texto = open(os.path.join(a.input_text_dir, os.listdir(a.input_text_dir)[0]), encoding="utf-8").read().strip()
assert texto, "sem texto"
q = int(float(os.environ.get("FORNALHA_SEGUNDOS", "2")) * 30)
poses = np.zeros((q, 52 * 3))
for k in range(q):
    t = k / (q - 1)
    poses[k, 16 * 3 + 2] = -math.radians(80) * t
    poses[k, 17 * 3 + 2] = math.radians(80) * t
trans = np.tile([0.0, 0.92, 0.0], (q, 1))
os.makedirs(a.output_dir, exist_ok=True)
np.savez(os.path.join(a.output_dir, "movimento_000.npz"), poses=poses, trans=trans, mocap_framerate=30.0)
