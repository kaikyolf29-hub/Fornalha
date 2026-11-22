extends CharacterBody3D
## Inimigo com IA básica: fica parado, persegue o jogador quando ele chega
## perto, ataca de perto e morre. Gerado pela Fornalha. O movimento (AnimationTree,
## pés no chão e olhar no jogador) fica em movimento.gd.

@export var velocidade := 3.2
@export var vida_max := 100
@export var dano := 10
@export var distancia_visao := 14.0
@export var distancia_ataque := 1.8
@export var tempo_entre_ataques := 1.4
@export var aceleracao := 12.0

enum Estado { PARADO, PERSEGUINDO, ATACANDO, MORTO }
var estado := Estado.PARADO
var vida := 100
var gravidade: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var anim: AnimationPlayer
var movimento: Node     # movimento.gd
var _espera := 0.0
var _origem := Vector3.ZERO

@onready var modelo: Node3D = $Modelo
var _ragdoll: PhysicalBoneSimulator3D


func _ready() -> void:
	add_to_group("inimigos")
	vida = vida_max
	_origem = global_position
	anim = _achar(modelo)
	_ragdoll = preload("res://Scripts/fornalha/fisica.gd").preparar(modelo, self)
	if anim:
		movimento = preload("res://Scripts/fornalha/movimento.gd").criar(self, modelo, anim)
	_tocar("parado")


static func _achar(no: Node) -> AnimationPlayer:
	if no is AnimationPlayer:
		return no
	for f in no.get_children():
		var a := _achar(f)
		if a:
			return a
	return null


func _physics_process(dt: float) -> void:
	if not is_on_floor():
		velocity.y -= gravidade * dt
	_espera = max(_espera - dt, 0.0)
	var jogador := get_tree().get_first_node_in_group("jogador") as Node3D
	if estado == Estado.MORTO or jogador == null or jogador.get("morto"):
		_andar(Vector3.ZERO, dt)
		if estado != Estado.MORTO:
			_tocar("parado")
		move_and_slide()
		_animar(null, dt)
		return
	var para := jogador.global_position - global_position
	para.y = 0.0
	var dist := para.length()
	if dist < distancia_ataque:
		estado = Estado.ATACANDO
	elif dist < distancia_visao:
		estado = Estado.PERSEGUINDO
	else:
		estado = Estado.PARADO
	match estado:
		Estado.PERSEGUINDO:
			var d := para.normalized()
			_andar(d * velocidade, dt)
			modelo.rotation.y = lerp_angle(modelo.rotation.y, atan2(d.x, d.z), 8.0 * dt)
			_tocar("andar")
		Estado.ATACANDO:
			_andar(Vector3.ZERO, dt)
			modelo.rotation.y = lerp_angle(modelo.rotation.y, atan2(para.x, para.z), 8.0 * dt)
			if _espera == 0.0:
				_espera = tempo_entre_ataques
				_golpear(jogador)
		_:
			_andar(Vector3.ZERO, dt)
			_tocar("parado")
	move_and_slide()
	_animar(jogador, dt)


## O golpe acerta um pouco depois de começar (sem parar o quadro de física à espera).
func _golpear(jogador: Node3D) -> void:
	_tocar("atacar", true)
	await get_tree().create_timer(0.4).timeout
	if estado == Estado.ATACANDO and is_instance_valid(jogador):
		jogador.receber_dano(dano)


func _andar(alvo: Vector3, dt: float) -> void:
	if movimento == null:
		velocity.x = alvo.x
		velocity.z = alvo.z
		return
	var h := Vector3(velocity.x, 0.0, velocity.z).move_toward(alvo, aceleracao * dt)
	velocity.x = h.x
	velocity.z = h.z


## Locomoção pela velocidade real e cabeça no jogador quando ele está à vista.
func _animar(jogador: Node3D, dt: float) -> void:
	if movimento == null or estado == Estado.MORTO:
		return
	movimento.atualizar(Vector2(velocity.x, velocity.z).length(), is_on_floor(), dt)
	if jogador and estado != Estado.PARADO:
		var mov_j = jogador.get("movimento")
		var cabeca: Vector3 = mov_j.posicao_da_cabeca() if mov_j else jogador.global_position + Vector3.UP * 1.6
		movimento.olhar_para(cabeca, 1.0)
	else:
		movimento.olhar_para(global_position + modelo.global_transform.basis.z * 5.0 + Vector3.UP * 1.6, 0.0)


func receber_dano(quanto: int) -> void:
	if estado == Estado.MORTO:
		return
	vida = max(vida - quanto, 0)
	if vida == 0:
		estado = Estado.MORTO
		var jog := get_tree().get_first_node_in_group("jogador") as Node3D
		var empurrao := Vector3.ZERO
		if jog:
			empurrao = (global_position - jog.global_position).normalized() * 40.0 + Vector3.UP * 8.0
		var caiu: bool = preload("res://Scripts/fornalha/fisica.gd").cair(_ragdoll, anim, empurrao)
		if movimento:
			movimento.morrer(caiu)
		elif not caiu:
			_tocar("morrer", true)
		var sons := get_node_or_null("/root/Sons")
		if sons:
			sons.tocar("morte", global_position)
		$Colisao.set_deferred("disabled", true)
		await get_tree().create_timer(4.0).timeout
		queue_free()
	else:
		_tocar("dano", true)


func _tocar(nome: String, reiniciar := false) -> void:
	if movimento:
		movimento.tocar(nome)  # parado/andar/correr: a locomoção é automática
		return
	if anim == null or not anim.has_animation(nome):
		return
	if reiniciar or anim.current_animation != nome:
		if anim.current_animation in ["atacar", "dano"] and anim.is_playing() and not reiniciar:
			return
		anim.play(nome, 0.15)
