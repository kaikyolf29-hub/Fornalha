extends RefCounted
## Física dos personagens da Fornalha (Godot 4.6 / Erethea):
## - capa, tecido e cabelo com ossos "capa_1..4" balançam por mola (SpringBoneSimulator3D);
## - ao morrer, o corpo cai pela física (ragdoll com PhysicalBoneSimulator3D).
## Gerado pela Fornalha; pode editar à vontade.

const RAGDOLL := {
	# osso: [filho que dá o comprimento, raio, massa]
	"pelvis": ["spine_01", 0.13, 14.0],
	"spine_01": ["spine_03", 0.14, 10.0],
	"spine_03": ["neck_01", 0.15, 10.0],
	"head": ["", 0.11, 5.0],
	"upperarm_l": ["lowerarm_l", 0.055, 3.0],
	"upperarm_r": ["lowerarm_r", 0.055, 3.0],
	"lowerarm_l": ["hand_l", 0.045, 2.0],
	"lowerarm_r": ["hand_r", 0.045, 2.0],
	"thigh_l": ["calf_l", 0.075, 8.0],
	"thigh_r": ["calf_r", 0.075, 8.0],
	"calf_l": ["foot_l", 0.06, 4.0],
	"calf_r": ["foot_r", 0.06, 4.0],
}


static func esqueleto(no: Node) -> Skeleton3D:
	if no is Skeleton3D:
		return no
	for f in no.get_children():
		var s := esqueleto(f)
		if s:
			return s
	return null


## Prepara a física do personagem. Devolve o simulador do ragdoll (ou null).
static func preparar(modelo: Node3D, corpo: PhysicsBody3D) -> PhysicalBoneSimulator3D:
	fios(modelo)
	materiais(modelo)
	var sk := esqueleto(modelo)
	if sk == null:
		return null
	_capa(sk)
	return _ragdoll(sk, corpo)


static func _capa(sk: Skeleton3D) -> void:
	if sk.find_bone("capa_1") < 0 or sk.find_bone("capa_4") < 0:
		return
	var mola := SpringBoneSimulator3D.new()
	mola.name = "MolaDaCapa"
	sk.add_child(mola)
	mola.set_setting_count(1)
	mola.set_root_bone_name(0, "capa_1")
	mola.set_end_bone_name(0, "capa_4")
	mola.set_extend_end_bone(0, true)
	mola.set_stiffness(0, 0.55)
	mola.set_drag(0, 0.45)
	mola.set_gravity(0, 1.6)
	mola.set_gravity_direction(0, Vector3(0, -1, 0))
	mola.set_radius(0, 0.05)


static func _ragdoll(sk: Skeleton3D, corpo: PhysicsBody3D) -> PhysicalBoneSimulator3D:
	if sk.find_bone("pelvis") < 0:
		return null
	var sim := PhysicalBoneSimulator3D.new()
	sim.name = "Ragdoll"
	sk.add_child(sim)
	for osso in RAGDOLL:
		var i := sk.find_bone(osso)
		if i < 0:
			continue
		var dados: Array = RAGDOLL[osso]
		var comprimento := 0.22
		var filho: String = dados[0]
		if filho != "" and sk.find_bone(filho) >= 0:
			comprimento = sk.get_bone_global_rest(i).origin.distance_to(sk.get_bone_global_rest(sk.find_bone(filho)).origin)
		var pb := PhysicalBone3D.new()
		pb.name = "Fisico_" + osso
		pb.bone_name = osso
		pb.mass = dados[2]
		pb.joint_type = PhysicalBone3D.JOINT_TYPE_CONE
		pb.friction = 0.8
		var forma := CollisionShape3D.new()
		var capsula := CapsuleShape3D.new()
		capsula.radius = dados[1]
		capsula.height = max(comprimento, capsula.radius * 2.0 + 0.01)
		forma.shape = capsula
		forma.position = Vector3(0, comprimento * 0.5, 0)
		pb.add_child(forma)
		sim.add_child(pb)
		pb.global_transform = sk.global_transform * sk.get_bone_global_pose(i)
	if corpo:
		sim.physical_bones_add_collision_exception(corpo.get_rid())
	return sim


