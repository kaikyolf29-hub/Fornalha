// Jogo de prova (Etapa 3, item 4 do PLANO_3_ETAPAS): uma IA faz um jogo pequeno completo só pelo MCP
// da Fornalha, seguindo a ordem do AGENTS.md: bíblia → arma e casa por peças → herói com controles finos
// → três inimigos → mapa com a vila usando a casa → música e efeitos → cena curta → montar → testar.
// No fim confere o que o run_test viu (andou, inimigos perseguiram, fotos de cada região, cena tocada).
//
// Uso: node jogo_de_prova.mjs <caminho do fornalha-cli> [pasta onde criar o jogo]
//   FORNALHA_PROVA_NIVEL: leve | equilibrado | qualidade (padrão) | maximo
//   FORNALHA_PROVA_VOZ=1: dubla a cena (precisa do Ignis aberto com a voz); sem isso, só legenda.
// Leva de 15 a 40 minutos sem placa (personagens realistas, mapa e engine).

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const cli = process.argv[2] || process.env.FORNALHA_CLI;
if (!cli) {
  console.error("Uso: node jogo_de_prova.mjs <caminho do fornalha-cli> [pasta]");
  process.exit(2);
}
const pai = process.argv[3] || path.join(os.tmpdir(), "fornalha-jogo-de-prova");
const nivel = process.env.FORNALHA_PROVA_NIVEL || "qualidade";
const LONGO = { timeout: 3600000, resetTimeoutOnProgress: true };

let falhas = 0;
function confere(cond, texto, extra) {
  if (cond) console.log(`  ✓ ${texto}`);
  else {
    console.log(`  ✗ ${texto}${extra ? `\n      ${JSON.stringify(extra).slice(0, 600)}` : ""}`);
    falhas++;
  }
}

const client = new Client({ name: "jogo-de-prova", version: "1.0.0" });
// o ambiente inteiro (DISPLAY/WAYLAND para a engine abrir a janela e tirar as fotos)
await client.connect(new StdioClientTransport({ command: cli, args: ["mcp"], env: { ...process.env }, stderr: "inherit" }));

async function chamar(nome, args) {
  const t0 = Date.now();
  const r = await client.callTool({ name: nome, arguments: args }, undefined, LONGO);
  const s = ((Date.now() - t0) / 1000).toFixed(0);
  if (r.isError) {
    console.log(`  ✗ ${nome} (${s} s): ${r.content?.[0]?.text?.slice(0, 800)}`);
    falhas++;
    return null;
  }
  console.log(`  · ${nome} (${s} s)`);
  return r.structuredContent;
}

console.log(`Jogo de prova em ${pai} (nível ${nivel})`);
fs.mkdirSync(pai, { recursive: true });
const proj = await chamar("create_project", { nome: "Brasa Antiga", pasta_pai: pai, genero: "action RPG", camera: "terceira pessoa" });
const raiz = proj?.raiz;
confere(raiz && fs.existsSync(path.join(raiz, "AGENTS.md")), "projeto com o guia para qualquer IA");

// 1. bíblia: paleta, estilo, áreas e nível de qualidade
await chamar("update_project", {
  alteracoes: {
    nivel,
    guia_visual: { paleta: ["#6b4a2b", "#7a2e22", "#4e5258", "#c9a227"], texto_de_estilo: "medieval sombrio, realista, cores terrosas" },
    mundo: { areas: [{ id: "vila", nome: "Vila de Brasa", tipo: "vila" }, { id: "mata", nome: "Mata Escura", tipo: "floresta" }, { id: "cripta", nome: "Cripta", tipo: "masmorra" }] },
  },
});

