# TRELLIS.2 de mentira: mesma interface (from_pretrained, cuda, run → malha com
# vertices, faces, coords, attrs, layout e voxel_size). Faz um "boneco" de duas
# esferas com a cor de cima e a de baixo tiradas da imagem recebida.
import numpy as np

import nvdiffrast.torch  # noqa: F401  o código de verdade importa; a Fornalha entrega um substituto


class _Malha:
    def __init__(self, img):
        a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
        h = a.shape[0]
        cima, baixo = a[: h // 2].reshape(-1, 3).mean(0), a[h // 2 :].reshape(-1, 3).mean(0)
        verts, faces = [], []
        for centro, raio in (((0, 0, 0.18), 0.17), ((0, 0, -0.2), 0.25)):
            nu, nv = 96, 64
            base = len(verts)
            for i in range(nv):
                t = np.pi * i / (nv - 1)
                for j in range(nu):
                    p = 2 * np.pi * j / nu
                    verts.append((centro[0] + raio * np.sin(t) * np.cos(p), centro[1] + raio * np.sin(t) * np.sin(p), centro[2] + raio * np.cos(t)))
            for i in range(nv - 1):
                for j in range(nu):
                    q = [base + i * nu + j, base + i * nu + (j + 1) % nu, base + (i + 1) * nu + j, base + (i + 1) * nu + (j + 1) % nu]
                    faces += [(q[0], q[2], q[1]), (q[1], q[2], q[3])]
        self.vertices = np.array(verts, dtype=np.float32)
        self.faces = np.array(faces, dtype=np.int64)
        res = 128
        self.voxel_size = 1.0 / res
        coords = np.unique(np.clip(np.floor((self.vertices + 0.5) * res), 0, res - 1).astype(np.int64), axis=0)
        z = (coords[:, 2] + 0.5) / res - 0.5
        cor = np.where((z > -0.02)[:, None], cima, baixo)
        self.coords = np.concatenate([np.zeros((len(coords), 1), dtype=np.int64), coords], axis=1)
        self.attrs = np.concatenate([cor, np.full((len(coords), 3), 0.5)], axis=1).astype(np.float32)
        self.layout = {"base_color": slice(0, 3), "metallic": slice(3, 4), "roughness": slice(4, 5), "alpha": slice(5, 6)}

    def simplify(self, n):
        return self


class Trellis2ImageTo3DPipeline:
    @classmethod
    def from_pretrained(cls, nome):
        return cls()

    def cuda(self):
        return self

    def run(self, imagem, seed=1, pipeline_type="512"):
        return [_Malha(imagem)]
