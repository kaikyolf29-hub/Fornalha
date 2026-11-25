extends Node
## Teste automático da Fornalha (autoload "TesteFornalha"). Só liga com
## `-- --fornalha-teste <pasta>`: anda, pula, ataca (também andando), tira capturas,
## confere o movimento (árvore de animação, pés no chão parado, olhar) e escreve
## relatorio.json. No jogo normal não faz nada.

var ativo := false
var pasta := ""
var duracao := 9.0
var _t := 0.0
var _quadros := 0
var _fps: Array[float] = []
var _capturas: Array[String] = []
var _jogador: Node3D
var _inicio := Vector3.ZERO
var _total_inimigos := 0
var _perseguiram := {}
var _marcos := {}
var _pes: Array[float] = []        # pior pé (com IK) em cada quadro parado, em metros
var _pes_sem_ik: Array[float] = [] # o mesmo pé sem o IK (a pose da animação contra o chão)
var _atacou_andando := false
var _olhou := false
var _parado_ha := 0.0
const CAPTURAS := [1.2, 3.0, 4.6, 6.4, 8.2]


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var i := args.find("--fornalha-teste")
	if i == -1:
		return
	ativo = true
	pasta = args[i + 1] if args.size() > i + 1 else "user://teste_fornalha"
	var j := args.find("--segundos")
	if j != -1 and args.size() > j + 1:
		duracao = float(args[j + 1])
	DirAccess.make_dir_recursive_absolute(pasta)
	process_mode = Node.PROCESS_MODE_ALWAYS
	print("FORNALHA_TESTE inicio ", pasta)


func _uma_vez(nome: String, quando: float) -> bool:
	if _t >= quando and not _marcos.has(nome):
		_marcos[nome] = true
		return true
	return false


func _process(dt: float) -> void:
	if not ativo:
		return
	_t += dt
	_quadros += 1
	if _quadros > 5:
		_fps.append(Engine.get_frames_per_second())
	if _jogador == null:
		_jogador = get_tree().get_first_node_in_group("jogador")
		if _jogador:
			_inicio = _jogador.global_position
			_total_inimigos = get_tree().get_nodes_in_group("inimigos").size()
			if _jogador.get("movimento"):
				_jogador.movimento.medir = true
	for inimigo in get_tree().get_nodes_in_group("inimigos"):
		if inimigo.get("estado") in [1, 2]:
			_perseguiram[inimigo.name] = true
	if _jogador:
		# roteiro: anda para a frente, pula, vira, ataca
		if _t > 0.8 and _t < 3.6:
			_jogador.entrada_teste = Vector2(0, -1)
		elif _t >= 3.6 and _t < 4.4:
			_jogador.entrada_teste = Vector2(0.6, -0.8)
		else:
			_jogador.entrada_teste = Vector2.ZERO
		if _uma_vez("pulo", 2.0):
			_jogador.pular()
		# golpe andando: a camada de cima ataca e as pernas seguem a locomoção
		if _uma_vez("ataque_andando", 1.15):
			_jogador.atacar()
		_conferir_movimento(dt)
		for k in [4.6, 5.6, 6.6, 7.6]:
			if _uma_vez("ataque%s" % k, k):
				_jogador.atacar()
	for k in CAPTURAS.size():
		if _uma_vez("captura%d" % k, CAPTURAS[k]):
			_capturar(k + 1)
	if _t >= duracao:
		_terminar()


func _conferir_movimento(dt: float) -> void:
	var mov = _jogador.get("movimento")
	if mov == null:
		return
	var e: Dictionary = mov.estado_atual()
	if e["cima"] > 0.5 and e["velocidade"] > 0.6 and e["pernas_do_golpe"] < 0.35:
		_atacou_andando = true
	if e["olhar"] > 0.5:
		_olhou = true
	# pés no chão: só quadros parados de verdade (0,3 s sem andar nem agir, o IK já assentado), no chão
	# e com o IK inteiro; entram o começo (antes de andar) e o fim (depois dos golpes)
	var parado: bool = Vector2(_jogador.velocity.x, _jogador.velocity.z).length() < 0.05 and _jogador.is_on_floor()
	parado = parado and e["acao_cima"] == "" and e["acao_corpo"] == "" and e["peso_ik"] > 0.98
	_parado_ha = _parado_ha + dt if parado else 0.0
	if _parado_ha > 0.3 and mov.medida.has("com_ik"):
		var com: Array = mov.medida["com_ik"]
		var sem: Array = mov.medida["sem_ik"]
		_pes.append(maxf(absf(com[0]), absf(com[1])))
		_pes_sem_ik.append(maxf(absf(sem[0]), absf(sem[1])))


static func _cm(lista: Array[float]) -> Dictionary:
	if lista.is_empty():
		return {"amostras": 0}
	var soma := 0.0
	for v in lista:
		soma += v
	return {"amostras": lista.size(), "max": snappedf(lista.max() * 100.0, 0.01), "media": snappedf(soma / lista.size() * 100.0, 0.01)}


func _capturar(n: int) -> void:
	# sem tela (modo headless) não há imagem para capturar
	if DisplayServer.get_name() == "headless":
		return
	var tex := get_viewport().get_texture()
	if tex == null:
		return
	var img := tex.get_image()
	if img == null or img.is_empty():
		return
	var caminho := pasta.path_join("captura_%02d.png" % n)
	if img.save_png(caminho) == OK:
		_capturas.append(caminho)


