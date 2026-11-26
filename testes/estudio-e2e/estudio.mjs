// Uso: node testes/estudio-e2e/estudio.mjs <app/ui> <fornalha-cli> <raiz de um projeto com Characters/templario/templario.glb> <pasta das capturas>
// Precisa do Playwright com o Chromium (require("playwright")). Abre a janela de verdade no Chromium, com a API
// local de verdade por trás, ajusta braço e antebraço no quadro 12 do "atacar", grava como animação nova pelo
// Blender e confere que o estúdio mostrou o mesmo giro que o Blender gravou (diferença < 1°).
// Teste de ponta a ponta do Estúdio 3D: a janela (Chromium) + a API de verdade + o Blender.
// O que o estúdio mostra antes de gravar tem de ser o que o Blender grava (mesmo giro no mesmo quadro).
import { createRequire } from "node:module";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [ui, cli, raizProjeto, saida] = process.argv.slice(2);
const PORTA_API = 11491, PORTA_UI = 8765;
const tipos = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2", ".png": "image/png" };
const estatico = http.createServer((req, res) => {
  const p = path.join(ui, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!p.startsWith(ui) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "content-type": tipos[path.extname(p)] || "application/octet-stream" });
  fs.createReadStream(p).pipe(res);
}).listen(PORTA_UI);
const api = spawn(cli, ["servir", "--porta", String(PORTA_API)], { stdio: ["ignore", "inherit", "inherit"], env: process.env });
for (let i = 0; i < 120; i++) {
  try { const r = await fetch(`http://127.0.0.1:${PORTA_API}/fornalha/ferramentas/get_status`, { method: "POST", headers: { "content-type": "application/json", "x-fornalha-cliente": "pessoa" }, body: "{}" }); if (r.ok) break; } catch {}
  await new Promise((ok) => setTimeout(ok, 500));
}

