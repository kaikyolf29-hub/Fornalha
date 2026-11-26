shader_type spatial;
// Visual anime da Fornalha (guia_visual.render = "anime" na bíblia): luz em faixas (claro e sombra com
// borda definida, sombra puxando para a cor escolhida), meia-faixa de transição, brilho de borda do
// lado da luz e brilho especular recortado. O contorno é o contorno.gdshader (next_pass). Gerado pela
// Fornalha; pode editar à vontade (os valores vêm da bíblia e do material de cada peça).
render_mode cull_back;

uniform sampler2D textura : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 cor : source_color = vec4(1.0);
uniform bool tem_textura = false;
uniform bool usa_alfa = false;  // cards de cabelo: recorte pelo alfa do atlas
uniform bool cor_do_vertice = false;  // tom de cada mecha
uniform vec3 cor_da_sombra : source_color = vec3(0.62, 0.55, 0.72);
uniform float sombra_minima : hint_range(0.0, 1.0) = 0.42;
uniform float borda_brilho : hint_range(0.0, 1.0) = 0.3;
uniform float brilho : hint_range(0.0, 1.0) = 0.25;

void fragment() {
	vec4 c = cor;
	if (tem_textura) {
		c *= texture(textura, UV);
	}
	if (cor_do_vertice) {
		c.rgb *= COLOR.rgb;
	}
	if (usa_alfa && c.a < 0.5) {
		discard;
	}
	ALBEDO = c.rgb;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}

void light() {
	float nl = dot(NORMAL, LIGHT);
	// duas faixas com borda fina, e a sombra projetada também em faixa
	float claro = smoothstep(0.0, 0.03, nl) * smoothstep(0.35, 0.55, ATTENUATION);
	float meio = smoothstep(0.42, 0.46, nl) * claro * 0.12;
	vec3 tom = mix(cor_da_sombra * sombra_minima, vec3(1.0), claro) + meio;
	DIFFUSE_LIGHT += tom * LIGHT_COLOR / PI;
	// brilho de borda (do lado da luz) e especular recortado
	float borda = smoothstep(0.66, 0.7, 1.0 - max(dot(NORMAL, VIEW), 0.0)) * claro * borda_brilho;
	vec3 h = normalize(LIGHT + VIEW);
	float esp = smoothstep(0.955, 0.965, dot(NORMAL, h)) * claro * brilho;
	SPECULAR_LIGHT += (borda + esp) * LIGHT_COLOR / PI;
}
