extends Node
## Movimento dos personagens da Fornalha (Godot 4.6 / Erethea). Gerado pela Fornalha; pode editar.
## - Locomoção por AnimationTree: BlendSpace1D pela velocidade real (parado → andar → correr → pique).
##   Os ciclos andam juntos (mesma fase, linha do tempo normalizada) e o ritmo de cada um segue a
##   velocidade do corpo, medida nos pés de cada animação: a passada não patina.
## - Camada de cima (golpes, defesa) misturada da cintura para cima: dá para atacar andando. Parado,
##   as pernas também seguem o golpe.
## - Ações de corpo inteiro (pular, esquivar, dano, aterrissar) por cima de tudo, com fade.
## - Pés no chão: TwoBoneIK3D por perna, com raio no calcanhar e na ponta, tornozelo alinhado ao
##   chão (rampa, escada) e pelve descendo pela diferença. Liga parado ou andando devagar.
## - Olhar: LookAtModifier3D na cabeça (e no pescoço, quando o eixo dele é vertical), com limite de
##   ângulo e suavização.
## O IK e o olhar usam classes da Godot 4.6 (TwoBoneIK3D, LookAtModifier3D), criadas pelo nome: numa
## engine sem elas (Erethea antiga) o jogo roda com a locomoção e as camadas, sem IK nem olhar.

signal acao_terminou(nome: String)
signal passo(lado: int)

## Nomes dos ossos: esqueleto de jogo (Unreal, o do humano realista) e perfil humanoide da Godot (Forja).
const OSSOS := {
	"pelve": ["pelvis", "Hips"],
	"coluna": ["spine_01", "Spine"],
	"pescoco": ["neck_01", "Neck"],
	"cabeca": ["head", "Head"],
	"coxa_e": ["thigh_l", "LeftUpperLeg"],
	"canela_e": ["calf_l", "LeftLowerLeg"],
	"pe_e": ["foot_l", "LeftFoot"],
	"ponta_e": ["ball_l", "LeftToes"],
	"coxa_d": ["thigh_r", "RightUpperLeg"],
	"canela_d": ["calf_r", "RightLowerLeg"],
	"pe_d": ["foot_r", "RightFoot"],
	"ponta_d": ["ball_r", "RightToes"],
}
const LOCOMOCAO := ["parado", "andar", "correr", "correr_rapido"]
## Velocidade natural (m/s, para 1,8 m de altura) quando a medição pelos pés não dá certo.
const VELOCIDADE_PADRAO := {"andar": 1.3, "correr": 3.2, "correr_rapido": 5.5}
## Golpes e defesa: da cintura para cima (as pernas seguem a locomoção quando o corpo anda).
const ACOES_CIMA := ["atacar", "atacar_2", "atacar_3", "combo", "defender", "soco", "soco_2", "zumbi_ataque", "interagir"]
## Ações de corpo inteiro.
const ACOES_CORPO := ["pular", "aterrissar", "esquivar", "dano", "dano_forte"]
const FADE := {"dano": [0.05, 0.15], "dano_forte": [0.05, 0.2], "pular": [0.08, 0.2], "aterrissar": [0.06, 0.25], "esquivar": [0.08, 0.2]}
const CAMADA_MUNDO := 1
const DEGRAU := 0.03            # altura entre calcanhar e ponta que a inclinação do chão não explica (m)
const INCLINACAO_MAX := 0.7     # rampa mais inclinada que o pé acompanha (rad, ~40°)

var ativo := false
var arvore: AnimationTree
var anim: AnimationPlayer
var esqueleto: Skeleton3D
var corpo: CharacterBody3D
var modelo: Node3D
var ossos := {}
var ciclos := {}            # nome → {"v": m/s, "L": s, "D": m por ciclo, "fase": 0..1}
var morto := false
var medir := false          # o teste automático liga: mede a altura dos pés depois do IK
var medida := {}            # última medida: {"com_ik": [e, d], "sem_ik": [e, d]} (m)

var _pontos: Array = []     # pontos do BlendSpace1D: [{"nome", "v", "D"}] em ordem de velocidade
var _v := 0.0               # velocidade suavizada usada na mistura
var _fase := 0.0
var _no_ar := 0.0
var _estado := "chao"
var _camadas := {
	"cima": {"acao": "", "t": 0.0, "dur": 0.0, "peso": 0.0, "entra": 0.1, "sai": 0.25, "fim": false},
	"corpo": {"acao": "", "t": 0.0, "dur": 0.0, "peso": 0.0, "entra": 0.1, "sai": 0.2, "fim": false},
}
var _pernas := 1.0          # quanto as pernas seguem o golpe (1 parado, 0 andando)

# pés no chão
var peso_ik := 0.0
var _ik: SkeletonModifier3D   # TwoBoneIK3D (Godot 4.6)
var _pre: SkeletonModifier3D
var _pos: SkeletonModifier3D
var _alvos: Array[Marker3D] = []
var _polos: Array[Marker3D] = []
var _sola_calc: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO]
var _sola_ponta: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO]
var _delta: Array[float] = [0.0, 0.0]
var _giro: Array[Quaternion] = [Quaternion.IDENTITY, Quaternion.IDENTITY]
var _base_pe: Array[Basis] = [Basis.IDENTITY, Basis.IDENTITY]
var _sem_ik: Array[float] = [0.0, 0.0]
var _pelve := 0.0
var _excluir: Array[RID] = []

# olhar
var _olhar: Array[SkeletonModifier3D] = []   # LookAtModifier3D
var _olhar_base: Array[float] = []
var _alvo_olhar: Marker3D
var _ponto_olhar := Vector3.ZERO
var _peso_olhar := 0.0
var _peso_olhar_alvo := 0.0
var _frente_da_cabeca := Vector3.FORWARD   # eixo do osso da cabeça que aponta para a frente do rosto


class PreparaPes extends SkeletonModifier3D:
	## Antes do IK: raios no chão, pelve e alvos dos pés.
	var mov

	func _process_modification_with_delta(dt: float) -> void:
		if mov:
			mov._antes_do_ik(get_skeleton(), dt)


class AlinhaPes extends SkeletonModifier3D:
	## Depois do IK: tornozelo alinhado ao chão.
	var mov

	func _process_modification_with_delta(_dt: float) -> void:
		if mov:
			mov._depois_do_ik(get_skeleton())


