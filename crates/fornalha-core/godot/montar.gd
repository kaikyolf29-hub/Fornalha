extends SceneTree
## Monta as cenas do jogo a partir de res://.fornalha/cena.json (escrito pela
## Fornalha): personagem jogável, inimigos, mundo e a cena principal. Roda com
## `--headless --script res://Scripts/fornalha/montar.gd` depois do `--import`.

const MANIFESTO := "res://.fornalha/cena.json"
const CAMADA_MUNDO := 1
const CAMADA_JOGADOR := 2
const CAMADA_INIMIGOS := 4
var erros: Array[String] = []
var feitas: Array[String] = []


func _init() -> void:
	var m = JSON.parse_string(FileAccess.get_file_as_string(MANIFESTO))
	if typeof(m) != TYPE_DICTIONARY:
		printerr("FORNALHA_MONTAR erro: manifesto ilegível")
		quit(1)
		return
	var cenas_personagens := {}
	for p in m.get("personagens", []):
		var cena := _personagem(p)
		if cena != "":
			cenas_personagens[p["id"]] = cena
	var w_info: Dictionary = m.get("mundo", {})
	w_info["ceu"] = m.get("ceu", "")
	var mundo := _mundo(w_info)
	_principal(m, mundo, cenas_personagens)
	print("FORNALHA_MONTAR ", JSON.stringify({"ok": erros.is_empty(), "cenas": feitas, "erros": erros}))
	quit(0 if erros.is_empty() else 1)


func _salvar(raiz: Node, caminho: String) -> String:
	var pacote := PackedScene.new()
	var r := pacote.pack(raiz)
	if r != OK:
		erros.append("não consegui empacotar %s (%d)" % [caminho, r])
		return ""
	r = ResourceSaver.save(pacote, caminho)
	if r != OK:
		erros.append("não consegui salvar %s (%d)" % [caminho, r])
		return ""
	feitas.append(caminho)
	raiz.free()
	return caminho


## Carrega um script e confere se ele compila (script com erro vira nó sem script).
func _script(caminho: String) -> Script:
	var s = load(caminho)
	if s == null or not (s as Script).can_instantiate():
		erros.append("o script %s não compila (veja os erros da engine)" % caminho)
		return null
	return s


func _dono(no: Node, raiz: Node) -> void:
	no.owner = raiz


func _personagem(p: Dictionary) -> String:
	var cena_modelo = load(p["modelo"])
	if cena_modelo == null:
		erros.append("modelo não importado: %s" % p["modelo"])
		return ""
	var altura: float = p.get("altura", 1.8)
	var jogador: bool = p.get("tipo", "inimigo") == "jogador"
	var raiz := CharacterBody3D.new()
	raiz.name = p["id"]
	var script := _script("res://Scripts/fornalha/%s.gd" % ("jogador" if jogador else "inimigo"))
	if script == null:
		raiz.free()
		return ""
	raiz.set_script(script)
	raiz.collision_layer = CAMADA_JOGADOR if jogador else CAMADA_INIMIGOS
	raiz.collision_mask = CAMADA_MUNDO | (CAMADA_INIMIGOS if jogador else CAMADA_JOGADOR)
	var modelo: Node3D = cena_modelo.instantiate()
	modelo.name = "Modelo"
	raiz.add_child(modelo)
	_dono(modelo, raiz)
	var col := CollisionShape3D.new()
	col.name = "Colisao"
	var capsula := CapsuleShape3D.new()
	capsula.radius = clamp(altura * 0.17, 0.2, 0.5)
	capsula.height = altura
	col.shape = capsula
	col.position.y = altura / 2.0
	raiz.add_child(col)
	_dono(col, raiz)
	if jogador:
		var braco := SpringArm3D.new()
		braco.name = "BracoCamera"
		braco.position.y = altura * 0.85
		braco.rotation.x = -0.32
		braco.spring_length = 3.4
		braco.margin = 0.25
		# esfera em vez de raio: a câmera não atravessa quina de parede
		var esfera := SphereShape3D.new()
		esfera.radius = 0.22
		braco.shape = esfera
		braco.collision_mask = CAMADA_MUNDO
		raiz.add_child(braco)
		_dono(braco, raiz)
		var cam := Camera3D.new()
		cam.name = "Camera"
		cam.fov = 65.0
		cam.near = 0.08
		# por cima do ombro (como nos jogos de ação em terceira pessoa): perto de parede a câmera
		# fica ao lado da cabeça, não dentro dela
		cam.position.x = 0.45
		braco.add_child(cam)
		_dono(cam, raiz)
	else:
		raiz.set("vida_max", p.get("vida", 100))
		raiz.set("dano", p.get("dano", 10))
	return _salvar(raiz, p["cena"])


