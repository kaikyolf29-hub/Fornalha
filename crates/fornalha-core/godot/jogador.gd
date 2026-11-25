extends CharacterBody3D
## Jogador em terceira pessoa. Gerado pela Fornalha; pode editar à vontade.
## WASD anda, Shift corre, Espaço pula, clique esquerdo ataca, direito defende,
## Ctrl esquiva, Esc solta o mouse. O movimento (AnimationTree, pés no chão e olhar)
## fica em movimento.gd.

signal vida_mudou(vida: int, vida_max: int)
## Numa cena curta (CenasCurtas.tocar) o jogador fica parado e sem controle.
var em_cena := false

@export var velocidade := 4.0
@export var velocidade_corrida := 7.5
@export var forca_pulo := 5.5
@export var sensibilidade := 0.004
@export var vida_max := 100
@export var dano_ataque := 34
@export var alcance_ataque := 2.2
@export var aceleracao := 16.0   # m/s² ao sair andando (inércia de jogo de ação)
@export var frenagem := 22.0     # m/s² ao soltar as teclas

var vida := 100
var gravidade: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var anim: AnimationPlayer
var movimento: Node     # movimento.gd: locomoção misturada, camadas, pés no chão e olhar
var acao := ""          # animação de ação em andamento (atacar, defender, esquivar, dano)
var morto := false
var entrada_teste := Vector2.ZERO   # o teste automático da Fornalha mexe aqui
var _tempo_passo := 0.0
const GOLPES := ["atacar", "atacar_2", "atacar_3"]
var _combo := 0
var _proximo_golpe := false   # clicou durante o golpe: emenda o próximo (memória de comando)
var _no_ar := false
var _ragdoll: PhysicalBoneSimulator3D

@onready var modelo: Node3D = $Modelo
@onready var braco: SpringArm3D = $BracoCamera
var _malhas: Array[GeometryInstance3D] = []
var _transparencia := 0.0
var _inclinacao_neutra := 0.0   # inclinação inicial da câmera: olhar reto para a frente


func _ready() -> void:
	add_to_group("jogador")
	vida = vida_max
	_inclinacao_neutra = braco.rotation.x
	_criar_controles()
	anim = _achar_animacoes(modelo)
	_ragdoll = preload("res://Scripts/fornalha/fisica.gd").preparar(modelo, self)
	_juntar_malhas(modelo)
	if anim:
		movimento = preload("res://Scripts/fornalha/movimento.gd").criar(self, modelo, anim)
		if movimento:
			movimento.acao_terminou.connect(_fim_da_animacao)
			movimento.passo.connect(func(_lado: int) -> void: _som("passo", global_position))
		else:
			anim.animation_finished.connect(_fim_da_animacao)
		_tocar("parado")
	var teste := get_node_or_null("/root/TesteFornalha")
	if teste == null or not teste.ativo:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	vida_mudou.emit(vida, vida_max)


func _criar_controles() -> void:
	var teclas := {"frente": KEY_W, "tras": KEY_S, "esquerda": KEY_A, "direita": KEY_D, "pular": KEY_SPACE, "correr": KEY_SHIFT, "esquivar": KEY_CTRL}
	for nome in teclas:
		if not InputMap.has_action(nome):
			InputMap.add_action(nome)
			var ev := InputEventKey.new()
			ev.physical_keycode = teclas[nome]
			InputMap.action_add_event(nome, ev)
	for par in [["atacar", MOUSE_BUTTON_LEFT], ["defender", MOUSE_BUTTON_RIGHT]]:
		if not InputMap.has_action(par[0]):
			InputMap.add_action(par[0])
			var ev := InputEventMouseButton.new()
			ev.button_index = par[1]
			InputMap.action_add_event(par[0], ev)


static func _achar_animacoes(no: Node) -> AnimationPlayer:
	if no is AnimationPlayer:
		return no
	for filho in no.get_children():
		var a := _achar_animacoes(filho)
		if a:
			return a
	return null


func _unhandled_input(evento: InputEvent) -> void:
	if em_cena:
		return
	if evento is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		braco.rotation.y -= evento.relative.x * sensibilidade
		braco.rotation.x = clamp(braco.rotation.x - evento.relative.y * sensibilidade, -1.2, 0.5)
	elif evento.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED


