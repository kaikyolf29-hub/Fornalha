shader_type spatial;
// Cabelo da Fornalha (padrão AAA): cards com atlas de mechas, transparência pontilhada (sem erro
// de ordem; com TAA fica macia; funciona até no renderizador de compatibilidade), duas faixas de brilho anisotrópico pela direção do fio (Kajiya-Kay: uma
// branca deslocada para a ponta e uma tingida pela cor do cabelo deslocada para a raiz), raiz mais
// escura e luz atravessando contra a luz. Gerado pela Fornalha; pode editar à vontade.
render_mode cull_disabled, depth_draw_opaque;

uniform sampler2D atlas : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D dados : hint_default_white, filter_linear_mipmap;  // R oclusão, G profundidade, B raiz→ponta
uniform sampler2D normais : hint_normal, filter_linear_mipmap;  // normal de cada fio (cilindro)
uniform float rugosidade : hint_range(0.0, 1.0) = 0.55;
uniform float brilho_primario : hint_range(0.0, 1.0) = 0.06;
uniform float brilho_secundario : hint_range(0.0, 1.0) = 0.1;

varying float raiz_v;
varying float desvio_v;

varying vec3 fio;

float limiar_pontilhado(vec2 p) {
	const float bayer[16] = float[16](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0, 3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);
	ivec2 q = ivec2(mod(p, 4.0));
	float b = (bayer[q.y * 4 + q.x] + 0.5) / 16.0;
	float r = fract(sin(dot(floor(p), vec2(12.9898, 78.233))) * 43758.5453);
	return clamp(mix(b, r, 0.35), 0.04, 0.96);
}

void vertex() {
	// o V do UV corre ao longo do fio: a binormal é a direção do fio
	fio = normalize((MODELVIEW_MATRIX * vec4(BINORMAL, 0.0)).xyz);
}

void fragment() {
	vec4 c = texture(atlas, UV);
	vec3 d = texture(dados, UV).rgb;
	raiz_v = d.b;
	desvio_v = d.g - 0.5;  // cada fio do atlas com o seu valor: o brilho quebra fio a fio
	ALBEDO = c.rgb * COLOR.rgb;  // tom de cada mecha (cor de vértice; branco quando não tem)
	NORMAL_MAP = texture(normais, UV).rgb;
	NORMAL_MAP_DEPTH = 0.9;
	// transparência por pontilhado (Bayer 4x4 + ruído por fragmento): o mesmo efeito do alpha hash,
	// mas funciona também no renderizador de compatibilidade (placas antigas, sem Vulkan)
	if (c.a < limiar_pontilhado(FRAGCOORD.xy)) {
		discard;
	}
	// card de duas faces: no verso a engine inverte a normal, mas a normal veio da casca lisa do penteado
	// e tem de apontar para fora dos dois lados (senão os cards virados de costas ficam escuros: manchas)
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
	AO = d.r;
	AO_LIGHT_AFFECT = 0.5;
	ROUGHNESS = rugosidade;
	SPECULAR = 0.0;
	BACKLIGHT = c.rgb * 0.4;
}

float kajiya(vec3 t, vec3 h, float expoente) {
	float th = dot(t, h);
	float atenua = smoothstep(-1.0, 0.0, th);
	return atenua * pow(sqrt(max(0.0, 1.0 - th * th)), expoente);
}

void light() {
	vec3 h = normalize(LIGHT + VIEW);
	float nl = dot(NORMAL, LIGHT);
	// difuso "envolvente": o cabelo é um volume, a luz contorna
	DIFFUSE_LIGHT += max((nl + 0.45) / 1.45, 0.0) * ATTENUATION * LIGHT_COLOR / PI;
	// deslocamento da faixa de brilho diferente em cada fio (sem faixa lisa "de plástico")
	vec3 t1 = normalize(fio + NORMAL * (-0.08 + 0.3 * desvio_v));
	vec3 t2 = normalize(fio + NORMAL * (0.12 + 0.3 * desvio_v));
	// brilho só onde a luz bate, mais fraco na raiz (fios de baixo ficam na sombra dos de cima)
	float vis = smoothstep(0.0, 0.35, nl) * ATTENUATION * mix(0.25, 1.0, raiz_v) * (0.55 + 0.9 * (desvio_v + 0.5));
	SPECULAR_LIGHT += (kajiya(t1, h, 280.0) * brilho_primario + kajiya(t2, h, 60.0) * brilho_secundario * ALBEDO) * vis * LIGHT_COLOR / PI;
}
