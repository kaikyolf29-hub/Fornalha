extends Node
## Toca os efeitos sonoros gerados pela Fornalha (Audio/efeitos) e a música da
## área (Audio/musica). Autoload "Sons".

var efeitos := {}   # nome -> lista de AudioStream (variações)
var musica: AudioStreamPlayer


func _ready() -> void:
	var dir := DirAccess.open("res://Audio/efeitos")
	if dir:
		for arquivo in dir.get_files():
			if arquivo.ends_with(".wav"):
				var nome := arquivo.get_basename().rstrip("0123456789").trim_suffix("_")
				var base := nome.split("_")[0]
				var stream := load("res://Audio/efeitos/" + arquivo)
				if stream:
					for chave in [nome, base]:
						if not efeitos.has(chave):
							efeitos[chave] = []
						efeitos[chave].append(stream)
	musica = AudioStreamPlayer.new()
	musica.volume_db = -8.0
	add_child(musica)


func tocar(nome: String, onde := Vector3.ZERO) -> void:
	var lista: Array = efeitos.get(nome, [])
	if lista.is_empty():
		return
	var p := AudioStreamPlayer3D.new()
	p.stream = lista[randi() % lista.size()]
	p.pitch_scale = randf_range(0.93, 1.07)
	add_child(p)
	p.global_position = onde
	p.play()
	p.finished.connect(p.queue_free)


func tocar_musica(caminho: String) -> void:
	var original := load(caminho)
	if original == null:
		return
	# cópia: mexer no loop do recurso em cache deixa ele preso na saída do jogo
	var stream: AudioStream = original.duplicate()
	if stream is AudioStreamWAV:
		stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
		stream.loop_begin = 0
		stream.loop_end = int(stream.get_length() * stream.mix_rate)
	musica.stream = stream
	musica.play()


func _exit_tree() -> void:
	# solta os sons antes de o jogo fechar (senão a engine avisa "resources still in use at exit")
	if musica:
		musica.stop()
		musica.stream = null
	efeitos.clear()