let falhas = 0;
const confere = (c, t, x) => { console.log(`${c ? "✓" : "✗"} ${t}${x !== undefined ? " " + JSON.stringify(x) : ""}`); if (!c) falhas++; };
const navegador = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await navegador.newPage({ viewport: { width: 1500, height: 1250 }, deviceScaleFactor: 1 });
page.on("console", (m) => { if (m.type() === "error") console.log("console:", m.text()); });
page.on("pageerror", (e) => console.log("erro na página:", e.message));
await page.exposeFunction("__api", async (method, p, body) => {
  const r = await fetch(`http://127.0.0.1:${PORTA_API}${p}`, { method, headers: { "content-type": "application/json", "x-fornalha-cliente": "pessoa" }, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, corpo: await r.json().catch(() => ({})) };
});
await page.exposeFunction("__ler", (c) => {
  const ext = path.extname(c).slice(1).toLowerCase();
  return { mime: { png: "image/png", glb: "model/gltf-binary" }[ext] || "application/octet-stream", base64: fs.readFileSync(c).toString("base64") };
});
await page.addInitScript(() => {
  window.__TAURI__ = { core: { invoke: async (cmd, a) => {
    if (cmd === "api") return window.__api(a.method, a.path, a.body);
    if (cmd === "ler_arquivo") return window.__ler(a.caminho);
    if (cmd === "botoes_janela") return { estilo: "windows", esquerda: [], direita: ["minimize", "maximize", "close"] };
    throw new Error("sem " + cmd);
  } } };
});
await page.goto(`http://127.0.0.1:${PORTA_UI}/index.html`);
await page.waitForFunction(() => typeof abrirProjeto === "function" && window.FornalhaEstudio);
await page.evaluate((r) => abrirProjeto(r), raizProjeto);
await page.waitForFunction(() => raiz && recibos.length > 0, null, { timeout: 60000 });
await page.evaluate(() => irPara("movimento"));
await page.waitForFunction(() => [...document.querySelectorAll("#mov-personagem option")].some((o) => o.value.endsWith("templario.glb")), null, { timeout: 120000 });
await page.selectOption("#mov-personagem", "Characters/templario/templario.glb");
await page.click("#est-abrir");
await page.waitForFunction(() => window.FornalhaEstudio.estado().ossos > 0, null, { timeout: 120000 });
let est = await page.evaluate(() => window.FornalhaEstudio.estado());
confere(est.ossos >= 57 && est.armas === 1, "o estúdio abriu o templário com o esqueleto e a espada", est);
await page.evaluate(() => window.FornalhaEstudio.trocarClipe("atacar"));
await page.waitForTimeout(800);
await page.evaluate(() => { window.FornalhaEstudio.irPara(12); window.FornalhaEstudio.selecionar("upperarm_r"); });
await page.waitForTimeout(400);
await page.locator("#estudio-3d").screenshot({ path: path.join(saida, "estudio_material.png") });

// ajuste: 15° em Y e −10° em Z (mundo) no braço, 10° em X no antebraço, no quadro 12
await page.evaluate(() => {
  const E = window.FornalhaEstudio;
  for (let i = 0; i < 3; i++) E.girar("y", 5);
  for (let i = 0; i < 2; i++) E.girar("z", -5);
  E.selecionar("lowerarm_r");
  E.girar("x", 5); E.girar("x", 5);
});
const quadros = [6, 9, 12, 15, 18];
const previa = {};
for (const q of quadros) previa[q] = await page.evaluate((q) => { const E = window.FornalhaEstudio; E.irPara(q); return { braco: E.giroNoMundo("upperarm_r"), ante: E.giroNoMundo("lowerarm_r"), mao: E.giroNoMundo("hand_r") }; }, q);
est = await page.evaluate(() => window.FornalhaEstudio.estado());
confere(est.edicoes === 7, "sete ajustes registrados", est.edicoes);
await page.evaluate(() => window.FornalhaEstudio.irPara(12));
await page.waitForTimeout(300);
await page.locator("#estudio-3d").screenshot({ path: path.join(saida, "estudio_ajustado.png") });
await page.fill("#est-novo-nome", "atacar_ajustado");
await page.click("#est-salvar-como");
await page.waitForFunction(() => !document.getElementById("est-veredito").hidden, null, { timeout: 600000 });
await page.waitForFunction(() => window.FornalhaEstudio.estado().animacao === "atacar_ajustado", null, { timeout: 60000 });
const veredito = await page.locator("#est-veredito").innerText();
console.log("veredito:", veredito.replace(/\s+/g, " "));
const ang = (a, b) => { const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]); return (2 * Math.acos(Math.min(1, d)) * 180) / Math.PI; };
let pior = 0;
for (const q of quadros) {
  const depois = await page.evaluate((q) => { const E = window.FornalhaEstudio; E.irPara(q); return { braco: E.giroNoMundo("upperarm_r"), ante: E.giroNoMundo("lowerarm_r"), mao: E.giroNoMundo("hand_r") }; }, q);
  for (const k of ["braco", "ante", "mao"]) pior = Math.max(pior, ang(previa[q][k], depois[k]));
  console.log(`  quadro ${q}: braço ${ang(previa[q].braco, depois.braco).toFixed(2)}°, antebraço ${ang(previa[q].ante, depois.ante).toFixed(2)}°, mão ${ang(previa[q].mao, depois.mao).toFixed(2)}°`);
}
confere(pior < 1.0, "o que o estúdio mostrou é o que o Blender gravou (diferença máxima em graus)", +pior.toFixed(3));
// a original continua
const orig = await page.evaluate(() => { const E = window.FornalhaEstudio; E.trocarClipe("atacar"); E.irPara(12); return E.giroNoMundo("upperarm_r"); });
const previaSemAjuste = await page.evaluate(() => window.FornalhaEstudio.estado());
confere(previaSemAjuste.animacao === "atacar", "a animação original continua no personagem");
for (const estilo of ["barro", "anime"]) {
  await page.evaluate((s) => { const E = window.FornalhaEstudio; E.trocarClipe("atacar_ajustado"); E.irPara(12); E.estilo(s); }, estilo);
  await page.waitForTimeout(500);
  await page.locator("#estudio-3d").screenshot({ path: path.join(saida, `estudio_${estilo}.png`) });
}
await navegador.close();
api.kill();
estatico.close();
console.log(falhas ? `${falhas} falha(s)` : "Estúdio 3D: tudo certo");
process.exit(falhas ? 1 : 0);
