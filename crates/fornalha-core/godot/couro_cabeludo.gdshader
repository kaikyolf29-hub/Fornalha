shader_type spatial;
// Couro cabeludo da Fornalha (camada 0 do cabelo): cor do cabelo com fios curtinhos e fade na linha
// do cabelo, por pontilhado (funciona em qualquer renderizador). Gerado pela Fornalha.
render_mode cull_back, depth_draw_opaque;

uniform sampler2D textura : source_color, filter_linear_mipmap;
uniform float rugosidade = 0.75;

float limiar_pontilhado(vec2 p) {
	const float bayer[16] = float[16](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0, 3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);
	ivec2 q = ivec2(mod(p, 4.0));
	float b = (bayer[q.y * 4 + q.x] + 0.5) / 16.0;
	float r = fract(sin(dot(floor(p), vec2(12.9898, 78.233))) * 43758.5453);
	return clamp(mix(b, r, 0.35), 0.04, 0.96);
}

void fragment() {
	vec4 c = texture(textura, UV);
	if (c.a < limiar_pontilhado(FRAGCOORD.xy)) {
		discard;
	}
	ALBEDO = c.rgb;
	ROUGHNESS = rugosidade;
	SPECULAR = 0.2;
}