func _physics_process(dt: float) -> void:
	if not is_on_floor():
		velocity.y -= gravidade * dt
	if morto:
		velocity.x = 0.0
		velocity.z = 0.0
		move_and_slide()
		return
	if em_cena:  # cena curta: parado, sem controle (a cena manda)
		var parado := Vector3(velocity.x, 0.0, velocity.z).move_toward(Vector3.ZERO, frenagem * dt)
		velocity.x = parado.x
		velocity.z = parado.z
		move_and_slide()
		_animar(Vector3.ZERO, false, dt)
		return
	var entrada := Input.get_vector("esquerda", "direita", "frente", "tras") + entrada_teste
	var direcao := braco.global_transform.basis * Vector3(entrada.x, 0.0, entrada.y)
	direcao.y = 0.0
	direcao = direcao.normalized() if direcao.length() > 0.05 else Vector3.ZERO
	var correndo := Input.is_action_pressed("correr")
	var v := velocidade_corrida if correndo else velocidade
	if acao in GOLPES or acao == "defender":
		v *= 0.25
	var horizontal := Vector3(velocity.x, 0.0, velocity.z).move_toward(direcao * v, (aceleracao if direcao != Vector3.ZERO else frenagem) * dt)
	velocity.x = horizontal.x
	velocity.z = horizontal.z
	if direcao != Vector3.ZERO:
		modelo.rotation.y = lerp_angle(modelo.rotation.y, atan2(direcao.x, direcao.z), 12.0 * dt)
	if Input.is_action_just_pressed("pular") and is_on_floor():
		pular()
	if Input.is_action_just_pressed("atacar"):
		atacar()
	if Input.is_action_just_pressed("defender"):
		_acao("defender")
	if Input.is_action_just_pressed("esquivar"):
		_acao("esquivar")
	move_and_slide()
	_animar(direcao, correndo, dt)
	_esmaecer_perto_da_camera(dt)


func _juntar_malhas(no: Node) -> void:
	if no is GeometryInstance3D:
		_malhas.append(no)
	for f in no.get_children():
		_juntar_malhas(f)


## Com a câmera colada no personagem (parede atrás), o corpo fica transparente em vez de tapar a tela.
func _esmaecer_perto_da_camera(dt: float) -> void:
	var dist := braco.get_hit_length()
	var alvo := clampf((1.1 - dist) / 0.6, 0.0, 0.85)
	if is_equal_approx(alvo, _transparencia):
		return
	_transparencia = move_toward(_transparencia, alvo, dt * 4.0)
	for m in _malhas:
		m.transparency = _transparencia


func pular() -> void:
	if is_on_floor() and not morto:
		velocity.y = forca_pulo
		_acao("pular")
		_som("pulo", global_position)


func atacar() -> void:
	if morto:
		return
	if acao in GOLPES:
		_proximo_golpe = true
		return
	_golpe(0)


func _golpe(i: int) -> void:
	_combo = i
	var nome: String = GOLPES[i] if anim and anim.has_animation(GOLPES[i]) else "atacar"
	_mirar_no_mais_perto()
	_acao(nome)
	_som("golpe", global_position)
	var espera := 0.38
	if anim and anim.has_animation(nome):
		espera = clamp(anim.get_animation(nome).length * 0.45, 0.15, 0.5)
	await get_tree().create_timer(espera).timeout
	var frente := Vector3(sin(modelo.rotation.y), 0.0, cos(modelo.rotation.y))
	for inimigo in get_tree().get_nodes_in_group("inimigos"):
		var para: Vector3 = (inimigo as Node3D).global_position - global_position
		para.y = 0.0
		if para.length() < alcance_ataque and frente.dot(para.normalized()) > 0.3:
			inimigo.receber_dano(dano_ataque)
			_som("impacto", inimigo.global_position)


