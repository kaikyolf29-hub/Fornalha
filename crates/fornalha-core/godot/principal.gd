extends Node3D
## Cena principal montada pela Fornalha: toca a música da área ao abrir.

@export_file("*.wav", "*.ogg") var musica := ""


func _ready() -> void:
	var sons := get_node_or_null("/root/Sons")
	if musica != "" and sons:
		sons.tocar_musica(musica)