class Rosto extends SkeletonModifier3D:
	## Piscar (pálpebras), olhadas rápidas (olhos) e a boca seguindo a curva da fala (mandíbula), com os
	## ossos que a Fornalha põe no humano (eye_l/r, eyelid_upper_l/r, eyelid_lower_l/r, jaw).
	var olhos: Array[int] = []
	var cima: Array[int] = []
	var baixo: Array[int] = []
	var jaw := -1
	var eixo_x := Vector3.RIGHT   # eixo X do modelo no espaço do esqueleto
	var eixo_y := Vector3.UP
	var _piscar := 0.0
	var _fase := -1.0
	var _ate_piscar := 2.0
	var _olho := Vector2.ZERO
	var _alvo := Vector2.ZERO
	var _ate_olhar := 1.0
	var _curva: Array = []
	var _qps := 30.0
	var _t_fala := -1.0

	## Abre e fecha a boca pela curva (0 a 1 por quadro) do arquivo .boca.json da fala.
	func falar(curva: Array, quadros_por_segundo := 30.0) -> void:
		_curva = curva
		_qps = maxf(quadros_por_segundo, 1.0)
		_t_fala = 0.0

	func _process_modification_with_delta(dt: float) -> void:
		var sk := get_skeleton()
		if sk == null:
			return
		# piscar: fecha em 70 ms, segura 50 ms, abre em 120 ms; a cada 2,5–6 s
		_ate_piscar -= dt
		if _ate_piscar <= 0.0 and _fase < 0.0:
			_fase = 0.0
			_ate_piscar = randf_range(2.5, 6.0)
		if _fase >= 0.0:
			_fase += dt
			if _fase < 0.07:
				_piscar = _fase / 0.07
			elif _fase < 0.12:
				_piscar = 1.0
			elif _fase < 0.24:
				_piscar = 1.0 - (_fase - 0.12) / 0.12
			else:
				_piscar = 0.0
				_fase = -1.0
		# olhadas rápidas (sacadas) para pontos perto do centro
		_ate_olhar -= dt
		if _ate_olhar <= 0.0:
			_alvo = Vector2(randf_range(-9.0, 9.0), randf_range(-4.0, 3.0))
			_ate_olhar = randf_range(0.8, 2.6)
		_olho = _olho.lerp(_alvo, clampf(dt * 22.0, 0.0, 1.0))
		for i in cima:
			_girar(sk, i, eixo_x, deg_to_rad(30.0 * _piscar))
		for i in baixo:
			_girar(sk, i, eixo_x, deg_to_rad(-8.0 * _piscar))
		for i in olhos:
			_girar(sk, i, eixo_y, deg_to_rad(_olho.x))
			_girar(sk, i, eixo_x, deg_to_rad(-_olho.y))
		if jaw >= 0 and _t_fala >= 0.0:
			_t_fala += dt
			var q := int(_t_fala * _qps)
			if q >= _curva.size():
				_t_fala = -1.0
			else:
				_girar(sk, jaw, eixo_x, deg_to_rad(20.0 * clampf(float(_curva[q]), 0.0, 1.0)))

	func _girar(sk: Skeleton3D, i: int, eixo: Vector3, ang: float) -> void:
		if absf(ang) < 1e-5:
			return
		var g := sk.get_bone_global_pose(i)
		g.basis = Basis(eixo.normalized(), ang) * g.basis
		sk.set_bone_global_pose(i, g)


## Cria o movimento de um personagem (filho do corpo). Devolve null se o modelo não tiver o que precisa.
static func criar(corpo_: CharacterBody3D, modelo_: Node3D, anim_: AnimationPlayer) -> Node:
	if corpo_ == null or modelo_ == null or anim_ == null:
		return null
	var m = load("res://Scripts/fornalha/movimento.gd").new()
	m.name = "Movimento"
	corpo_.add_child(m)
	if not m.preparar(corpo_, modelo_, anim_):
		m.queue_free()
		return null
	return m


static func _achar_esqueleto(no: Node) -> Skeleton3D:
	if no is Skeleton3D:
		return no
	for f in no.get_children():
		var s := _achar_esqueleto(f)
		if s:
			return s
	return null


func preparar(corpo_: CharacterBody3D, modelo_: Node3D, anim_: AnimationPlayer) -> bool:
	corpo = corpo_
	modelo = modelo_
	anim = anim_
	esqueleto = _achar_esqueleto(modelo)
	if esqueleto == null or not anim.has_animation("parado"):
		return false
	for papel in OSSOS:
		for nome in OSSOS[papel]:
			var i := esqueleto.find_bone(nome)
			if i >= 0:
				ossos[papel] = i
				break
	_medir_solas()
	_medir_ciclos()
	_criar_arvore()
	_criar_pes()
	_criar_olhar()
	_criar_rosto()
	_criar_molas()
	esqueleto.skeleton_updated.connect(_esqueleto_atualizado)
	ativo = true
	add_to_group("movimento_fornalha")
	_ignorar_ossos_dos_outros.call_deferred()
	return true


## Os ossos do ragdoll de um personagem (corpos físicos que seguem a animação) não podem servir de
## parede nem de plataforma para o corpo de outro: um golpe rápido "lançava" quem encostasse no
## braço (o CharacterBody3D herdava a velocidade do osso). Vale nos dois sentidos. Os raios dos pés
## também ignoram esses ossos (o pé não pisa no corpo caído de um inimigo).
func _ignorar_ossos_dos_outros() -> void:
	if not is_inside_tree():
		return
	for outro in get_tree().get_nodes_in_group("movimento_fornalha"):
		if outro == self or outro.corpo == null:
			continue
		for pb in _ossos_fisicos(outro.esqueleto):
			corpo.add_collision_exception_with(pb)
			if not pb.get_rid() in _excluir:
				_excluir.append(pb.get_rid())
		for pb in _ossos_fisicos(esqueleto):
			outro.corpo.add_collision_exception_with(pb)
			if not pb.get_rid() in outro._excluir:
				outro._excluir.append(pb.get_rid())


static func _ossos_fisicos(sk: Skeleton3D) -> Array[PhysicalBone3D]:
	var lista: Array[PhysicalBone3D] = []
	if sk == null:
		return lista
	for f in sk.get_children():
		if f is PhysicalBoneSimulator3D:
			for pb in f.get_children():
				if pb is PhysicalBone3D:
					lista.append(pb)
	return lista


func tem(nome: String) -> bool:
	return anim != null and anim.has_animation(nome)


func duracao(nome: String) -> float:
	return anim.get_animation(nome).length if tem(nome) else 0.0


# ---------------------------------------------------------------- medição dos ciclos

