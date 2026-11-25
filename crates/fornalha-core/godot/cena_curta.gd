extends Node
## Cenas curtas da Fornalha (autoload "CenasCurtas"). tocar("id") lê res://Cutscenes/<id>.cena.json e
## mostra cada linha: câmera no enquadramento pedido, animação, fala dublada com a boca (Sons.falar),
## olhar para quem escuta e legenda. Jogador e inimigos esperam; no fim a câmera e o controle voltam.
## Enquadramentos: close, medio, aberto, ombro (por cima do ombro de quem escuta), dois (os dois juntos).

signal terminou(id: String)

var tocando := false
## O que foi tocado na última cena (o teste automático confere).
var relatorio := {}


func tocar(id: String) -> void:
	var caminho := "res://Cutscenes/%s.cena.json" % id
	var dados = JSON.parse_string(FileAccess.get_file_as_string(caminho)) if FileAccess.file_exists(caminho) else null
	if typeof(dados) != TYPE_DICTIONARY or tocando:
		push_warning("Cena curta %s não existe (ou outra está tocando)." % caminho)
		terminou.emit(id)
		return
	tocando = true
	relatorio = {"id": id, "linhas": [], "boca_mexeu": false}
	var cena := get_tree().current_scene
	var anterior := get_viewport().get_camera_3d()
	var cam := Camera3D.new()
	cam.fov = 50.0
	cam.name = "CameraDaCena"
	cena.add_child(cam)
	cam.make_current()
	var legenda := _legenda(cena)
	_esperar_todos(true)
	for linha in dados.get("linhas", []):
		var quem := _personagem(String(linha.get("quem", "")))
		var outro := _personagem(String(linha.get("olhar_para", "")))
		if quem and outro:
			_virar_para(quem, outro.global_position)
			_virar_para(outro, quem.global_position)
		_enquadrar(cam, quem, outro, String(linha.get("camera", "medio")))
		var dur := float(linha.get("duracao", 0.0))
		var mov = quem.get("movimento") if quem else null
		var anim := String(linha.get("animacao", ""))
		if anim != "" and mov:
			dur = maxf(dur, mov.tocar(anim))
		var audio := String(linha.get("audio", ""))
		if audio != "":
			get_node("/root/Sons").falar(String(linha.get("quem", "")), audio)
			dur = maxf(dur, float(linha.get("segundos", 0.0)) + 0.3)
			if mov and mov.get("rosto") and not mov.rosto._curva.is_empty():
				relatorio["boca_mexeu"] = true
		var texto := String(linha.get("texto", ""))
		legenda.get_node("Texto").text = texto
		if dur <= 0.0:
			dur = 1.5 + texto.length() * 0.06  # tempo de leitura da legenda
		relatorio["linhas"].append({"quem": linha.get("quem", ""), "camera": linha.get("camera", "medio"), "segundos": snappedf(dur, 0.01),
				"achou_quem": quem != null, "tem_rosto": mov != null and mov.get("rosto") != null, "fala": audio != ""})
		var t := 0.0
		while t < dur:
			if mov and outro and outro.get("movimento"):
				mov.olhar_para(outro.movimento.posicao_da_cabeca(), 1.0)
			await get_tree().process_frame
			t += get_process_delta_time()
	legenda.queue_free()
	cam.queue_free()
	if anterior:
		anterior.make_current()
	_esperar_todos(false)
	tocando = false
	terminou.emit(id)


func _esperar_todos(sim: bool) -> void:
	for grupo in ["jogador", "inimigos"]:
		for n in get_tree().get_nodes_in_group(grupo):
			if "em_cena" in n:
				n.em_cena = sim


func _personagem(id: String) -> Node3D:
	if id == "":
		return null
	for n in get_tree().get_nodes_in_group("personagens"):
		if n is Node3D and (n.get_meta("fornalha_id", "") == id or n.name == id):
			return n
	return null


func _cabeca(p: Node3D) -> Vector3:
	var mov = p.get("movimento")
	if mov and mov.has_method("posicao_da_cabeca"):
		return mov.posicao_da_cabeca()
	return p.global_position + Vector3.UP * 1.6


func _frente(p: Node3D) -> Vector3:
	var modelo = p.get("modelo")
	var ry: float = modelo.global_rotation.y if modelo is Node3D else p.global_rotation.y
	return Vector3(sin(ry), 0.0, cos(ry))  # os modelos da Fornalha olham para +Z


func _virar_para(p: Node3D, ponto: Vector3) -> void:
	var d := ponto - p.global_position
	d.y = 0.0
	var modelo = p.get("modelo")
	if d.length() > 0.01 and modelo is Node3D:
		modelo.global_rotation.y = atan2(d.x, d.z)


func _enquadrar(cam: Camera3D, quem: Node3D, outro: Node3D, tipo: String) -> void:
	if quem == null:
		return
	var cabeca := _cabeca(quem)
	var frente := _frente(quem)
	var lado := frente.cross(Vector3.UP).normalized()
	var pos: Vector3
	var alvo := cabeca
	match tipo:
		"close":
			pos = cabeca + frente * 0.9 + lado * 0.25 + Vector3.UP * 0.03
		"aberto":
			pos = cabeca + frente * 5.0 + lado * 1.6 + Vector3.UP * 0.8
			alvo = cabeca - Vector3.UP * 0.6
		"ombro":
			if outro:
				var c2 := _cabeca(outro)
				var d := (cabeca - c2)
				d.y = 0.0
				d = d.normalized()
				pos = c2 - d * 0.75 + d.cross(Vector3.UP).normalized() * 0.45 + Vector3.UP * 0.12
			else:
				pos = cabeca + frente * 2.0 + lado * 0.6
		"dois":
			if outro:
				var c2 := _cabeca(outro)
				var meio := (cabeca + c2) / 2.0
				var d := (c2 - cabeca)
				d.y = 0.0
				var perp := d.normalized().cross(Vector3.UP).normalized()
				pos = meio + perp * (d.length() * 1.1 + 1.8) + Vector3.UP * 0.2
				alvo = meio - Vector3.UP * 0.15
			else:
				pos = cabeca + frente * 3.0
		_:  # medio
			pos = cabeca + frente * 2.0 + lado * 0.5 - Vector3.UP * 0.1
			alvo = cabeca - Vector3.UP * 0.25
	cam.global_position = pos
	if not pos.is_equal_approx(alvo):
		cam.look_at(alvo, Vector3.UP)


func _legenda(cena: Node) -> CanvasLayer:
	var camada := CanvasLayer.new()
	camada.name = "LegendaDaCena"
	camada.layer = 20
	var faixa := ColorRect.new()
	faixa.color = Color(0, 0, 0, 0.45)
	faixa.anchor_left = 0.0
	faixa.anchor_right = 1.0
	faixa.anchor_top = 0.84
	faixa.anchor_bottom = 1.0
	camada.add_child(faixa)
	var texto := Label.new()
	texto.name = "Texto"
	texto.anchor_left = 0.08
	texto.anchor_right = 0.92
	texto.anchor_top = 0.85
	texto.anchor_bottom = 0.99
	texto.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	texto.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	texto.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	texto.add_theme_font_size_override("font_size", 22)
	camada.add_child(texto)
	cena.add_child(camada)
	return camada