## Ajuda de mira: vira para o inimigo mais perto (até 3,5 m) antes de golpear.
func _mirar_no_mais_perto() -> void:
	var melhor: Node3D = null
	var menor := 3.5
	for inimigo in get_tree().get_nodes_in_group("inimigos"):
		var no := inimigo as Node3D
		if no == null or no.get("estado") == 3:
			continue
		var d := no.global_position.distance_to(global_position)
		if d < menor:
			menor = d
			melhor = no
	if melhor:
		var para := melhor.global_position - global_position
		modelo.rotation.y = atan2(para.x, para.z)


func receber_dano(quanto: int) -> void:
	if morto:
		return
	if acao == "defender":
		quanto = int(quanto * 0.2)
	vida = max(vida - quanto, 0)
	vida_mudou.emit(vida, vida_max)
	if vida == 0:
		morto = true
		var caiu: bool = preload("res://Scripts/fornalha/fisica.gd").cair(_ragdoll, anim, Vector3.UP * 6.0)
		if movimento:
			movimento.morrer(caiu)
		elif not caiu:
			_tocar("morrer")
	else:
		_acao("dano")


func _acao(nome: String) -> void:
	if movimento:
		# só vira ação se a animação existe (senão a ação nunca terminaria)
		if movimento.tocar(nome) > 0.0:
			acao = nome
		return
	acao = nome
	_tocar(nome)


func _fim_da_animacao(nome: Variant) -> void:
	if String(nome) == acao:
		acao = ""
		# a sequência de golpes não continua por cima de dano, esquiva ou pulo
		var emendar: bool = _proximo_golpe and String(nome) in GOLPES and (movimento == null or movimento.acao_atual("corpo") == "")
		_proximo_golpe = false
		if emendar:
			_golpe((_combo + 1) % GOLPES.size())


func _animar(direcao: Vector3, correndo: bool, dt: float) -> void:
	if movimento == null:
		_animar_sem_arvore(direcao, correndo, dt)
		return
	# a árvore mistura a locomoção pela velocidade real; aqui só entram os eventos
	movimento.atualizar(Vector2(velocity.x, velocity.z).length(), is_on_floor(), dt)
	# a cabeça olha para onde a câmera aponta (o LookAtModifier3D limita e suaviza); para cima e
	# para baixo só a diferença em relação à câmera parada, senão ele olharia o chão o tempo todo
	var frente := -braco.global_transform.basis.z
	frente.y = 0.0
	var incl := clampf(braco.rotation.x - _inclinacao_neutra, -0.6, 0.6) * 0.7
	movimento.olhar_para(movimento.posicao_da_cabeca() + (frente.normalized() * cos(incl) + Vector3.UP * sin(incl)) * 10.0)
	var estava_no_ar := _no_ar
	_no_ar = movimento.no_ar()
	if estava_no_ar and not _no_ar and direcao == Vector3.ZERO and acao in ["", "pular"]:
		_acao("aterrissar")


## Caminho antigo (modelo sem esqueleto conhecido): toca as animações pelo nome.
func _animar_sem_arvore(direcao: Vector3, correndo: bool, dt: float) -> void:
	if not is_on_floor():
		_no_ar = true
		if acao == "" or (acao == "pular" and anim and not anim.is_playing()):
			acao = ""
			_tocar("no_ar")
		return
	if _no_ar:
		_no_ar = false
		if anim and anim.has_animation("aterrissar") and direcao == Vector3.ZERO:
			_acao("aterrissar")
			return
	if acao != "" and acao != "pular":
		return
	if direcao == Vector3.ZERO:
		acao = ""
		_tocar("parado")
	else:
		acao = ""
		# andar normal no ritmo de corrida leve; Shift é o pique
		var passo := "correr_rapido" if correndo and anim and anim.has_animation("correr_rapido") else ("correr" if correndo else "andar")
		_tocar(passo)
		_tempo_passo -= dt
		if _tempo_passo <= 0.0:
			_tempo_passo = 0.32 if correndo else 0.45
			_som("passo", global_position)


func _tocar(nome: String) -> void:
	if movimento:
		movimento.tocar(nome)  # a locomoção (parado, andar, correr) é automática
		return
	if anim and anim.has_animation(nome) and anim.current_animation != nome:
		anim.play(nome, 0.15)


func _som(nome: String, onde: Vector3) -> void:
	var sons := get_node_or_null("/root/Sons")
	if sons:
		sons.tocar(nome, onde)
