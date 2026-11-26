shader_type spatial;
// Contorno do visual anime: a casca da malha empurrada pela normal (cresce com a distância, para a
// linha ficar com a mesma grossura na tela) e desenhada só por dentro. Gerado pela Fornalha.
render_mode unshaded, cull_front, depth_draw_opaque;

uniform vec4 cor : source_color = vec4(0.09, 0.07, 0.08, 1.0);
uniform float espessura = 0.0035;

void vertex() {
	float d = -(MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).z;
	VERTEX += NORMAL * espessura * clamp(d, 0.6, 12.0);
}

void fragment() {
	ALBEDO = cor.rgb;
}
