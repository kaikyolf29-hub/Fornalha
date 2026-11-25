// Teste de ponta a ponta do MCP da Fornalha com o SDK oficial do MCP
// (o mesmo que o Claude Code usa). Testa os dois transportes:
//   1) stdio:  <cli> mcp           (ou o comando em FORNALHA_MCP_CMD, ex.: fornalha.exe --mcp)
//   2) HTTP:   <cli> servir --porta N  →  http://127.0.0.1:N/mcp
//
// Uso: node teste.mjs <caminho do fornalha-cli>
//   FORNALHA_MCP_CMD / FORNALHA_MCP_ARGS: outro comando para o stdio (ex.: fornalha.exe --mcp)
//   FORNALHA_MCP_URL: testa o HTTP numa Fornalha já aberta (ex.: http://127.0.0.1:11480/mcp)
// Pronto da Fase 0: "o Claude Code cria um projeto novo pelo MCP".

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { spawn } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";

const cli = process.argv[2] || process.env.FORNALHA_CLI;
if (!cli && !process.env.FORNALHA_MCP_CMD) {
  console.error("Uso: node teste.mjs <caminho do fornalha-cli>");
  process.exit(2);
}

let falhas = 0;
function confere(cond, texto) {
  if (cond) console.log(`  ✓ ${texto}`);
  else {
    console.log(`  ✗ ${texto}`);
    falhas++;
  }
}

const FERRAMENTAS = [
  "get_status", "create_project", "open_project", "list_projects", "get_project", "update_project",
  "detect_gpu", "list_quality_levels", "choose_model", "list_models", "record_receipt",
  "list_receipts", "check_licenses", "export_credits",
  "create_character", "generate_concept", "generate_3d", "create_material", "create_skeleton", "generate_animation",
  "retarget_animation", "generate_sfx", "generate_music", "generate_voice", "generate_blockout", "generate_code",
  "import_to_engine", "run_test", "plan_request", "queue_job", "list_queue", "cancel_job", "check_style",
  "list_motions", "apply_motion", "check_motion", "import_motion", "show_skeleton", "edit_skeleton", "dress_character",
];

const PASTAS = ["GameDesign", "World", "Characters", "Enemies", "Items", "Weapons", "Animations",
  "Audio", "VFX", "Cutscenes", "UI", "Scripts", "blender", "ai"];

async function roteiro(client, nomeCliente, quemEsperado, home) {
  const { tools } = await client.listTools();
  const nomes = tools.map((t) => t.name);
  confere(FERRAMENTAS.every((n) => nomes.includes(n)), `tools/list traz as ${FERRAMENTAS.length} ferramentas`);
  confere(tools.every((t) => t.inputSchema?.type === "object"), "toda ferramenta tem inputSchema de objeto");

  const status = await client.callTool({ name: "get_status", arguments: {} });
  confere(status.structuredContent?.app === "Fornalha", "get_status responde");

  const pai = path.join(home, `jogos-${nomeCliente}`);
  const criado = await client.callTool({
    name: "create_project",
    arguments: { nome: `Reino de Cinzas ${nomeCliente}`, pasta_pai: pai, genero: "action RPG", camera: "terceira pessoa" },
  });
  confere(!criado.isError, `${nomeCliente} cria um projeto novo pelo MCP`);
  const raiz = criado.structuredContent?.raiz;
  confere(raiz && fs.existsSync(path.join(raiz, "game.project.json")), "game.project.json existe no disco");
  confere(raiz && PASTAS.every((p) => fs.statSync(path.join(raiz, p)).isDirectory()), "as 14 pastas padrão existem");
  const biblia = JSON.parse(fs.readFileSync(path.join(raiz, "game.project.json"), "utf8"));
  confere(biblia.conceito?.genero === "action RPG" && biblia.comercial === true, "bíblia com o conceito e comercial");
  confere(criado.content?.[0]?.type === "text", "resultado também vem em texto (compatível)");

  const atualizado = await client.callTool({
    name: "update_project",
    arguments: { alteracoes: { guia_visual: { paleta: ["#1a2b3c"], traco: "cel shading" } } },
  });
  confere(atualizado.structuredContent?.biblia?.guia_visual?.traco === "cel shading", "update_project mescla a bíblia");

  const escolha = await client.callTool({ name: "choose_model", arguments: { funcao: "cerebro", nivel: "qualidade" } });
  confere(escolha.structuredContent?.modelo?.id === "qwen3-14b", "choose_model segue a tabela de níveis");

  fs.writeFileSync(path.join(raiz, "Characters", "heroi.png"), "png de teste");
  const recibo = await client.callTool({
    name: "record_receipt",
    arguments: { arquivo: "Characters/heroi.png", modelo: "flux2-klein-4b", prompt: "herói com machado", seed: 7 },
  });
  confere(recibo.structuredContent?.recibo?.quem_pediu === quemEsperado, `recibo marca quem pediu: ${quemEsperado}`);

  fs.writeFileSync(path.join(raiz, "Audio", "fala.wav"), "wav de teste");
  const bloqueado = await client.callTool({ name: "record_receipt", arguments: { arquivo: "Audio/fala.wav", modelo: "omnivoice" } });
  confere(bloqueado.isError === true, "modelo sem licença comercial é bloqueado em projeto comercial");

  const pend = await client.callTool({ name: "check_licenses", arguments: {} });
  confere(Array.isArray(pend.structuredContent?.sem_recibo) && pend.structuredContent.sem_recibo.includes("Audio/fala.wav"),
    "check_licenses acha o asset sem recibo");

  const creditos = await client.callTool({ name: "export_credits", arguments: {} });
  confere(fs.existsSync(path.join(raiz, "ai", "creditos-e-licencas.md")) && creditos.structuredContent?.assets_com_ia === 1,
    "export_credits grava o relatório");

  const musica = await client.callTool({ name: "generate_music", arguments: { situacao: "vila", compassos: 4 } });
  confere(musica.structuredContent?.loop === true && fs.existsSync(path.join(raiz, "Audio", "musica", "vila.wav")), "generate_music grava a trilha em loop");
  const sfx = await client.callTool({ name: "generate_sfx", arguments: { efeitos: ["passo_grama", "golpe"], variacoes: 2 } });
  confere(sfx.structuredContent?.arquivos?.length === 4, "generate_sfx grava os efeitos com variações");
  const codigo = await client.callTool({ name: "generate_code", arguments: {} });
  confere(fs.existsSync(path.join(raiz, "Scripts", "fornalha", "jogador.gd")) && fs.existsSync(path.join(raiz, "project.godot")), "generate_code escreve o jogo para a engine");

  // com o Ignis aberto, quem planeja é o cérebro (no processador pode levar minutos)
  const plano = await client.callTool({ name: "plan_request", arguments: { pedido: "a música de combate e os efeitos sonoros", executar: "noite" } }, undefined, { timeout: 600000 });
  const nomesPlano = (plano.structuredContent?.passos || []).map((p) => p.ferramenta);
  confere(nomesPlano.includes("generate_music") && nomesPlano.includes("generate_sfx") && plano.structuredContent?.tarefas?.length === nomesPlano.length,
    `plan_request planeja (${plano.structuredContent?.origem}) e põe na fila da noite`);
  const fila = await client.callTool({ name: "list_queue", arguments: {} });
  confere(fila.structuredContent?.tarefas?.some((t) => t.quando === "noite" && t.situacao === "esperando"), "list_queue mostra a fila da noite");
  await client.callTool({ name: "update_project", arguments: { alteracoes: { guia_visual: { paleta: ["#7a2e22", "#2f3640"] } } } });
  const estilo = await client.callTool({ name: "check_style", arguments: {} });
  confere(!estilo.isError && typeof estilo.structuredContent?.conferidos === "number", "check_style confere o guia visual");

  const semProjeto = await client.callTool({ name: "open_project", arguments: { caminho: path.join(home, "nao-existe") } });
  confere(semProjeto.isError === true, "erro de ferramenta volta com isError");
}