## Uma foto de cada ponto do mapa (bancada de mapa), com o FPS ali: a IA olha e ajusta.
func _fotos_do_mapa() -> Array:
	var fotos := []
	var pontos := get_tree().get_nodes_in_group("foto_mapa")
	if pontos.is_empty() or DisplayServer.get_name() == "headless":
		return fotos
	var anterior := get_viewport().get_camera_3d()
	var escondidas := []  # a foto do mapa sai sem a interface do jogo
	for c in get_tree().current_scene.find_children("*", "CanvasLayer", true, false):
		if (c as CanvasLayer).visible:
			(c as CanvasLayer).visible = false
			escondidas.append(c)
	var cam := Camera3D.new()
	cam.fov = 70.0
	cam.far = 3000.0
	get_tree().current_scene.add_child(cam)
	for p in pontos:
		cam.global_transform = (p as Node3D).global_transform
		cam.make_current()
		var soma := 0.0
		var compat := RenderingServer.get_current_rendering_method() == "gl_compatibility"
		var quadros := 8 if compat else 24  # no Forward+, a luz global (SDFGI) e a névoa precisam assentar
		for i in quadros:
			await get_tree().process_frame
			if i >= quadros / 3:
				soma += Engine.get_frames_per_second()
		var img := get_viewport().get_texture().get_image()
		var nome := String(p.name).trim_prefix("Foto_")
		var caminho := pasta.path_join("mapa_%s.png" % nome)
		if img and not img.is_empty() and img.save_png(caminho) == OK:
			fotos.append({"id": nome, "imagem": caminho, "fps": snappedf(soma / float(quadros - quadros / 3), 0.1)})
	cam.queue_free()
	for c in escondidas:
		c.visible = true
	if anterior:
		anterior.make_current()
	return fotos


## A primeira cena curta do projeto (res://Cutscenes), com uma foto de cada linha.
func _cena_curta() -> Dictionary:
	var cenas := get_node_or_null("/root/CenasCurtas")
	var dir := DirAccess.open("res://Cutscenes")
	if cenas == null or dir == null:
		return {}
	var achada := ""
	for arq in dir.get_files():
		if arq.ends_with(".cena.json"):
			achada = arq.trim_suffix(".cena.json")
			break
	if achada == "":
		return {}
	var fotos := []
	var tela := DisplayServer.get_name() != "headless"
	cenas.tocar(achada)
	var n := 0
	var limite := 0.0
	while cenas.tocando and limite < 40.0:
		await get_tree().process_frame
		limite += get_process_delta_time()
		var linhas: Array = cenas.relatorio.get("linhas", [])
		if tela and linhas.size() > n:
			n = linhas.size()
			for i in 6:
				await get_tree().process_frame
			var img := get_viewport().get_texture().get_image()
			var caminho := pasta.path_join("cena_%s_%02d.png" % [achada, n])
			if img and not img.is_empty() and img.save_png(caminho) == OK:
				fotos.append(caminho)
	var r: Dictionary = cenas.relatorio.duplicate(true)
	r["terminou"] = not cenas.tocando
	r["fotos"] = fotos
	r["jogador_voltou"] = _jogador == null or not _jogador.get("em_cena")
	return r


func _terminar() -> void:
	ativo = false
	var cena_curta := await _cena_curta()
	var fotos_mapa := await _fotos_do_mapa()
	var media := 0.0
	for f in _fps:
		media += f
	media = media / max(_fps.size(), 1)
	var rel := {
		"ok": true,
		"segundos": _t,
		"quadros": _quadros,
		"fps_medio": snappedf(media, 0.1),
		"cena": get_tree().current_scene.scene_file_path if get_tree().current_scene else "",
		"engine": Engine.get_version_info(),
		"capturas": _capturas,
		"fotos_mapa": fotos_mapa,
		"cena_curta": cena_curta,
		"jogador": {},
		"inimigos": {"total": _total_inimigos, "vivos": 0, "perseguiram": _perseguiram.size()},
	}
	if _jogador:
		var andou := _jogador.global_position - _inicio
		andou.y = 0.0
		rel["jogador"] = {"andou_m": snappedf(andou.length(), 0.01), "no_chao": _jogador.is_on_floor(), "vida": _jogador.vida, "caiu_do_mapa": _jogador.global_position.y < -20.0}
		var mov = _jogador.get("movimento")
		var ciclos := {}
		if mov:
			for nome in mov.ciclos:
				ciclos[nome] = snappedf(mov.ciclos[nome]["v"], 0.01)
		rel["movimento"] = {
			"arvore": mov != null and mov.arvore != null and mov.arvore is AnimationTree,
			"ik_pes": mov != null and mov._ik != null and mov._ik.is_class("TwoBoneIK3D"),
			"olhar": mov != null and not mov._olhar.is_empty(),
			"olhou": _olhou,
			"atacou_andando": _atacou_andando,
			"pes_parado_cm": _cm(_pes),
			"pes_sem_ik_cm": _cm(_pes_sem_ik),
			"velocidade_dos_ciclos": ciclos,
		}
	var vivos := 0
	for inimigo in get_tree().get_nodes_in_group("inimigos"):
		if inimigo.get("estado") != 3:
			vivos += 1
	rel["inimigos"]["vivos"] = vivos
	var f := FileAccess.open(pasta.path_join("relatorio.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(rel, "  "))
	f.close()
	print("FORNALHA_TESTE fim ", JSON.stringify(rel))
	# fecha a cena antes de sair, para cada nó soltar o que carregou
	get_tree().current_scene.queue_free()
	await get_tree().process_frame
	get_tree().quit(0)
