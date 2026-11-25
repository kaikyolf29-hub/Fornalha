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
	var mapa: Dictionary = m.get("mapa", {})
	var mundo := _mapa(mapa, w_info) if mapa.has("pasta") else _mundo(w_info)
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
	# Sons.falar(id, …) acha o personagem mesmo com o nome trocado (inimigo_01…)
	raiz.set_meta("fornalha_id", p["id"])
	raiz.add_to_group("personagens", true)
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


## Mundo da bancada de mapa (World/mapa/mapa.json): terreno com a pintura das camadas, colisão pelo
## mapa de altura, água, construções, vegetação em MultiMesh por bloco (com distância de corte), luz e
## névoa pela hora e pelo clima, paredes invisíveis na borda e os pontos de foto de cada região.
const ALCANCE_VEG := {"arvore": 420.0, "arbusto": 140.0, "pedra": 240.0}
const BLOCO_VEG := 128.0


func _mapa(w: Dictionary, w_antigo: Dictionary) -> String:
	var pasta: String = w["pasta"]
	var info = JSON.parse_string(FileAccess.get_file_as_string(pasta.path_join("mapa.json")))
	if typeof(info) != TYPE_DICTIONARY:
		erros.append("mapa.json ilegível em %s" % pasta)
		return _mundo(w_antigo)
	var arqs: Dictionary = info.get("arquivos", {})
	var lado: float = info.get("tamanho_m", 512.0)
	var raiz := Node3D.new()
	raiz.name = "Mundo"
	# terreno
	var cena_t = load(pasta.path_join(arqs.get("terreno", "terreno.glb")))
	if cena_t == null:
		erros.append("terreno do mapa não importado")
	else:
		var terreno: Node3D = cena_t.instantiate()
		terreno.name = "Terreno"
		raiz.add_child(terreno)
		_dono(terreno, raiz)
		var mat := ShaderMaterial.new()
		mat.shader = load("res://Scripts/fornalha/terreno.gdshader")
		mat.set_shader_parameter("pintura", load(pasta.path_join(arqs.get("pintura", "pintura.png"))))
		mat.set_shader_parameter("tamanho_m", lado)
		var cores: Dictionary = info.get("cores_camadas", {})
		var camadas: Array = info.get("camadas", [])
		var com := Vector4.ZERO
		for i in camadas.size():
			var nome: String = camadas[i]
			if cores.has(nome):
				mat.set_shader_parameter("cor_%d" % i, Color(cores[nome]))
			var tex: Dictionary = w.get("texturas", {}).get(nome, {})
			if tex.has("cor") and ResourceLoader.exists(tex["cor"]):
				mat.set_shader_parameter("tex_%d" % i, load(tex["cor"]))
				if tex.has("normal") and ResourceLoader.exists(tex["normal"]):
					mat.set_shader_parameter("nrm_%d" % i, load(tex["normal"]))
				com[i] = 1.0
		mat.set_shader_parameter("com_textura", com)
		for mi in terreno.find_children("*", "MeshInstance3D", true, false):
			(mi as MeshInstance3D).material_override = mat
	# colisão pelo mapa de altura (leve para a física, sem a malha inteira)
	var n: int = int(info.get("pontos_por_lado", 0))
	var res: float = info.get("resolucao_m", 1.0)
	var dados := FileAccess.get_file_as_bytes(pasta.path_join(arqs.get("relevo_r32", "relevo.r32"))).to_float32_array()
	if n > 1 and dados.size() == n * n:
		if not is_equal_approx(res, 1.0):
			for i in dados.size():
				dados[i] /= res
		var forma := HeightMapShape3D.new()
		forma.map_width = n
		forma.map_depth = n
		forma.map_data = dados
		var arq_col := pasta.path_join("colisao.res")
		if ResourceSaver.save(forma, arq_col, ResourceSaver.FLAG_CHANGE_PATH) != OK:
			erros.append("não consegui salvar a colisão do terreno")
		var chao := StaticBody3D.new()
		chao.name = "Chao"
		chao.collision_layer = CAMADA_MUNDO
		var col := CollisionShape3D.new()
		col.name = "Relevo"
		col.shape = forma
		col.scale = Vector3.ONE * res
		chao.add_child(col)
		raiz.add_child(chao)
		_dono(chao, raiz)
		_dono(col, raiz)
	else:
		erros.append("relevo.r32 com tamanho errado (%d valores, esperava %d)" % [dados.size(), n * n])
	# água e construções
	if arqs.get("agua", "") != "":
		var cena_a = load(pasta.path_join(arqs["agua"]))
		if cena_a:
			var agua: Node3D = cena_a.instantiate()
			agua.name = "Agua"
			var mat_a := ShaderMaterial.new()
			mat_a.shader = load("res://Scripts/fornalha/agua.gdshader")
			for mi in agua.find_children("*", "MeshInstance3D", true, false):
				(mi as MeshInstance3D).material_override = mat_a
				(mi as MeshInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			raiz.add_child(agua)
			_dono(agua, raiz)
	if arqs.get("estruturas", "") != "":
		var cena_e = load(pasta.path_join(arqs["estruturas"]))
		if cena_e:
			var est: Node3D = cena_e.instantiate()
			est.name = "Construcoes"
			raiz.add_child(est)
			_dono(est, raiz)
	_vegetacao(raiz, pasta, arqs.get("espalhamento", "espalhamento.json"), lado)
	# paredes invisíveis na borda (o relevo fecha o mapa, a parede garante)
	var borda := StaticBody3D.new()
	borda.name = "Borda"
	borda.collision_layer = CAMADA_MUNDO
	raiz.add_child(borda)
	_dono(borda, raiz)
	for i in 4:
		var c := CollisionShape3D.new()
		var caixa := BoxShape3D.new()
		var eixo_x := i < 2
		caixa.size = Vector3(2.0, 600.0, lado + 4.0) if eixo_x else Vector3(lado + 4.0, 600.0, 2.0)
		c.shape = caixa
		var s := -1.0 if i % 2 == 0 else 1.0
		c.position = Vector3(s * (lado / 2.0 + 1.0), 0.0, 0.0) if eixo_x else Vector3(0.0, 0.0, s * (lado / 2.0 + 1.0))
		borda.add_child(c)
		_dono(c, raiz)
	# pontos de foto (o teste tira uma foto de cada)
	for f in info.get("fotos", []):
		var mk := Marker3D.new()
		mk.name = "Foto_%s" % f["id"]
		var pos := Vector3(f["pos"][0], f["pos"][1], f["pos"][2])
		var alvo := Vector3(f["olha"][0], f["olha"][1], f["olha"][2])
		mk.transform = Transform3D(Basis.looking_at(alvo - pos, Vector3.UP), pos)
		mk.add_to_group("foto_mapa", true)
		raiz.add_child(mk)
		_dono(mk, raiz)
	_luz_do_mapa(raiz, info.get("luz", {}), info.get("hora", "tarde"), w_antigo.get("ceu", ""))
	return _salvar(raiz, w.get("cena", "res://World/mundo.tscn"))


func _vegetacao(raiz: Node3D, pasta: String, arquivo: String, lado: float) -> void:
	var esp = JSON.parse_string(FileAccess.get_file_as_string(pasta.path_join(arquivo)))
	if typeof(esp) != TYPE_DICTIONARY:
		erros.append("espalhamento.json ilegível")
		return
	var veg := Node3D.new()
	veg.name = "Vegetacao"
	raiz.add_child(veg)
	_dono(veg, raiz)
	var troncos := StaticBody3D.new()
	troncos.name = "Troncos"
	troncos.collision_layer = CAMADA_MUNDO
	veg.add_child(troncos)
	_dono(troncos, raiz)
	var tipos: Dictionary = esp.get("tipos", {})
	var inst: Dictionary = esp.get("instancias", {})
	var script_veg := _script("res://Scripts/fornalha/vegetacao.gd")
	var cil := CylinderShape3D.new()
	cil.radius = 0.32
	cil.height = 4.0
	var cenas := {}  # "arquivo.glb#no": o GLB carrega uma vez e cada variante é um nó dele
	for tipo in tipos:
		var malhas := []
		for ref in tipos[tipo]:
			var partes_ref: PackedStringArray = String(ref).split("#")
			var arq := partes_ref[0]
			if not cenas.has(arq):
				var cena = load(pasta.path_join(arq))
				cenas[arq] = cena.instantiate() if cena else null
			var raiz_glb: Node = cenas[arq]
			var malha: Mesh = null
			if raiz_glb:
				var no: Node = raiz_glb.find_child(partes_ref[1], true, false) if partes_ref.size() > 1 else raiz_glb
				var achou: Array = [no] if no is MeshInstance3D else (no.find_children("*", "MeshInstance3D", true, false) if no else [])
				if not achou.is_empty():
					malha = (achou[0] as MeshInstance3D).mesh
			if malha == null:
				erros.append("vegetação não importada: %s" % ref)
			malhas.append(malha)
		var grupos := {}
		for it in inst.get(tipo, []):
			var v := int(it[0])
			if v < 0 or v >= malhas.size() or malhas[v] == null:
				continue
			var bx := int(floor((float(it[1]) + lado / 2.0) / BLOCO_VEG))
			var bz := int(floor((float(it[3]) + lado / 2.0) / BLOCO_VEG))
			var chave := "%d_%d_%d" % [v, bx, bz]
			if not grupos.has(chave):
				grupos[chave] = []
			grupos[chave].append(it)
		for chave in grupos:
			var lista: Array = grupos[chave]
			var partes: PackedStringArray = chave.split("_")
			var centro := Vector3((int(partes[1]) + 0.5) * BLOCO_VEG - lado / 2.0, 0.0, (int(partes[2]) + 0.5) * BLOCO_VEG - lado / 2.0)
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = malhas[int(partes[0])]
			mm.instance_count = lista.size()
			var dados := PackedFloat32Array()
			dados.resize(lista.size() * 12)
			for i in lista.size():
				var it: Array = lista[i]
				var b := Basis(Vector3.UP, float(it[4])).scaled(Vector3.ONE * float(it[5]))
				var pos := Vector3(float(it[1]), float(it[2]), float(it[3]))
				var o := pos - centro
				var linha := [b.x.x, b.y.x, b.z.x, o.x, b.x.y, b.y.y, b.z.y, o.y, b.x.z, b.y.z, b.z.z, o.z]
				for k in 12:
					dados[i * 12 + k] = linha[k]
				if tipo == "arvore":
					var c := CollisionShape3D.new()
					c.shape = cil
					c.position = pos + Vector3(0, 2.0, 0)
					troncos.add_child(c)
					_dono(c, raiz)
			var mmi := MultiMeshInstance3D.new()
			mmi.name = "%s_%s" % [tipo, chave]
			mmi.multimesh = mm
			if script_veg:
				mmi.set_script(script_veg)
				mmi.set("transformacoes", dados)
			mmi.position = centro
			mmi.visibility_range_end = ALCANCE_VEG.get(tipo, 300.0)
			mmi.visibility_range_end_margin = 25.0
			mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			if tipo != "arvore":  # planta baixa e pedra sem sombra: a sombra custa mais que ela
				mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			veg.add_child(mmi)
			_dono(mmi, raiz)
	for arq in cenas:
		if cenas[arq]:
			cenas[arq].free()


func _luz_do_mapa(raiz: Node3D, luz: Dictionary, hora: String, hdri: String) -> void:
	var sol := DirectionalLight3D.new()
	sol.name = "Sol"
	sol.rotation_degrees = Vector3(-float(luz.get("sol_elevacao", 35.0)), float(luz.get("sol_azimute", 35.0)), 0.0)
	sol.light_color = Color(luz.get("sol_cor", "#ffe2b8"))
	sol.light_energy = float(luz.get("sol_energia", 1.5))
	sol.shadow_enabled = true
	sol.shadow_blur = 1.5
	sol.light_angular_distance = 0.6
	sol.directional_shadow_max_distance = 220.0
	raiz.add_child(sol)
	_dono(sol, raiz)
	var ambiente := WorldEnvironment.new()
	ambiente.name = "Ambiente"
	var env := Environment.new()
	var ceu := Sky.new()
	if true:  # o céu segue a hora do plano (o HDRI do pacote tem chão e árvores de outro lugar)
		var mat := ProceduralSkyMaterial.new()
		mat.sky_top_color = Color(luz.get("ceu_topo", "#4a72ad"))
		mat.sky_horizon_color = Color(luz.get("ceu_horizonte", "#e3cfb4"))
		# abaixo do horizonte, a mesma bruma do horizonte (sem chão escuro aparecendo além da borda)
		mat.ground_horizon_color = Color(luz.get("ceu_horizonte", "#e3cfb4"))
		mat.ground_bottom_color = Color(luz.get("nevoa_cor", "#d8cdbd")).darkened(0.15)
		ceu.sky_material = mat
	env.background_mode = Environment.BG_SKY
	env.sky = ceu
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.ambient_light_energy = 0.35 if hora == "noite" else 1.0
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.ssao_enabled = true
	env.ssao_radius = 1.2
	env.ssil_enabled = true
	env.sdfgi_enabled = true
	env.glow_enabled = true
	env.glow_intensity = 0.35
	env.fog_enabled = true
	env.fog_light_color = Color(luz.get("nevoa_cor", "#d8cdbd"))
	env.fog_density = float(luz.get("nevoa_densidade", 0.004))
	env.fog_sky_affect = 0.25
	env.fog_height = float(luz.get("nevoa_altura", 0.0))
	env.fog_height_density = 0.04
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = float(luz.get("nevoa_densidade", 0.004)) * 0.5
	env.adjustment_enabled = true
	env.adjustment_contrast = 1.05
	env.adjustment_saturation = 1.05
	ambiente.environment = env
	raiz.add_child(ambiente)
	_dono(ambiente, raiz)


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
