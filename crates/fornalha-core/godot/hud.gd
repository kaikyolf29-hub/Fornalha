extends CanvasLayer
## Barra de vida e ajuda dos controles. Gerado pela Fornalha.

var barra: ProgressBar
var rotulo: Label


func _ready() -> void:
	var caixa := VBoxContainer.new()
	caixa.position = Vector2(24, 20)
	add_child(caixa)
	barra = ProgressBar.new()
	barra.custom_minimum_size = Vector2(260, 22)
	barra.show_percentage = false
	var estilo := StyleBoxFlat.new()
	estilo.bg_color = Color("#e2541b")
	barra.add_theme_stylebox_override("fill", estilo)
	caixa.add_child(barra)
	rotulo = Label.new()
	rotulo.text = "WASD andar · Shift correr · Espaço pular · Clique atacar · Esc mouse"
	rotulo.add_theme_color_override("font_color", Color(1, 1, 1, 0.75))
	caixa.add_child(rotulo)
	await get_tree().process_frame
	var jogador := get_tree().get_first_node_in_group("jogador")
	if jogador:
		jogador.vida_mudou.connect(_vida)
		_vida(jogador.vida, jogador.vida_max)


func _vida(vida: int, vida_max: int) -> void:
	barra.max_value = vida_max
	barra.value = vida