## Morte com física: a animação para e o corpo cai, com um empurrão na direção do golpe.
static func cair(sim: PhysicalBoneSimulator3D, anim: AnimationPlayer, empurrao := Vector3.ZERO) -> bool:
	if sim == null:
		return false
	if anim:
		anim.stop()
	sim.physical_bones_start_simulation()
	if empurrao != Vector3.ZERO:
		for pb in sim.get_children():
			if pb is PhysicalBone3D and String(pb.bone_name) in ["spine_03", "pelvis"]:
				pb.apply_central_impulse(empurrao)
	return true


static var _render := ""


## O visual do jogo pela bíblia (game.project.json → guia_visual.render): "realista" (padrão) ou "anime".
static func render() -> String:
	if _render == "":
		_render = "realista"
		var b = JSON.parse_string(FileAccess.get_file_as_string("res://game.project.json")) if FileAccess.file_exists("res://game.project.json") else null
		if typeof(b) == TYPE_DICTIONARY and typeof(b.get("guia_visual")) == TYPE_DICTIONARY:
			var r := String(b["guia_visual"].get("render", "realista")).to_lower()
			if r in ["anime", "toon", "cel", "cel_shading"]:
				_render = "anime"
	return _render


## Cabelo fio a fio (nível Máximo): a malha <id>_hair_strands traz cada fio como uma cadeia de arestas
## (LINES), com a largura do fio no nome do material (_cabelo_fios_70 = 0,7 mm). Na Erethea vira um
## EretheaHairStrands (fitas viradas para a câmera, brilho de cabelo, presas ao esqueleto) e os fios
## tomam o lugar dos cards (o couro cabeludo e a camada de baixo ficam); com
## fornalha/cabelo/cards_com_fios = true, os dois juntos. Na Godot comum as linhas ficam escondidas (linha
## de 1 px não é cabelo) e os cards seguem fazendo o cabelo. Devolve quantos penteados viraram fios.
static func fios(no: Node) -> int:
	var feitos := 0
	var erethea := ClassDB.class_exists("EretheaHairStrands") and render() != "anime"
	for n in no.find_children("*_hair_strands*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if mi.mesh == null or mi.has_meta("fios_feitos"):
			continue
		mi.set_meta("fios_feitos", true)
		mi.visible = false
		if not erethea:
			continue
		var largura := 0.0007
		var cor := Color(0.25, 0.17, 0.11)
		var mat := mi.mesh.surface_get_material(0) as BaseMaterial3D
		if mat != null:
			cor = mat.albedo_color
			var nome := String(mat.resource_name)
			var i := nome.rfind("_cabelo_fios_")
			if i >= 0 and nome.substr(i + 13).is_valid_int():
				largura = nome.substr(i + 13).to_int() * 0.00001
		var cabelo: MeshInstance3D = ClassDB.instantiate("EretheaHairStrands")
		cabelo.name = String(mi.name) + "_erethea"
		cabelo.set("source_mesh", mi.mesh)
		cabelo.set("width", largura)
		cabelo.set("color_root", cor * 0.85)
		cabelo.set("color_tip", cor)
		cabelo.skin = mi.skin
		mi.get_parent().add_child(cabelo)
		cabelo.transform = mi.transform
		# os nós são irmãos: o mesmo caminho até o esqueleto (sob o Skeleton3D, NodePath(".."))
		cabelo.skeleton = mi.skeleton if not mi.skeleton.is_empty() else NodePath("..")
		if not ProjectSettings.get_setting("fornalha/cabelo/cards_com_fios", false):
			# os cards (material <id>_cabelo_cards) saem; a camada de baixo e o couro cabeludo ficam
			for c in mi.get_parent().find_children("*", "MeshInstance3D", true, false):
				var cm := c as MeshInstance3D
				if cm.mesh != null and cm.mesh.get_surface_count() > 0 and cm.mesh.surface_get_material(0) != null \
						and String(cm.mesh.surface_get_material(0).resource_name).contains("cabelo_cards"):
					cm.visible = false
		feitos += 1
	return feitos


## Visual anime: troca o material de cada peça pelo de faixas (com a textura e a cor dele) e põe o
## contorno; cabelo em cards recorta pelo alfa e não leva contorno (seria uma linha em cada card).
static func materiais_anime(no: Node) -> int:
	var feitos := 0
	var mi := no as MeshInstance3D
	if mi != null and mi.mesh != null and not String(mi.name).contains("_hair_strands"):
		for i in mi.mesh.get_surface_count():
			var base := mi.get_active_material(i) as BaseMaterial3D
			if base == null:
				continue
			var nome := String(base.resource_name)
			var cards := nome.contains("cabelo_cards") or nome.contains("couro_cabeludo") or nome.contains("eyelash") or nome.contains("eyebrow")
			var sm := ShaderMaterial.new()
			sm.shader = load("res://Scripts/fornalha/anime.gdshader")
			sm.set_shader_parameter("cor", base.albedo_color)
			if base.albedo_texture:
				sm.set_shader_parameter("textura", base.albedo_texture)
				sm.set_shader_parameter("tem_textura", true)
			sm.set_shader_parameter("usa_alfa", cards or base.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED)
			sm.set_shader_parameter("cor_do_vertice", nome.contains("cabelo_cards"))
			if not cards and not nome.contains("olho") and not nome.contains("eyes"):
				var linha := ShaderMaterial.new()
				linha.shader = load("res://Scripts/fornalha/contorno.gdshader")
				sm.next_pass = linha
			mi.set_surface_override_material(i, sm)
			feitos += 1
	for f in no.get_children():
		feitos += materiais_anime(f)
	return feitos


## Materiais especiais: os cards de cabelo ganham o shader de cabelo (hash, brilho anisotrópico), o
## couro cabeludo vira hash e a pele ganha espalhamento sob a superfície (orelha contra a luz).
## No visual anime, todos viram o material de faixas com contorno.
static func materiais(no: Node) -> void:
	if render() == "anime":
		materiais_anime(no)
		return
	var mi := no as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in mi.mesh.get_surface_count():
			var mat: Material = mi.mesh.surface_get_material(i)
			if mat == null:
				continue
			var nome := String(mat.resource_name)
			var base := mat as BaseMaterial3D
			if nome.contains("cabelo_cards") and base != null:
				var sm := ShaderMaterial.new()
				sm.shader = load("res://Scripts/fornalha/cabelo.gdshader")
				sm.set_shader_parameter("atlas", base.albedo_texture)
				if base.ao_texture:
					sm.set_shader_parameter("dados", base.ao_texture)
				if base.normal_texture:
					sm.set_shader_parameter("normais", base.normal_texture)
				mi.set_surface_override_material(i, sm)
				mi.lod_bias = 8.0  # a simplificação de longe não pode comer as mechas finas
			elif nome.contains("couro_cabeludo") and base != null:
				# camada 0: fade pontilhado na linha do cabelo (sem erro de ordem com os cards)
				var cc := ShaderMaterial.new()
				cc.shader = load("res://Scripts/fornalha/couro_cabeludo.gdshader")
				cc.set_shader_parameter("textura", base.albedo_texture)
				mi.set_surface_override_material(i, cc)
			elif nome.ends_with("_pele") and base != null:
				var pele: BaseMaterial3D = base.duplicate()
				pele.subsurf_scatter_enabled = true
				pele.subsurf_scatter_strength = 0.35
				pele.subsurf_scatter_skin_mode = true
				mi.set_surface_override_material(i, pele)
	for f in no.get_children():
		materiais(f)
