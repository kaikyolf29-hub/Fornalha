extends Node
## Teste automático da Fornalha (autoload "TesteFornalha"). Só liga com
## `-- --fornalha-teste <pasta>`: anda, pula, ataca, tira capturas e escreve
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
		for k in [4.6, 5.6, 6.6, 7.6]:
			if _uma_vez("ataque%s" % k, k):
				_jogador.atacar()
	for k in CAPTURAS.size():
		if _uma_vez("captura%d" % k, CAPTURAS[k]):
			_capturar(k + 1)
	if _t >= duracao:
		_terminar()


func _capturar(n: int) -> void:
	var tex := get_viewport().get_texture()
	if tex == null:
		return
	var img := tex.get_image()
	if img == null or img.is_empty():
		return
	var caminho := pasta.path_join("captura_%02d.png" % n)
	if img.save_png(caminho) == OK:
		_capturas.append(caminho)


func _terminar() -> void:
	ativo = false
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
		"jogador": {},
		"inimigos": {"total": _total_inimigos, "vivos": 0, "perseguiram": _perseguiram.size()},
	}
	if _jogador:
		var andou := _jogador.global_position - _inicio
		andou.y = 0.0
		rel["jogador"] = {"andou_m": snappedf(andou.length(), 0.01), "no_chao": _jogador.is_on_floor(), "vida": _jogador.vida, "caiu_do_mapa": _jogador.global_position.y < -20.0}
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