## Altura aproximada do personagem pelo esqueleto (cabeça em descanso).
func _altura() -> float:
	if ossos.has("cabeca"):
		return clampf(esqueleto.get_bone_global_rest(ossos["cabeca"]).origin.y * 1.09, 0.6, 6.0)
	return 1.8


## Posição do osso (espaço do esqueleto) no tempo t da animação, calculada das trilhas.
func _osso_no_tempo(a: Animation, prefixo: String, osso: int, t: float) -> Transform3D:
	var cadeia: Array[int] = []
	var i := osso
	while i >= 0:
		cadeia.push_front(i)
		i = esqueleto.get_bone_parent(i)
	var g := Transform3D.IDENTITY
	for b in cadeia:
		var descanso := esqueleto.get_bone_rest(b)
		var caminho := NodePath(prefixo + ":" + esqueleto.get_bone_name(b))
		var pos := descanso.origin
		var rot := descanso.basis.get_rotation_quaternion()
		var esc := descanso.basis.get_scale()
		var tp := a.find_track(caminho, Animation.TYPE_POSITION_3D)
		if tp >= 0:
			pos = a.position_track_interpolate(tp, t)
		var tr := a.find_track(caminho, Animation.TYPE_ROTATION_3D)
		if tr >= 0:
			rot = a.rotation_track_interpolate(tr, t)
		var te := a.find_track(caminho, Animation.TYPE_SCALE_3D)
		if te >= 0:
			esc = a.scale_track_interpolate(te, t)
		g = g * Transform3D(Basis(rot).scaled(esc), pos)
	return g


func _prefixo_das_trilhas() -> String:
	var raiz := anim.get_node_or_null(anim.root_node)
	return String(raiz.get_path_to(esqueleto)) if raiz else "Skeleton3D"


## Pontos da sola (calcanhar e ponta) presos ao osso do pé, tirados da pose de descanso.
func _medir_solas() -> void:
	var lados := ["e", "d"]
	for k in 2:
		var lado: String = lados[k]
		if not ossos.has("pe_" + lado):
			continue
		var pe_rest := esqueleto.get_bone_global_rest(ossos["pe_" + lado])
		var tornozelo := pe_rest.origin
		var ponta := tornozelo + Vector3(0, -tornozelo.y, 0.12 * _altura() / 1.8)
		if ossos.has("ponta_" + lado):
			ponta = esqueleto.get_bone_global_rest(ossos["ponta_" + lado]).origin
		var chao := minf(0.0, ponta.y - 0.005)
		var frente := Vector3(ponta.x - tornozelo.x, 0.0, ponta.z - tornozelo.z)
		var calc := Vector3(tornozelo.x, chao, tornozelo.z) - frente * 0.25
		_sola_calc[k] = pe_rest.affine_inverse() * calc
		_sola_ponta[k] = pe_rest.affine_inverse() * Vector3(ponta.x, chao, ponta.z)


## Mede, nos pés de cada ciclo de locomoção, a velocidade natural (o ponto da sola que está no chão
## corre para trás na velocidade do corpo: calcanhar ao andar, ponta ao correr) e a fase em que o
## pé esquerdo está mais à frente.
func _medir_ciclos() -> void:
	var escala := _altura() / 1.8
	var prefixo := _prefixo_das_trilhas()
	var para_modelo := modelo.global_transform.affine_inverse() * esqueleto.global_transform
	for nome in LOCOMOCAO:
		if not tem(nome):
			continue
		var a := anim.get_animation(nome)
		var L := maxf(a.length, 0.05)
		var info := {"v": 0.0, "L": L, "D": 0.0, "fase": 0.0}
		if nome != "parado":
			var v_medida := []
			var fase := 0.0
			var lados := ["e", "d"]
			for j in 2:
				if not ossos.has("pe_" + lados[j]):
					continue
				var n := 96
				var solas: Array = []   # por amostra: [calcanhar, ponta] no espaço do modelo
				var z_max := -INF
				for k in n + 1:
					var pw := para_modelo * _osso_no_tempo(a, prefixo, ossos["pe_" + lados[j]], L * k / n)
					solas.append([pw * _sola_calc[j], pw * _sola_ponta[j]])
					if j == 0 and pw.origin.z > z_max:
						z_max = pw.origin.z
						fase = float(k) / n
				var h_min := INF
				for par in solas:
					h_min = minf(h_min, minf(par[0].y, par[1].y))
				var dt := L / n
				for k in n:
					# o ponto mais baixo da sola nesta amostra; apoio se está rente ao chão nas duas
					var i := 0 if solas[k][0].y <= solas[k][1].y else 1
					var p0: Vector3 = solas[k][i]
					var p1: Vector3 = solas[k + 1][i]
					if p0.y < h_min + 0.02 * escala and p1.y < h_min + 0.02 * escala:
						v_medida.append(-(p1.z - p0.z) / dt)
			v_medida.sort()
			var v: float = v_medida[v_medida.size() >> 1] if v_medida.size() >= 4 else 0.0
			var padrao: float = VELOCIDADE_PADRAO.get(nome, 1.5) * escala
			if v < padrao * 0.35 or v > padrao * 3.0:
				v = padrao
			info["v"] = v
			info["D"] = v * L
			info["fase"] = fmod(fase, 1.0)
		ciclos[nome] = info


# ---------------------------------------------------------------- árvore de animação

func _caminho_do_osso(raiz: Node, osso: int) -> NodePath:
	return NodePath(String(raiz.get_path_to(esqueleto)) + ":" + esqueleto.get_bone_name(osso))


func _descendentes(osso: int) -> Array[int]:
	var lista: Array[int] = [osso]
	var k := 0
	while k < lista.size():
		for f in esqueleto.get_bone_children(lista[k]):
			lista.append(f)
		k += 1
	return lista


func _animacao(nome: String, laco := false) -> AnimationNodeAnimation:
	var a := AnimationNodeAnimation.new()
	a.animation = nome
	if laco:
		a.use_custom_timeline = true
		a.timeline_length = duracao(nome)
		a.stretch_time_scale = false
		a.loop_mode = Animation.LOOP_LINEAR
	return a


func _transicao_de(nomes: Array, xfade: float) -> AnimationNodeTransition:
	var t := AnimationNodeTransition.new()
	t.input_count = nomes.size()
	t.xfade_time = xfade
	t.allow_transition_to_self = true
	for k in nomes.size():
		t.set_input_name(k, nomes[k])
		t.set_input_reset(k, true)
	return t