// 2. arma e casa montadas por peças (a forma que a IA descreve olhando a referência)
const espada = await chamar("generate_3d", {
  tipo: "arma", nome: "espada_de_aren",
  materiais: { aco: { cor: "#c9ced4", tipo: "metal", rugosidade: 0.25 }, guarda: { cor: "#8c6a2a", tipo: "metal", rugosidade: 0.4 }, couro: { cor: "#3a2416", tipo: "couro" } },
  pecas: [
    { tipo: "extrusao", material: "aco", espessura: 0.007, gume: 0.016, contorno: [[-0.026, 0.11], [0.026, 0.11], [0.024, 0.55], [0.02, 0.86], [0, 0.98], [-0.02, 0.86], [-0.024, 0.55]] },
    { tipo: "extrusao", material: "guarda", espessura: 0.03, gume: 0.006, borda: 0.012,
      contorno: [[-0.13, 0.085], [-0.1, 0.095], [-0.03, 0.1], [0.03, 0.1], [0.1, 0.095], [0.13, 0.085], [0.135, 0.108], [0.1, 0.118], [0.03, 0.115], [-0.03, 0.115], [-0.1, 0.118], [-0.135, 0.108]] },
    { tipo: "torno", material: "couro", lados: 12, perfil: [[0, -0.11], [0.016, -0.11], [0.018, -0.05], [0.0175, 0.02], [0.016, 0.085], [0, 0.085]] },
    { tipo: "torno", material: "guarda", lados: 16, perfil: [[0, -0.175], [0.022, -0.168], [0.032, -0.145], [0.026, -0.122], [0.012, -0.112], [0, -0.11]] },
  ],
});
confere(espada && fs.existsSync(espada.arquivos?.modelo || ""), "espada montada por peças");
const casa = await chamar("generate_3d", {
  tipo: "objeto", nome: "casa_brasa",
  materiais: { pedra: { cor: "#9a948a", tipo: "pedra" }, telha: { cor: "#5a3a2e", tipo: "telha" }, madeira: { cor: "#4a3324", tipo: "madeira" }, janela: { cor: "#141210" } },
  pecas: [
    { tipo: "caixa", material: "pedra", centro: [0, 0, 1.6], tamanho: [7, 5, 3.2], chanfro: 0.05 },
    { tipo: "extrusao", plano: "lado", material: "pedra", espessura: 7.0, contorno: [[-2.5, 3.2], [2.5, 3.2], [0, 5.6]] },
    { tipo: "caixa", material: "telha", centro: [0, -1.35, 4.45], tamanho: [7.6, 3.4, 0.18], rotacao: [43.8, 0, 0] },
    { tipo: "caixa", material: "telha", centro: [0, 1.35, 4.45], tamanho: [7.6, 3.4, 0.18], rotacao: [-43.8, 0, 0] },
    { tipo: "caixa", material: "pedra", centro: [2.2, 1.0, 5.2], tamanho: [0.8, 0.8, 2.6], chanfro: 0.04 },
    { tipo: "caixa", material: "madeira", centro: [0, -2.55, 1.1], tamanho: [1.2, 0.12, 2.2] },
    { tipo: "caixa", material: "janela", centro: [-2.2, -2.53, 1.7], tamanho: [0.9, 0.08, 1.0], espelhar: "x" },
  ],
});
const casaGlb = casa?.arquivos?.modelo || "";
confere(fs.existsSync(casaGlb), "casa montada por peças");

// 3. herói com os controles finos (penteado, barba, idade) e três inimigos
const heroi = await chamar("create_character", {
  nome: "Aren", papel: "protagonista", descricao: "andarilho de meia-idade, ex-ferreiro, com espada", arma: "espada",
  idade: 48, genero: "masculino",
  cabelo: { penteado: "short04", cor: "#4f4842", volume_cm: 1.2, agrupamento: 0.6, ondulacao: 0.25 },
  barba: { tipo: "cheia", cor: "#5b534b", comprimento_cm: 2.0, densidade: 1.1 },
});
confere(heroi && fs.existsSync(heroi.arquivos?.modelo || ""), "herói criado", heroi?.avisos);
const inimigos = [];
for (const pedido of [
  { papel: "inimigo", tipo: "orc", descricao: "orc grandalhão com martelo", arma: "martelo" },
  { papel: "inimigo", tipo: "zumbi", descricao: "zumbi de aldeia, camponês morto-vivo", arma: "nenhuma" },
  { papel: "inimigo", descricao: "mercenário de capuz com machado", arma: "machado" },
]) {
  const r = await chamar("create_character", pedido);
  const id = r?.ficha?.id;
  confere(id && fs.existsSync(path.join(raiz, `Enemies/${id}/${id}.glb`)), `inimigo ${id || pedido.descricao}`);
  if (id) inimigos.push(id);
}

