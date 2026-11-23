extends Node3D
## Cena principal montada pela Fornalha: toca a música da área ao abrir.

@export_file("*.wav", "*.ogg") var musica := ""


func _ready() -> void:
	_cor_do_chao()
	_grama()
	var sons := get_node_or_null("/root/Sons")
	if musica != "" and sons:
		sons.tocar_musica(musica)


## O chão do mundo traz a variação de cor por vértice (terra batida nas áreas e nos caminhos, grama seca,
## baixadas mais escuras): o material dele passa a multiplicar a textura pela cor do vértice.
func _cor_do_chao() -> void:
	for n in find_children("chao*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if mi.mesh == null:
			continue
		for i in mi.mesh.get_surface_count():
			var m := mi.get_active_material(i)
			if m is BaseMaterial3D and not (m as BaseMaterial3D).vertex_color_use_as_albedo:
				var novo := (m as BaseMaterial3D).duplicate() as BaseMaterial3D
				novo.vertex_color_use_as_albedo = true
				novo.vertex_color_is_srgb = true
				mi.set_surface_override_material(i, novo)


const GRAMA_SHADER := """
shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;
uniform vec3 cor_base : source_color = vec3(0.13, 0.22, 0.07);
uniform vec3 cor_ponta : source_color = vec3(0.47, 0.55, 0.22);
varying float altura;
void vertex() {
	altura = UV.y;
	vec3 mundo = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float vento = sin(TIME * 1.6 + mundo.x * 0.35 + mundo.z * 0.21) + 0.4 * sin(TIME * 3.1 + mundo.z * 0.9);
	VERTEX.x += vento * 0.07 * UV.y * UV.y;
	VERTEX.z += vento * 0.03 * UV.y * UV.y;
}
void fragment() {
	// folhas finas desenhadas no quadro: mais estreitas na ponta
	float folha = abs(fract(UV.x * 5.0 + floor(UV.x * 5.0) * 0.37) - 0.5) * 2.0;
	if (folha > 1.0 - UV.y * 0.92) { discard; }
	vec3 c = mix(cor_base, cor_ponta, UV.y) * COLOR.rgb;
	ALBEDO = c;
	ROUGHNESS = 0.85;
	SPECULAR = 0.25;
	BACKLIGHT = vec3(0.25, 0.3, 0.12);
	AO = mix(0.35, 1.0, UV.y);
	AO_LIGHT_AFFECT = 0.6;
}
"""


## Tufos de grama (MultiMesh) espalhados no chão do mundo, onde a cor do chão é de grama (não na terra
## batida dos caminhos e do largo das áreas) e onde não é encosta; balançam com o vento e somem longe.
## Feito ao abrir o jogo: o servidor sem tela da montagem não guarda os dados do MultiMesh.
func _grama() -> void:
	var chao: MeshInstance3D = null
	for n in find_children("chao*", "MeshInstance3D", true, false):
		chao = n
		break
	if chao == null or chao.mesh == null or chao.mesh.get_surface_count() == 0:
		return
	var xf := chao.global_transform
	var arr := chao.mesh.surface_get_arrays(0)
	var vs: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
	var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX]
	var cores = arr[Mesh.ARRAY_COLOR]
	if vs.is_empty() or idx.is_empty():
		return
	var tufo := _malha_do_tufo()
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var celulas := {}
	var tamanho := 18.0
	var tentativas := mini(140000, idx.size() / 3 * 6)
	for _i in tentativas:
		var t := rng.randi_range(0, idx.size() / 3 - 1) * 3
		var a := vs[idx[t]]
		var b := vs[idx[t + 1]]
		var c := vs[idx[t + 2]]
		var n := (b - a).cross(c - a).normalized()
		if absf(n.y) < 0.86:
			continue
		var u := rng.randf()
		var v := rng.randf()
		if u + v > 1.0:
			u = 1.0 - u
			v = 1.0 - v
		var p := a + (b - a) * u + (c - a) * v
		var cor := Color(1, 1, 1)
		if cores is PackedColorArray and not (cores as PackedColorArray).is_empty():
			var ca: PackedColorArray = cores
			cor = ca[idx[t]] * (1.0 - u - v) + ca[idx[t + 1]] * u + ca[idx[t + 2]] * v
		# terra batida (bem mais vermelho que verde) não tem grama; a grama seca tem
		if cor.r > cor.g * 1.12:
			continue
		var mundo := xf * p
		var chave := Vector2i(floori(mundo.x / tamanho), floori(mundo.z / tamanho))
		if not celulas.has(chave):
			celulas[chave] = []
		var base := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * rng.randf_range(0.7, 1.35))
		celulas[chave].append([Transform3D(base, mundo), Color(cor.r * rng.randf_range(0.85, 1.05), cor.g, cor.b * rng.randf_range(0.8, 1.0))])
	var mat := ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = GRAMA_SHADER
	mat.shader = sh
	tufo.surface_set_material(0, mat)
	var pai := Node3D.new()
	pai.name = "Grama"
	add_child(pai)
	for chave in celulas:
		var lista: Array = celulas[chave]
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.use_colors = true
		mm.mesh = tufo
		mm.instance_count = lista.size()
		for k in lista.size():
			mm.set_instance_transform(k, lista[k][0])
			mm.set_instance_color(k, lista[k][1])
		var mi := MultiMeshInstance3D.new()
		mi.name = "Grama_%d_%d" % [chave.x, chave.y]
		mi.multimesh = mm
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.visibility_range_end = 48.0
		mi.visibility_range_end_margin = 8.0
		mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		pai.add_child(mi)


func _malha_do_tufo() -> ArrayMesh:
	# três quadros cruzados (0,4 m de largura, 0,45 m de altura); UV.y = 0 no chão, 1 na ponta
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for k in 3:
		var ang := k * PI / 3.0
		var d := Vector3(cos(ang), 0, sin(ang)) * 0.2
		var cantos := [[-d, 0.0, 0.0], [d, 1.0, 0.0], [d + Vector3(0, 0.45, 0), 1.0, 1.0], [-d + Vector3(0, 0.45, 0), 0.0, 1.0]]
		for tri in [[0, 1, 2], [0, 2, 3]]:
			for i in tri:
				st.set_uv(Vector2(cantos[i][1], cantos[i][2]))
				st.set_normal(Vector3.UP)
				st.add_vertex(cantos[i][0])
	return st.commit()