func _ligar_clipes(raiz: AnimationNodeBlendTree, no: String, nomes: Array, xfade: float) -> void:
	raiz.add_node(no, _transicao_de(nomes, xfade))
	for k in nomes.size():
		var id := "%s_%d" % [no, k]
		raiz.add_node(id, _animacao(nomes[k]))
		raiz.connect_node(no, k, id)


func _criar_arvore() -> void:
	arvore = AnimationTree.new()
	arvore.name = "ArvoreDeAnimacao"
	anim.get_parent().add_child(arvore)
	arvore.anim_player = arvore.get_path_to(anim)
	var raiz_anim := arvore.get_node(arvore.root_node)
	var raiz := AnimationNodeBlendTree.new()
	# locomoção: BlendSpace1D pela velocidade real
	var bs := AnimationNodeBlendSpace1D.new()
	bs.sync = true
	bs.min_space = 0.0
	var lista: Array = []
	for nome in LOCOMOCAO:
		if ciclos.has(nome):
			lista.append({"nome": nome, "v": ciclos[nome]["v"], "D": ciclos[nome]["D"]})
	lista.sort_custom(func(x, y): return x["v"] < y["v"])
	var ultimo := -1.0
	for p in lista:
		if p["nome"] != "parado" and p["v"] < ultimo + 0.3:
			p["v"] = ultimo + 0.3
			p["D"] = p["v"] * ciclos[p["nome"]]["L"]
		ultimo = p["v"]
		_pontos.append(p)
	bs.max_space = maxf(ultimo * 2.0, 4.0)
	for k in _pontos.size():
		var p: Dictionary = _pontos[k]
		if p["nome"] == "parado":
			bs.add_blend_point(_animacao("parado", true), 0.0)
			continue
		# ciclo na linha do tempo normalizada (1 = um ciclo), começando com o pé esquerdo na frente
		var ponto := AnimationNodeBlendTree.new()
		var a := AnimationNodeAnimation.new()
		a.animation = p["nome"]
		a.use_custom_timeline = true
		a.timeline_length = 1.0
		a.stretch_time_scale = true
		a.loop_mode = Animation.LOOP_LINEAR
		a.start_offset = ciclos[p["nome"]]["fase"]
		ponto.add_node("anim", a)
		ponto.add_node("ritmo", AnimationNodeTimeScale.new())
		ponto.connect_node("ritmo", 0, "anim")
		ponto.connect_node("output", 0, "ritmo")
		bs.add_blend_point(ponto, p["v"])
	raiz.add_node("loco", bs)
	# chão, no ar e morto
	var estados := ["chao", "ar", "morto"]
	var est := _transicao_de(estados, 0.22)
	est.set_input_reset(0, false)
	raiz.add_node("estado", est)
	raiz.connect_node("estado", 0, "loco")
	raiz.add_node("no_ar", _animacao("no_ar" if tem("no_ar") else "parado", true))
	raiz.connect_node("estado", 1, "no_ar")
	raiz.add_node("morrer", _animacao("morrer" if tem("morrer") else "parado"))
	raiz.connect_node("estado", 2, "morrer")
	# camada de cima (filtro da cintura para cima) e pernas do golpe (filtro da cintura para baixo)
	var cima_nomes := ACOES_CIMA.filter(func(n): return tem(n))
	var corpo_nomes := ACOES_CORPO.filter(func(n): return tem(n))
	if cima_nomes.is_empty():
		cima_nomes = ["parado"]
	if corpo_nomes.is_empty():
		corpo_nomes = ["parado"]
	var de_cima: Array[int] = []
	if ossos.has("coluna"):
		de_cima = _descendentes(ossos["coluna"])
	var b_cima := AnimationNodeBlend2.new()
	var b_pernas := AnimationNodeBlend2.new()
	b_cima.filter_enabled = true
	b_pernas.filter_enabled = true
	for i in esqueleto.get_bone_count():
		var caminho := _caminho_do_osso(raiz_anim, i)
		if i in de_cima:
			b_cima.set_filter_path(caminho, true)
		else:
			b_pernas.set_filter_path(caminho, true)
	raiz.add_node("cima", b_cima)
	raiz.add_node("pernas", b_pernas)
	_ligar_clipes(raiz, "clipes_cima", cima_nomes, 0.12)
	_ligar_clipes(raiz, "clipes_pernas", cima_nomes, 0.12)
	raiz.connect_node("cima", 0, "estado")
	raiz.connect_node("cima", 1, "clipes_cima")
	raiz.connect_node("pernas", 0, "cima")
	raiz.connect_node("pernas", 1, "clipes_pernas")
	# corpo inteiro por cima de tudo
	raiz.add_node("corpo", AnimationNodeBlend2.new())
	_ligar_clipes(raiz, "clipes_corpo", corpo_nomes, 0.1)
	raiz.connect_node("corpo", 0, "pernas")
	raiz.connect_node("corpo", 1, "clipes_corpo")
	raiz.connect_node("output", 0, "corpo")
	arvore.tree_root = raiz
	arvore.active = true
	anim.stop()


## Chamado a cada quadro de física pelo dono (jogador ou inimigo).
func atualizar(velocidade_h: float, no_chao: bool, dt: float) -> void:
	if not ativo:
		return
	# no ar só depois de um instante fora do chão (degrau e rampa não piscam o estado)
	_no_ar = 0.0 if no_chao else _no_ar + dt
	var estado := "morto" if morto else ("ar" if _no_ar > 0.2 else "chao")
	if estado != _estado:
		if _estado == "ar" and estado == "chao" and _camadas["corpo"]["acao"] == "pular":
			_encerrar("corpo", 0.15)
		_estado = estado
		arvore.set("parameters/estado/transition_request", estado)
	_v = lerpf(_v, velocidade_h, 1.0 - exp(-12.0 * dt))
	_locomocao(dt)
	_atualizar_camadas(dt)
	_atualizar_ik(velocidade_h, dt)
	_atualizar_olhar(dt)


