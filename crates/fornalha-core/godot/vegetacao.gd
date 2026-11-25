extends MultiMeshInstance3D
## Vegetação da bancada de mapa da Fornalha. As posições ficam guardadas aqui (a engine sem tela, que
## monta as cenas, não guarda os dados do MultiMesh) e viram o MultiMesh quando a cena abre.
## Formato: 12 números por planta (base 3x3 em linhas e a posição), como o MultiMesh.buffer.

@export var transformacoes: PackedFloat32Array


func _ready() -> void:
	if multimesh == null or transformacoes.size() < 12:
		return
	multimesh.instance_count = transformacoes.size() / 12
	multimesh.buffer = transformacoes
