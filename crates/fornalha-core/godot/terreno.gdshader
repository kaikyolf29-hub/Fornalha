shader_type spatial;
// Terreno da bancada de mapa da Fornalha: quatro camadas (grama, terra, rocha, areia ou neve) pintadas
// pela pintura.png (uma camada por canal). Com as texturas CC0 do pacote de materiais, cada camada usa
// a sua; sem elas, cor com variação. Rocha em projeção triplanar (não estica nos barrancos) e as outras
// com duas amostras giradas (sem a repetição aparecer de longe).
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D pintura : hint_default_black, filter_linear, repeat_disable;
uniform float tamanho_m = 512.0;
uniform float escala_uv = 0.25;
uniform vec4 cor_0 : source_color = vec4(0.30, 0.45, 0.20, 1.0);
uniform vec4 cor_1 : source_color = vec4(0.48, 0.38, 0.27, 1.0);
uniform vec4 cor_2 : source_color = vec4(0.50, 0.48, 0.45, 1.0);
uniform vec4 cor_3 : source_color = vec4(0.77, 0.69, 0.53, 1.0);
// 1 = a camada tem textura (grama, terra, rocha, areia/neve)
uniform vec4 com_textura = vec4(0.0);
uniform sampler2D tex_0 : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D tex_1 : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D tex_2 : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D tex_3 : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D nrm_0 : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D nrm_1 : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D nrm_2 : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D nrm_3 : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float forca_normal = 0.8;

varying vec3 pos_mundo;
varying vec3 normal_mundo;

void vertex() {
	pos_mundo = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	normal_mundo = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

float sorteio(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float ruido(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = sorteio(i);
	float b = sorteio(i + vec2(1.0, 0.0));
	float c = sorteio(i + vec2(0.0, 1.0));
	float d = sorteio(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

vec4 duas(sampler2D t, vec2 uv, float m) {
	vec2 uv2 = mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * uv * 0.71 + vec2(0.37, 0.11);
	return mix(texture(t, uv), texture(t, uv2), m);
}

vec4 tri(sampler2D t, vec3 p, vec3 pesos) {
	return texture(t, p.zy) * pesos.x + texture(t, p.xz) * pesos.y + texture(t, p.xy) * pesos.z;
}

void fragment() {
	vec4 w = texture(pintura, pos_mundo.xz / tamanho_m + 0.5);
	// bordas das camadas recortadas com ruído (sem o borrão da pintura de 1 m)
	float n = ruido(pos_mundo.xz * 0.45) * 0.65 + ruido(pos_mundo.xz * 1.7) * 0.35;
	w = max(w + (n - 0.5) * vec4(0.0, 0.5, 0.35, 0.4), vec4(0.0));
	w = pow(w, vec4(2.0));
	w /= max(dot(w, vec4(1.0)), 1e-4);
	vec2 uv = pos_mundo.xz * escala_uv;
	float m = smoothstep(0.3, 0.7, ruido(pos_mundo.xz * 0.04));
	vec3 pesos = pow(abs(normal_mundo), vec3(4.0));
	pesos /= dot(pesos, vec3(1.0));
	vec3 p = pos_mundo * escala_uv;
	float var = 0.88 + 0.24 * ruido(pos_mundo.xz * 0.5);
	vec3 c0 = mix(cor_0.rgb * var, duas(tex_0, uv, m).rgb, com_textura.x);
	vec3 c1 = mix(cor_1.rgb * var, duas(tex_1, uv, m).rgb, com_textura.y);
	vec3 c2 = mix(cor_2.rgb * var, tri(tex_2, p, pesos).rgb, com_textura.z);
	vec3 c3 = mix(cor_3.rgb * var, duas(tex_3, uv, m).rgb, com_textura.w);
	ALBEDO = c0 * w.x + c1 * w.y + c2 * w.z + c3 * w.w;
	vec3 plano = vec3(0.5, 0.5, 1.0);
	vec3 n0 = mix(plano, duas(nrm_0, uv, m).rgb, com_textura.x);
	vec3 n1 = mix(plano, duas(nrm_1, uv, m).rgb, com_textura.y);
	vec3 n2 = mix(plano, texture(nrm_2, p.xz).rgb, com_textura.z);
	vec3 n3 = mix(plano, duas(nrm_3, uv, m).rgb, com_textura.w);
	NORMAL_MAP = n0 * w.x + n1 * w.y + n2 * w.z + n3 * w.w;
	NORMAL_MAP_DEPTH = forca_normal;
	ROUGHNESS = 0.92 - 0.1 * w.z;
	SPECULAR = 0.3;
}