func _locomocao(dt: float) -> void:
	arvore.set("parameters/loco/blend_position", _v)
	# ritmo: ciclos por segundo = velocidade / distância de um ciclo na mistura atual
	var moveis := _pontos.filter(func(p): return p["nome"] != "parado")
	if moveis.is_empty():
		return
	var D: float = moveis[0]["D"]
	for k in moveis.size() - 1:
		var a: Dictionary = moveis[k]
		var b: Dictionary = moveis[k + 1]
		if _v >= a["v"] and _v <= b["v"]:
			D = lerpf(a["D"], b["D"], (_v - a["v"]) / maxf(b["v"] - a["v"], 0.01))
	if _v > moveis[-1]["v"]:
		D = moveis[-1]["D"]
	var L0: float = ciclos[moveis[0]["nome"]]["L"]
	var ritmo := clampf(_v / maxf(D, 0.05), 0.3 / L0, 3.0)
	for k in _pontos.size():
		if _pontos[k]["nome"] != "parado":
			arvore.set("parameters/loco/%d/ritmo/scale" % k, ritmo)
	# passos: o pé esquerdo pisa no começo do ciclo e o direito na metade
	var antes := _fase
	_fase = fmod(_fase + ritmo * dt, 1.0)
	if _v > 0.4 and _estado == "chao":
		if _fase < antes:
			passo.emit(0)
		elif antes < 0.5 and _fase >= 0.5:
			passo.emit(1)


## Toca uma ação por nome: golpes e defesa na camada de cima, o resto no corpo inteiro.
## Devolve a duração (0 se a animação não existe).
func tocar(nome: String) -> float:
	if not ativo or not tem(nome) or nome in LOCOMOCAO or nome == "no_ar":
		return 0.0
	if nome == "morrer":
		morrer(false)
		return duracao(nome)
	var camada := "cima" if nome in ACOES_CIMA else "corpo"
	var c: Dictionary = _camadas[camada]
	var fades: Array = FADE.get(nome, [0.1, 0.25])
	c["acao"] = nome
	c["t"] = 0.0
	c["dur"] = duracao(nome)
	c["entra"] = fades[0]
	c["sai"] = minf(fades[1], c["dur"] * 0.4)
	c["fim"] = false
	if camada == "cima":
		arvore.set("parameters/clipes_cima/transition_request", nome)
		arvore.set("parameters/clipes_pernas/transition_request", nome)
	else:
		arvore.set("parameters/clipes_corpo/transition_request", nome)
		# ação de corpo inteiro interrompe o golpe (avisado depois que a nova ação já vale)
		_encerrar("cima", 0.1)
	return c["dur"]


## Como estão as camadas agora (o teste automático confere).
func estado_atual() -> Dictionary:
	return {"velocidade": _v, "cima": _camadas["cima"]["peso"], "pernas_do_golpe": _camadas["cima"]["peso"] * _pernas,
			"corpo": _camadas["corpo"]["peso"], "acao_cima": _camadas["cima"]["acao"], "acao_corpo": _camadas["corpo"]["acao"],
			"peso_ik": peso_ik, "olhar": _peso_olhar, "estado": _estado, "arvore_ativa": arvore != null and arvore.active}


## No ar de verdade (fora do chão por mais de um instante).
func no_ar() -> bool:
	return _estado == "ar"


func acao_atual(camada := "") -> String:
	if camada != "":
		return _camadas[camada]["acao"]
	return _camadas["corpo"]["acao"] if _camadas["corpo"]["acao"] != "" else _camadas["cima"]["acao"]


func _encerrar(camada: String, fade: float) -> void:
	var c: Dictionary = _camadas[camada]
	if c["acao"] == "":
		return
	c["sai"] = fade
	c["dur"] = minf(c["dur"], c["t"] + fade)
	if not c["fim"]:
		c["fim"] = true
		acao_terminou.emit(c["acao"])


func _atualizar_camadas(dt: float) -> void:
	for nome in _camadas:
		var c: Dictionary = _camadas[nome]
		var alvo := 0.0
		if c["acao"] != "":
			c["t"] += dt
			# aterrissar é cortado quando a pessoa já sai andando
			if c["acao"] == "aterrissar" and _v > 0.8:
				_encerrar(nome, 0.15)
			if not c["fim"] and c["t"] >= c["dur"] - c["sai"]:
				c["fim"] = true
				acao_terminou.emit(c["acao"])
			alvo = 0.0 if c["fim"] else 1.0
		var vel: float = 1.0 / maxf(c["entra"] if alvo > c["peso"] else c["sai"], 0.01)
		c["peso"] = move_toward(c["peso"], alvo, vel * dt)
		if c["fim"] and c["peso"] <= 0.0:
			c["acao"] = ""
	_pernas = move_toward(_pernas, 1.0 - smoothstep(0.3, 1.2, _v), 4.0 * dt)
	arvore.set("parameters/cima/blend_amount", _camadas["cima"]["peso"])
	arvore.set("parameters/pernas/blend_amount", _camadas["cima"]["peso"] * _pernas)
	arvore.set("parameters/corpo/blend_amount", _camadas["corpo"]["peso"])


## Morte: sem IK nem olhar. Com ragdoll a física assume (a árvore para); sem, toca "morrer".
func morrer(com_ragdoll: bool) -> void:
	morto = true
	peso_ik = 0.0
	_peso_olhar = 0.0
	if _ik:
		_ik.active = false
	for m in [_pre, _pos]:
		if m:
			m.active = false
	for la in _olhar:
		la.active = false
	if not ativo:
		return
	for nome in _camadas:
		_camadas[nome]["acao"] = ""
		_camadas[nome]["peso"] = 0.0
	if com_ragdoll:
		arvore.active = false
	else:
		_estado = "morto"
		arvore.set("parameters/estado/transition_request", "morto")
		arvore.set("parameters/cima/blend_amount", 0.0)
		arvore.set("parameters/pernas/blend_amount", 0.0)
		arvore.set("parameters/corpo/blend_amount", 0.0)


# ---------------------------------------------------------------- pés no chão

func _criar_pes() -> void:
	if not ClassDB.class_exists("TwoBoneIK3D"):
		return
	for p in ["coxa_e", "canela_e", "pe_e", "coxa_d", "canela_d", "pe_d", "pelve"]:
		if not ossos.has(p):
			return
	var lados := ["e", "d"]
	for k in 2:
		var lado: String = lados[k]
		var alvo := Marker3D.new()
		alvo.name = "AlvoPe_" + lado
		add_child(alvo)
		_alvos.append(alvo)
		var polo := Marker3D.new()
		polo.name = "PoloJoelho_" + lado
		add_child(polo)
		_polos.append(polo)
	_pre = PreparaPes.new()
	_pre.name = "PesNoChao"
	_pre.mov = self
	var ik = ClassDB.instantiate("TwoBoneIK3D")
	_ik = ik
	_ik.name = "IKPernas"
	_pos = AlinhaPes.new()
	_pos.name = "TornozeloNoChao"
	_pos.mov = self
	for m in [_pre, _ik, _pos]:
		esqueleto.add_child(m)
	ik.set_setting_count(2)
	for k in 2:
		var lado: String = lados[k]
		ik.set_root_bone_name(k, esqueleto.get_bone_name(ossos["coxa_" + lado]))
		ik.set_middle_bone_name(k, esqueleto.get_bone_name(ossos["canela_" + lado]))
		ik.set_end_bone_name(k, esqueleto.get_bone_name(ossos["pe_" + lado]))
		ik.set_target_node(k, _ik.get_path_to(_alvos[k]))
		ik.set_pole_node(k, _ik.get_path_to(_polos[k]))
	# os modificadores do movimento vêm antes da mola da capa e do ragdoll
	esqueleto.move_child(_pre, 0)
	esqueleto.move_child(_ik, 1)
	esqueleto.move_child(_pos, 2)
	_ik.influence = 0.0
	_ik.active = false
	_excluir = [corpo.get_rid()]
	for pb in _ossos_fisicos(esqueleto):
		_excluir.append(pb.get_rid())