// 4. mapa pelo plano: a vila usa a casa montada; floresta; masmorra na encosta; rio
const mapa = await chamar("generate_map", {
  plano: {
    tamanho_m: 384, relevo: { estilo: "colinas", altura_m: 30 }, clima: "temperado", hora: "tarde", nevoa: 0.3, rio: true,
    regioes: [
      { id: "vila", tipo: "vila", centro: [0, 0], raio_m: 55, casas: [path.relative(raiz, casaGlb).split(path.sep).join("/")] },
      { id: "mata", tipo: "floresta", posicao: "norte", raio_m: 70 },
      { id: "cripta", tipo: "masmorra", posicao: "leste", raio_m: 40 },
    ],
    spawn: "vila",
  },
});
confere(mapa?.medidas?.aprovado === true, "mapa aprovado nas medidas", mapa?.medidas);
confere(!(mapa?.avisos || []).some((a) => a.includes("não existe")), "a vila achou a casa montada", mapa?.avisos);

// 5. som: música de duas situações e os efeitos
await chamar("generate_music", { situacao: "vila", compassos: 16 });
await chamar("generate_music", { situacao: "combate", compassos: 16 });
const sfx = await chamar("generate_sfx", {});
confere(sfx?.arquivos?.length >= 10, "efeitos sonoros");

// 6. cena curta: o herói encontra o primeiro inimigo
const alvo = inimigos[0] || "";
const cena = await chamar("create_cutscene", {
  id: "chegada", sem_voz: process.env.FORNALHA_PROVA_VOZ !== "1",
  roteiro: [
    { quem: "aren", fala: "Então é aqui que a brasa se apagou.", camera: "close", olhar_para: alvo },
    { quem: alvo, fala: "Volte por onde veio, ferreiro.", camera: "ombro", olhar_para: "aren" },
    { quem: "aren", fala: "Não sem o que vim buscar.", camera: "dois", olhar_para: alvo },
  ],
});
confere(cena && fs.existsSync(path.join(raiz, "Cutscenes/chegada.cena.json")), "cena curta gravada");

// 7. montar e testar na engine
// um inimigo perto do início (os do mapa ficam na masmorra, longe para os segundos do teste)
await chamar("import_to_engine", { inimigo_perto: true });
const teste = await chamar("run_test", { segundos: 25 });
console.log(JSON.stringify(teste, null, 1).slice(0, 4000));
confere(teste?.passou === true, "run_test passou", teste?.erros);
confere((teste?.jogador?.andou_m ?? 0) > 3, "o jogador andou no mapa");
confere((teste?.inimigos?.perseguiram ?? 0) >= 1, "inimigo viu e perseguiu", teste?.inimigos);
confere((teste?.inimigos?.total ?? 0) >= 3, "os três inimigos no jogo", teste?.inimigos);
confere((teste?.fotos_mapa || []).length >= 3 || !process.env.DISPLAY, "fotos de cada região do mapa", teste?.fotos_mapa);
confere(teste?.cena_curta?.linhas?.length === 3, "a cena curta tocou as 3 linhas", teste?.cena_curta);
const lic = await chamar("check_licenses", {});
confere(lic && (lic.sem_recibo || []).length === 0, "todo arquivo com recibo", lic?.sem_recibo);
await chamar("export_credits", {});

await client.close();
console.log(falhas ? `\n${falhas} falha(s). Jogo em ${raiz}` : `\nJogo de prova completo em ${raiz}`);
process.exit(falhas ? 1 : 0);