func _mundo(w: Dictionary) -> String:
	var raiz := Node3D.new()
	raiz.name = "Mundo"
	if w.has("modelo"):
		var cena = load(w["modelo"])
		if cena == null:
			erros.append("mundo não importado: %s" % w["modelo"])
		else:
			var blocos: Node3D = cena.instantiate()
			blocos.name = "Blockout"
			raiz.add_child(blocos)
			_dono(blocos, raiz)
	var sol := DirectionalLight3D.new()
	sol.name = "Sol"
	sol.rotation_degrees = Vector3(-42, -35, 0)
	sol.light_energy = 1.6
	sol.shadow_enabled = true
	sol.shadow_blur = 1.5
	sol.light_angular_distance = 0.6
	sol.directional_shadow_max_distance = 120.0
	raiz.add_child(sol)
	_dono(sol, raiz)
	var ambiente := WorldEnvironment.new()
	ambiente.name = "Ambiente"
	var env := Environment.new()
	var ceu := Sky.new()
	var hdri: String = w.get("ceu", "")
	if hdri != "" and ResourceLoader.exists(hdri):
		# céu HDRI de verdade (pacote CC0): ilumina e reflete nos metais
		var pano := PanoramaSkyMaterial.new()
		pano.panorama = load(hdri)
		ceu.sky_material = pano
	else:
		var mat := ProceduralSkyMaterial.new()
		mat.sky_top_color = Color("#3d5f8f")
		mat.sky_horizon_color = Color("#c9b49a")
		mat.ground_horizon_color = Color("#6b5a48")
		ceu.sky_material = mat
	env.background_mode = Environment.BG_SKY
	env.sky = ceu
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.0
	# qualidade de jogo moderno (Forward+; no modo compatibilidade a engine ignora o que não tem)
	env.ssao_enabled = true
	env.ssao_radius = 1.2
	env.ssil_enabled = true
	env.sdfgi_enabled = true
	env.glow_enabled = true
	env.glow_intensity = 0.35
	env.fog_enabled = true
	env.fog_density = 0.003
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = 0.008
	env.adjustment_enabled = true
	env.adjustment_contrast = 1.05
	env.adjustment_saturation = 1.05
	ambiente.environment = env
	raiz.add_child(ambiente)
	_dono(ambiente, raiz)
	return _salvar(raiz, w.get("cena", "res://World/mundo.tscn"))


func _principal(m: Dictionary, mundo: String, personagens: Dictionary) -> void:
	var raiz := Node3D.new()
	raiz.name = "Principal"
	var sp := _script("res://Scripts/fornalha/principal.gd")
	if sp:
		raiz.set_script(sp)
	raiz.set("musica", m.get("musica", ""))
	if mundo != "":
		var w: Node = load(mundo).instantiate()
		raiz.add_child(w)
		_dono(w, raiz)
	var spawn: Array = m.get("spawn_jogador", [0, 0.2, 0])
	var jogador_id: String = m.get("jogador", "")
	if personagens.has(jogador_id):
		var j: Node3D = load(personagens[jogador_id]).instantiate()
		j.position = Vector3(spawn[0], spawn[1] + 0.1, spawn[2])
		raiz.add_child(j)
		_dono(j, raiz)
	var inimigos: Array = m.get("inimigos", [])
	var pontos: Array = m.get("spawn_inimigos", [])
	if m.get("inimigo_perto", false) and not inimigos.is_empty():
		pontos = [[spawn[0], spawn[1], spawn[2] - 7.0]] + pontos
	if not inimigos.is_empty():
		for i in pontos.size():
			var id: String = inimigos[i % inimigos.size()]
			if not personagens.has(id):
				continue
			var e: Node3D = load(personagens[id]).instantiate()
			e.name = "%s_%02d" % [id, i]
			e.position = Vector3(pontos[i][0], pontos[i][1] + 0.1, pontos[i][2])
			raiz.add_child(e)
			_dono(e, raiz)
	var hud := CanvasLayer.new()
	hud.name = "HUD"
	var sh := _script("res://Scripts/fornalha/hud.gd")
	if sh:
		hud.set_script(sh)
	raiz.add_child(hud)
	_dono(hud, raiz)
	_salvar(raiz, m.get("principal", "res://principal.tscn"))