func _atualizar_ik(velocidade_h: float, dt: float) -> void:
	if _ik == null:
		return
	var alvo := 1.0 - smoothstep(1.4, 2.6, velocidade_h)
	var acao: String = _camadas["corpo"]["acao"]
	if _estado != "chao" or morto or acao in ["pular", "esquivar"]:
		alvo = 0.0
	# desliga rápido (no ar, ~0,15 s) e liga devagar (~0,35 s)
	peso_ik = move_toward(peso_ik, alvo, dt * (7.0 if alvo < peso_ik else 3.0))
	var ligado := peso_ik > 0.001
	_ik.active = ligado
	_ik.influence = peso_ik
	_pre.active = ligado
	_pos.active = ligado
	if not ligado:
		_pelve = 0.0
		_delta = [0.0, 0.0]


func _raio(espaco: PhysicsDirectSpaceState3D, p: Vector3, base_y: float) -> Dictionary:
	var de := Vector3(p.x, maxf(p.y, base_y) + 0.5, p.z)
	var ate := Vector3(p.x, minf(p.y, base_y) - 0.6, p.z)
	var q := PhysicsRayQueryParameters3D.create(de, ate, CAMADA_MUNDO, _excluir)
	return espaco.intersect_ray(q)


func _y_no_plano(ponto: Vector3, n: Vector3, xz: Vector3) -> float:
	return ponto.y - (n.x * (xz.x - ponto.x) + n.z * (xz.z - ponto.z)) / maxf(n.y, 0.2)


func _antes_do_ik(sk: Skeleton3D, dt: float) -> void:
	var xf := sk.global_transform
	var base_y := corpo.global_position.y
	var espaco := sk.get_world_3d().direct_space_state
	var suave := 1.0 - exp(-14.0 * dt)
	var lados := ["e", "d"]
	var tornozelos: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO]
	var frentes: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO]
	for k in 2:
		var pg := sk.get_bone_global_pose(ossos["pe_" + lados[k]])
		var pw := xf * pg
		var calc := pw * _sola_calc[k]
		var ponta := pw * _sola_ponta[k]
		var tornozelo := pw.origin
		tornozelos[k] = tornozelo
		frentes[k] = Vector3(ponta.x - calc.x, 0.0, ponta.z - calc.z)
		_base_pe[k] = pg.basis
		var h_min := minf(calc.y, ponta.y) - base_y
		var rc := _raio(espaco, calc, base_y)
		var rp := _raio(espaco, ponta, base_y)
		var n := Vector3.UP
		var ref := Vector3(tornozelo.x, base_y, tornozelo.z)
		var achou := true
		if not rc.is_empty() and not rp.is_empty():
			_sem_ik[k] = minf(calc.y - rc.position.y, ponta.y - rp.position.y)
			# rampa: a diferença de altura entre calcanhar e ponta bate com a inclinação do chão;
			# degrau: não bate (chão plano nos dois, alturas diferentes) e o pé fica no mais alto
			var n_med: Vector3 = (rc.normal + rp.normal).normalized()
			var d: Vector3 = rp.position - rc.position
			var prevista := -(n_med.x * d.x + n_med.z * d.z) / maxf(n_med.y, 0.2)
			if absf(d.y - prevista) > DEGRAU:
				ref = rc.position if rc.position.y > rp.position.y else rp.position
			else:
				n = n_med
				ref = (rc.position + rp.position) * 0.5
		elif not rc.is_empty():
			n = rc.normal
			ref = rc.position
		elif not rp.is_empty():
			n = rp.normal
			ref = rp.position
		else:
			achou = false
		if n.angle_to(Vector3.UP) > INCLINACAO_MAX:
			n = Vector3.UP.slerp(n, INCLINACAO_MAX / n.angle_to(Vector3.UP)).normalized()
		var giro := Quaternion(Vector3.UP, n) if achou else Quaternion.IDENTITY
		var delta := 0.0
		if achou:
			var sc := giro * (calc - tornozelo)
			var sp := giro * (ponta - tornozelo)
			# contato: pé perto do chão na animação fica colado; no ar, mantém a altura do passo
			var contato := 1.0 - smoothstep(0.03, 0.10, h_min)
			var folga := (1.0 - contato) * maxf(h_min, 0.0)
			var alvo_y := folga + maxf(_y_no_plano(ref, n, tornozelo + sc) - sc.y, _y_no_plano(ref, n, tornozelo + sp) - sp.y)
			delta = clampf(alvo_y - tornozelo.y, -0.45, 0.45)
		_delta[k] = lerpf(_delta[k], delta, suave)
		_giro[k] = _giro[k].slerp(giro, suave)
	# a pelve desce pela diferença (a perna que precisa ir mais baixo alcança o chão)
	_pelve = lerpf(_pelve, clampf(minf(_delta[0], _delta[1]), -0.4, 0.0), suave)
	var pi: int = ossos["pelve"]
	var deslocar := xf.basis.inverse() * Vector3(0.0, _pelve * peso_ik, 0.0)
	var pai := sk.get_bone_parent(pi)
	if pai >= 0:
		deslocar = sk.get_bone_global_pose(pai).basis.inverse() * deslocar
	sk.set_bone_pose_position(pi, sk.get_bone_pose_position(pi) + deslocar)
	for k in 2:
		_alvos[k].global_position = tornozelos[k] + Vector3(0.0, _delta[k], 0.0)
		var joelho := xf * sk.get_bone_global_pose(ossos["canela_" + lados[k]]).origin
		var frente := frentes[k].normalized() if frentes[k].length() > 0.01 else modelo.global_transform.basis.z.normalized()
		_polos[k].global_position = joelho + frente * 0.6


