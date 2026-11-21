extends CharacterBody3D
## Inimigo com IA básica: fica parado, persegue o jogador quando ele chega
## perto, ataca de perto e morre. Gerado pela Fornalha.

@export var velocidade := 3.2
@export var vida_max := 100
@export var dano := 10
@export var distancia_visao := 14.0
@export var distancia_ataque := 1.8
@export var tempo_entre_ataques := 1.4

enum Estado { PARADO, PERSEGUINDO, ATACANDO, MORTO }
var estado := Estado.PARADO
var vida := 100
var gravidade: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var anim: AnimationPlayer
var _espera := 0.0
var _origem := Vector3.ZERO

@onready var modelo: Node3D = $Modelo


func _ready() -> void:
	add_to_group("inimigos")
	vida = vida_max
	_origem = global_position
	anim = _achar(modelo)
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
		velocity.x = 0.0
		velocity.z = 0.0
		if estado != Estado.MORTO:
			_tocar("parado")
		move_and_slide()
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
			velocity.x = d.x * velocidade
			velocity.z = d.z * velocidade
			modelo.rotation.y = lerp_angle(modelo.rotation.y, atan2(d.x, d.z), 8.0 * dt)
			_tocar("andar")
		Estado.ATACANDO:
			velocity.x = 0.0
			velocity.z = 0.0
			modelo.rotation.y = lerp_angle(modelo.rotation.y, atan2(para.x, para.z), 8.0 * dt)
			if _espera == 0.0:
				_espera = tempo_entre_ataques
				_tocar("atacar", true)
				await get_tree().create_timer(0.4).timeout
				if estado == Estado.ATACANDO and is_instance_valid(jogador):
					jogador.receber_dano(dano)
		_:
			velocity.x = 0.0
			velocity.z = 0.0
			_tocar("parado")
	move_and_slide()


func receber_dano(quanto: int) -> void:
	if estado == Estado.MORTO:
		return
	vida = max(vida - quanto, 0)
	if vida == 0:
		estado = Estado.MORTO
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
	if anim == null or not anim.has_animation(nome):
		return
	if reiniciar or anim.current_animation != nome:
		if anim.current_animation in ["atacar", "dano"] and anim.is_playing() and not reiniciar:
			return
		anim.play(nome, 0.15)
