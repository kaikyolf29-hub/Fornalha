shader_type spatial;
// Água da bancada de mapa da Fornalha (rio e lago): cor pela espessura da água que se vê (raso claro,
// fundo escuro), ondinhas que andam, reflexo do céu. Funciona no Forward+ e no modo compatibilidade.
render_mode blend_mix, depth_draw_always, cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform vec4 cor_rasa : source_color = vec4(0.22, 0.44, 0.45, 1.0);
uniform vec4 cor_funda : source_color = vec4(0.05, 0.17, 0.23, 1.0);
uniform float profundidade_cor = 2.5;
uniform float velocidade = 1.0;
uniform sampler2D textura_profundidade : hint_depth_texture, filter_linear_mipmap;

varying vec3 pos_mundo;

void vertex() {
	pos_mundo = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	float t = TIME * velocidade;
	vec2 p = pos_mundo.xz;
	// três ondas cruzadas: a derivada vira a normal
	vec2 d1 = vec2(0.9, 0.4), d2 = vec2(-0.5, 1.1), d3 = vec2(1.7, -1.3);
	vec2 g = d1 * cos(dot(p, d1) + t * 1.3) * 0.05 + d2 * cos(dot(p, d2) - t * 1.1) * 0.04 + d3 * cos(dot(p, d3) + t * 2.1) * 0.02;
	NORMAL_MAP = normalize(vec3(0.5 - g.x, 0.5 - g.y, 1.0));
	float prof = texture(textura_profundidade, SCREEN_UV).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vec3 ndc = vec3(SCREEN_UV, prof) * 2.0 - 1.0;
#else
	vec3 ndc = vec3(SCREEN_UV * 2.0 - 1.0, prof);
#endif
	vec4 fundo = INV_PROJECTION_MATRIX * vec4(ndc, 1.0);
	fundo.xyz /= fundo.w;
	float espessura = clamp((-fundo.z - (-VERTEX.z)) / profundidade_cor, 0.0, 1.0);
	ALBEDO = mix(cor_rasa.rgb, cor_funda.rgb, espessura);
	ALPHA = mix(0.45, 0.94, espessura);
	ROUGHNESS = 0.04;
	METALLIC = 0.0;
	SPECULAR = 0.6;
}