func _depois_do_ik(sk: Skeleton3D) -> void:
	var b := sk.global_transform.basis.orthonormalized()
	var lados := ["e", "d"]
	for k in 2:
		var pe: int = ossos["pe_" + lados[k]]
		var giro_sk := Basis(b.inverse() * Basis(_giro[k]) * b).get_rotation_quaternion()
		var desejado := (Basis(giro_sk) * _base_pe[k].orthonormalized()).get_rotation_quaternion()
		var atual := sk.get_bone_global_pose(pe).basis.get_rotation_quaternion()
		var final := atual.slerp(desejado, peso_ik)
		var pai := sk.get_bone_parent(pe)
		var local := final
		if pai >= 0:
			local = sk.get_bone_global_pose(pai).basis.get_rotation_quaternion().inverse() * final
		sk.set_bone_pose_rotation(pe, local.normalized())


## Mede, na pose final (depois do IK e do olhar), a sola dos dois pés contra o chão e quanto a
## cabeça virou em relação ao corpo, para o teste.
func _esqueleto_atualizado() -> void:
	if not medir or not is_inside_tree():
		return
	var xf := esqueleto.global_transform
	if ossos.has("cabeca"):
		var f := xf.basis * (esqueleto.get_bone_global_pose(ossos["cabeca"]).basis * _frente_da_cabeca)
		var c := modelo.global_transform.basis.z
		f.y = 0.0
		c.y = 0.0
		if f.length() > 0.01 and c.length() > 0.01:
			medida["cabeca_graus"] = rad_to_deg(c.signed_angle_to(f, Vector3.UP))
	if _ik == null:
		return
	var espaco := esqueleto.get_world_3d().direct_space_state
	var base_y := corpo.global_position.y
	var com: Array = []
	var lados := ["e", "d"]
	for k in 2:
		var pw := xf * esqueleto.get_bone_global_pose(ossos["pe_" + lados[k]])
		var folgas: Array[float] = []
		for ponto in [pw * _sola_calc[k], pw * _sola_ponta[k]]:
			var r := _raio(espaco, ponto, base_y)
			if not r.is_empty():
				folgas.append(ponto.y - r.position.y)
		com.append(folgas.min() if not folgas.is_empty() else INF)
	var erro: Array = []
	for k in 2:
		erro.append((xf * esqueleto.get_bone_global_pose(ossos["pe_" + lados[k]])).origin.distance_to(_alvos[k].global_position))
	medida["com_ik"] = com
	medida["sem_ik"] = _sem_ik.duplicate()
	medida["peso_ik"] = peso_ik
	medida["pelve"] = _pelve
	medida["erro_alvo"] = erro
	medida["delta"] = _delta.duplicate()


# ---------------------------------------------------------------- olhar

func _eixo_osso(osso: int, direcao_sk: Vector3) -> Array:
	var local := esqueleto.get_bone_global_rest(osso).basis.inverse() * direcao_sk
	var abs_ := local.abs()
	var eixo := 0 if abs_.x >= abs_.y and abs_.x >= abs_.z else (1 if abs_.y >= abs_.z else 2)
	return [eixo, local[eixo] >= 0.0]


func _criar_olhar() -> void:
	if not ossos.has("cabeca") or not ClassDB.class_exists("LookAtModifier3D"):
		return
	var sk_para_modelo := (modelo.global_transform.affine_inverse() * esqueleto.global_transform).basis.orthonormalized()
	var frente_sk := sk_para_modelo.inverse() * Vector3(0, 0, 1)
	var cima_sk := sk_para_modelo.inverse() * Vector3(0, 1, 0)
	_frente_da_cabeca = (esqueleto.get_bone_global_rest(ossos["cabeca"]).basis.inverse() * frente_sk).normalized()
	_alvo_olhar = Marker3D.new()
	_alvo_olhar.name = "AlvoDoOlhar"
	add_child(_alvo_olhar)
	# [osso, limite para os lados (graus, total), limite para cima/baixo, influência]
	# O pescoço só entra se o eixo dele for quase vertical: girar em torno de um eixo inclinado para
	# a frente (o do MakeHuman tem ~18°) entorta a cabeça de lado em vez de virar.
	var cfg := []
	var so_cabeca := true
	if ossos.has("pescoco"):
		var eixo := _eixo_osso(ossos["pescoco"], cima_sk)
		var e_sk := esqueleto.get_bone_global_rest(ossos["pescoco"]).basis[eixo[0]].normalized()
		if absf(e_sk.dot(cima_sk.normalized())) > cos(deg_to_rad(10.0)):
			cfg.append([ossos["pescoco"], 70.0, 40.0, 0.35])
			so_cabeca = false
	cfg.append([ossos["cabeca"], 130.0 if so_cabeca else 120.0, 70.0, 0.9 if so_cabeca else 0.85])
	var pos := 0
	for c in cfg:
		var la = ClassDB.instantiate("LookAtModifier3D")
		la.name = "Olhar_" + esqueleto.get_bone_name(c[0])
		esqueleto.add_child(la)
		esqueleto.move_child(la, 3 + pos if _pre else pos)
		pos += 1
		la.bone = c[0]
		var f := _eixo_osso(c[0], frente_sk)
		# BoneAxis: +X 0, -X 1, +Y 2, -Y 3, +Z 4, -Z 5
		la.forward_axis = f[0] * 2 + (0 if f[1] else 1)
		var u := _eixo_osso(c[0], cima_sk)
		la.primary_rotation_axis = u[0]
		la.use_secondary_rotation = true
		la.use_angle_limitation = true
		la.symmetry_limitation = true
		la.primary_limit_angle = deg_to_rad(c[1])
		la.primary_damp_threshold = 0.6
		la.secondary_limit_angle = deg_to_rad(c[2])
		la.secondary_damp_threshold = 0.6
		la.duration = 0.3
		la.transition_type = Tween.TRANS_SINE
		la.ease_type = Tween.EASE_IN_OUT
		la.target_node = la.get_path_to(_alvo_olhar)
		la.influence = 0.0
		la.active = false
		_olhar.append(la)
		_olhar_base.append(c[3])


var rosto: Rosto