function portaLivre() {
  return new Promise((ok, erro) => {
    const s = net.createServer();
    s.listen(0, "127.0.0.1", () => {
      const p = s.address().port;
      s.close(() => ok(p));
    });
    s.on("error", erro);
  });
}

async function esperarApi(porta, ms = 20000) {
  const fim = Date.now() + ms;
  while (Date.now() < fim) {
    try {
      const r = await fetch(`http://127.0.0.1:${porta}/fornalha/estado`);
      if (r.ok) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  return false;
}

async function main() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "fornalha-e2e-"));
  const env = { ...process.env, FORNALHA_HOME: home };

  // 1) stdio
  const cmd = process.env.FORNALHA_MCP_CMD || cli;
  const args = process.env.FORNALHA_MCP_CMD ? (process.env.FORNALHA_MCP_ARGS || "").split(" ").filter(Boolean) : ["mcp"];
  console.log(`MCP por stdio: ${cmd} ${args.join(" ")}`);
  const stdio = new Client({ name: "claude-code", version: "teste" });
  await stdio.connect(new StdioClientTransport({ command: cmd, args, env, stderr: "inherit" }));
  confere(stdio.getServerVersion()?.name === "fornalha", "initialize: o servidor se apresenta como fornalha");
  await roteiro(stdio, "claude-code", "claude-code", home);
  await stdio.close();

  // 2) HTTP: numa Fornalha já aberta (FORNALHA_MCP_URL) ou no fornalha-cli servir
  const urlPronta = process.env.FORNALHA_MCP_URL;
  if (urlPronta || cli) {
    let servidor = null;
    let url = urlPronta;
    if (!url) {
      const porta = await portaLivre();
      console.log(`MCP por HTTP: ${cli} servir --porta ${porta}`);
      servidor = spawn(cli, ["servir", "--porta", String(porta)], { env, stdio: ["ignore", "inherit", "inherit"] });
      confere(await esperarApi(porta), "API local respondeu");
      url = `http://127.0.0.1:${porta}/mcp`;
    } else {
      console.log(`MCP por HTTP na Fornalha aberta: ${url}`);
    }
    try {
      const http = new Client({ name: "codex", version: "teste" });
      await http.connect(new StreamableHTTPClientTransport(new URL(url)));
      await roteiro(http, "codex", "codex", home);
      await http.close();
    } finally {
      if (servidor) servidor.kill();
    }
  }

  fs.rmSync(home, { recursive: true, force: true });
  if (falhas) {
    console.log(`\n${falhas} verificação(ões) falharam.`);
    process.exit(1);
  }
  console.log("\nTudo certo: o MCP da Fornalha funciona com o SDK oficial, por stdio e por HTTP.");
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
