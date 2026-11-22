extends Node
## Toca os efeitos sonoros gerados pela Fornalha (Audio/efeitos), a música da área pela
## situação (Audio/musica) e as falas presas ao personagem (Audio/dublagem). Autoload "Sons".

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


func tocar_musica(qual: String) -> void:
	## Pede a música pela situação ("combate", "vila"...) ou pelo caminho do arquivo. Na Erethea
	## (nós no grupo "erethea_musica"), quem troca a música é ela, no fim do compasso.
	var situacao := qual.get_file().get_basename() if qual.begins_with("res://") else qual
	var caminho := qual if qual.begins_with("res://") else "res://Audio/musica/%s.wav" % qual
	if get_tree() and get_tree().has_group("erethea_musica"):
		get_tree().call_group("erethea_musica", "tocar", situacao)
		return
	var original := load(caminho) if ResourceLoader.exists(caminho) else null
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


func falar(personagem: String, arquivo: String) -> AudioStreamPlayer3D:
	## Toca a fala presa ao personagem (o som sai da cabeça dele e acompanha quando ele anda).
	## arquivo: "res://Audio/dublagem/<id>_01.wav" ou só "<id>_01".
	var caminho := arquivo if arquivo.begins_with("res://") else "res://Audio/dublagem/%s.wav" % arquivo
	var stream: AudioStream = load(caminho) if ResourceLoader.exists(caminho) else null
	if stream == null:
		return null
	var dono := _personagem(personagem)
	var p := AudioStreamPlayer3D.new()
	p.stream = stream
	p.unit_size = 4.0
	p.name = "Fala"
	if dono:
		dono.add_child(p)
		p.position = Vector3(0, 1.6, 0)
	else:
		add_child(p)
	p.play()
	p.finished.connect(p.queue_free)
	return p


func _personagem(id: String) -> Node3D:
	if get_tree() == null:
		return null
	for n in get_tree().get_nodes_in_group("personagens"):
		if n is Node3D and (n.get_meta("fornalha_id", "") == id or n.name == id):
			return n
	return null


func _exit_tree() -> void:
	# solta os sons antes de o jogo fechar (senão a engine avisa "resources still in use at exit")
	if musica:
		musica.stop()
		musica.stream = null
	efeitos.clear()