func _criar_rosto() -> void:
	if esqueleto.find_bone("eyelid_upper_l") < 0:
		return
	var sk_para_modelo := (modelo.global_transform.affine_inverse() * esqueleto.global_transform).basis.orthonormalized()
	rosto = Rosto.new()
	rosto.name = "Rosto"
	rosto.eixo_x = sk_para_modelo.inverse() * Vector3(1, 0, 0)
	rosto.eixo_y = sk_para_modelo.inverse() * Vector3(0, 1, 0)
	for n in ["eye_l", "eye_r"]:
		if esqueleto.find_bone(n) >= 0:
			rosto.olhos.append(esqueleto.find_bone(n))
	for n in ["eyelid_upper_l", "eyelid_upper_r"]:
		if esqueleto.find_bone(n) >= 0:
			rosto.cima.append(esqueleto.find_bone(n))
	for n in ["eyelid_lower_l", "eyelid_lower_r"]:
		if esqueleto.find_bone(n) >= 0:
			rosto.baixo.append(esqueleto.find_bone(n))
	rosto.jaw = esqueleto.find_bone("jaw")
	esqueleto.add_child(rosto)


var molas: SpringBoneSimulator3D


## Capa com os ossos capa_1..capa_3 (malha da IA): vira mola (SpringBoneSimulator3D) que balança com o
## movimento e não atravessa as pernas (esferas no quadril, no joelho e no tornozelo).
func _criar_molas() -> void:
	# cadeias: [raiz, ponta, comprimento da ponta, rigidez, arrasto, gravidade, raio]
	var cadeias := []
	if esqueleto.find_bone("capa_1") >= 0 and esqueleto.find_bone("capa_3") >= 0:
		cadeias.append(["capa_1", "capa_3", 0.12, 0.7, 0.45, 0.8, 0.05])
	if esqueleto.find_bone("saia") >= 0:
		# a barra da sobreveste: um osso do quadril até a barra, de pé, empurrado pelas coxas e canelas
		cadeias.append(["saia", "saia", 0.5, 1.5, 0.5, 1.0, 0.06])
	# cadeias que a IA montou na bancada de esqueleto: ossos "mola_<grupo>_<n>" (cauda, cabelo, asa,
	# orelha, rabo de cavalo...), do 1 (raiz) até o último (ponta)
	var grupos := {}
	for i in esqueleto.get_bone_count():
		var nome := esqueleto.get_bone_name(i)
		if not nome.begins_with("mola_"):
			continue
		var partes := nome.rsplit("_", true, 1)
		if partes.size() != 2 or not partes[1].is_valid_int():
			continue
		var g: String = partes[0]
		var n := int(partes[1])
		if not grupos.has(g):
			grupos[g] = [n, n]
		grupos[g] = [mini(grupos[g][0], n), maxi(grupos[g][1], n)]
	for g in grupos:
		var rigidez := 0.8
		var gravidade := 0.6
		var raio := 0.03
		if "cabelo" in g or "rabo_de_cavalo" in g or "trança" in g:
			rigidez = 0.5
			gravidade = 0.8
			raio = 0.02
		elif "cauda" in g or "rabo" in g:
			rigidez = 1.2
			gravidade = 0.3
			raio = 0.05
		elif "asa" in g:
			rigidez = 2.0
			gravidade = 0.2
			raio = 0.05
		cadeias.append(["%s_%d" % [g, grupos[g][0]], "%s_%d" % [g, grupos[g][1]], 0.08, rigidez, 0.4, gravidade, raio])
	if cadeias.is_empty():
		return
	molas = SpringBoneSimulator3D.new()
	molas.name = "Molas"
	molas.setting_count = cadeias.size()
	for i in cadeias.size():
		var c: Array = cadeias[i]
		molas.set_root_bone_name(i, c[0])
		molas.set_end_bone_name(i, c[1])
		molas.set_extend_end_bone(i, true)
		if c[0] == c[1]:
			# osso sozinho: a ponta segue o eixo do próprio osso (o pai é a raiz, lá no chão)
			molas.set_end_bone_direction(i, SpringBoneSimulator3D.BONE_DIRECTION_PLUS_Y)
		molas.set_end_bone_length(i, c[2])
		molas.set_stiffness(i, c[3])
		molas.set_drag(i, c[4])
		molas.set_gravity(i, c[5])
		molas.set_radius(i, c[6])
		molas.set_enable_all_child_collisions(i, true)
	esqueleto.add_child(molas)
	for lado in ["l", "r"]:
		for par in [["thigh_", 0.13], ["calf_", 0.10], ["foot_", 0.08]]:
			var osso: String = par[0] + lado
			if esqueleto.find_bone(osso) < 0:
				continue
			var esfera := SpringBoneCollisionSphere3D.new()
			esfera.name = "Colisao_" + osso
			esfera.bone_name = osso
			esfera.radius = par[1]
			molas.add_child(esfera)


## Para onde olhar (ponto no mundo) e com quanta vontade (0 a 1). Chame a cada quadro.
func olhar_para(ponto: Vector3, peso := 1.0) -> void:
	_ponto_olhar = ponto
	_peso_olhar_alvo = clampf(peso, 0.0, 1.0)


func posicao_da_cabeca() -> Vector3:
	if esqueleto and ossos.has("cabeca"):
		return esqueleto.global_transform * esqueleto.get_bone_global_pose(ossos["cabeca"]).origin
	return corpo.global_position + Vector3.UP * 1.6 if corpo else Vector3.ZERO


func _atualizar_olhar(dt: float) -> void:
	if _olhar.is_empty():
		return
	var alvo := _peso_olhar_alvo
	if morto or _camadas["corpo"]["acao"] in ["esquivar", "dano", "dano_forte"]:
		alvo = 0.0
	# fora do campo de visão (atrás do corpo), a cabeça volta para a frente em vez de torcer
	var cabeca := posicao_da_cabeca()
	var para := _ponto_olhar - cabeca
	para.y = 0.0
	var frente := modelo.global_transform.basis.z
	frente.y = 0.0
	if para.length() > 0.01 and frente.length() > 0.01:
		alvo *= 1.0 - smoothstep(deg_to_rad(95.0), deg_to_rad(135.0), frente.angle_to(para))
	_peso_olhar = move_toward(_peso_olhar, alvo, 2.5 * dt)
	if _alvo_olhar.global_position.distance_to(_ponto_olhar) > 30.0:
		_alvo_olhar.global_position = _ponto_olhar
	else:
		_alvo_olhar.global_position = _alvo_olhar.global_position.lerp(_ponto_olhar, 1.0 - exp(-8.0 * dt))
	for k in _olhar.size():
		_olhar[k].active = _peso_olhar > 0.001
		_olhar[k].influence = _olhar_base[k] * _peso_olhar
