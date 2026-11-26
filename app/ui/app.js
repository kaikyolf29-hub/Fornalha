// Janela da Fornalha. Fala com o núcleo pelo Tauri (sem rede); fora do Tauri
// (desenvolvimento no navegador), usa a API local em 127.0.0.1:11480.
"use strict";

const tauri = window.__TAURI__ && window.__TAURI__.core;
const $ = (id) => document.getElementById(id);
let estacao = "projeto";
let info = null, estado = null, biblia = null, raiz = null, recibos = [];

// ---------- comportamento de aplicativo (não de página) ----------
document.addEventListener("contextmenu", (e) => { if (!e.target.closest("input, textarea, pre, code")) e.preventDefault(); });
document.addEventListener("keydown", (e) => {
  const k = e.key.toLowerCase(), ctrl = e.ctrlKey || e.metaKey;
  if (k === "f5" || (ctrl && ["r", "p", "u", "+", "-", "=", "0"].includes(k)) || (ctrl && e.shiftKey && k === "i")) e.preventDefault();
});
document.addEventListener("wheel", (e) => { if (e.ctrlKey) e.preventDefault(); }, { passive: false });
document.addEventListener("dragstart", (e) => { if (!e.target.closest("input, textarea")) e.preventDefault(); });

// ---------- barra de título integrada ----------
document.documentElement.dataset.so = /windows/i.test(navigator.userAgent) ? "windows" : /mac os/i.test(navigator.userAgent) ? "mac" : "linux";
const ICONES_JANELA = {
  windows: { caixa: 10, minimize: '<path d="M0 5.5h10"/>', maximize: '<rect x=".5" y=".5" width="9" height="9" rx="1"/>',
    restaurar: '<path d="M2.5 2.5V1.5a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-1"/><rect x=".5" y="2.5" width="7" height="7" rx="1"/>', close: '<path d="M.5.5l9 9M9.5.5l-9 9"/>' },
  gnome: { caixa: 16, minimize: '<path d="M4.5 11.5h7"/>', maximize: '<rect x="4" y="4" width="8" height="8" rx="1.5"/>',
    restaurar: '<rect x="3.5" y="6" width="6.5" height="6.5" rx="1.2"/><path d="M6 4h5a1 1 0 0 1 1 1v5"/>', close: '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>' },
  kde: { caixa: 16, minimize: '<path d="M4 6.5l4 4 4-4"/>', maximize: '<path d="M4 10l4-4 4 4"/>', restaurar: '<path d="M8 3.5l4.5 4.5L8 12.5 3.5 8z"/>', close: '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>' },
  mac: { caixa: 12, minimize: '<path d="M2.8 6h6.4"/>', maximize: '<path d="M3.4 3.3h3.3L3.4 6.6zM8.6 8.7H5.3l3.3-3.3z" fill="currentColor" stroke="none"/>',
    restaurar: '<path d="M5.7 5.7H2.9l2.8-2.8zM6.3 6.3h2.8L6.3 9.1z" fill="currentColor" stroke="none"/>', close: '<path d="M3.7 3.7l4.6 4.6M8.3 3.7L3.7 8.3"/>' },
};
const NOMES_JANELA = { minimize: "Minimizar", maximize: "Maximizar", close: "Fechar (a Fornalha continua perto do relógio)" };

(function barraDeTitulo() {
  const w = window.__TAURI__ && window.__TAURI__.window && window.__TAURI__.window.getCurrentWindow();
  if (!w) return;
  const raizHtml = document.documentElement;
  const svg = (estilo, d) => { const c = ICONES_JANELA[estilo].caixa; return `<svg viewBox="0 0 ${c} ${c}" aria-hidden="true">${d}</svg>`; };
  const marcar = async () => {
    const max = await w.isMaximized().catch(() => false);
    raizHtml.toggleAttribute("data-maximizada", max);
    for (const b of document.querySelectorAll('[data-janela="maximize"]')) b.title = max ? "Restaurar" : "Maximizar";
  };
  window.montarBotoesJanela = async (preferido) => {
    const b = await tauri.invoke("botoes_janela", { preferido: preferido || "auto" });
    const ic = ICONES_JANELA[b.estilo] || ICONES_JANELA.windows;
    raizHtml.dataset.botoes = b.estilo;
    raizHtml.toggleAttribute("data-botoes-esquerda", b.esquerda.length > 0);
    for (const [lado, lista] of [["esquerda", b.esquerda], ["direita", b.direita]]) {
      const caixa = $("controles-" + lado);
      caixa.innerHTML = lista.map((nome) => {
        const desenho = nome === "maximize" ? `<span class="i-max">${svg(b.estilo, ic.maximize)}</span><span class="i-rest">${svg(b.estilo, ic.restaurar)}</span>` : svg(b.estilo, ic[nome]);
        return `<button data-janela="${nome}" class="jan-${nome}" title="${NOMES_JANELA[nome]}" aria-label="${NOMES_JANELA[nome]}" tabindex="-1">${desenho}</button>`;
      }).join("");
      caixa.hidden = lista.length === 0;
    }
    marcar();
  };
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-janela]");
    if (!b) return;
    if (b.dataset.janela === "minimize") w.minimize();
    else if (b.dataset.janela === "maximize") w.toggleMaximize();
    else if (b.dataset.janela === "close") w.close();
  });
  api("GET", "/janela/info").then((c) => montarBotoesJanela(c.estilo_janela)).catch(() => montarBotoesJanela("auto"));
  marcar();
  w.onResized(marcar);
  const clicavel = "a, button, input, select, textarea, label, summary, audio, [contenteditable], [role=button], [tabindex]:not([tabindex='-1'])";
  const podeArrastar = (alvo) => {
    if (!(alvo instanceof Element) || alvo.closest(clicavel)) return false;
    const area = alvo.closest("[data-arrastar]");
    return !!area && (area === alvo || area.dataset.arrastar === "tudo");
  };
  let inicio = null;
  document.addEventListener("mousedown", (e) => {
    inicio = null;
    if (e.button !== 0 || !podeArrastar(e.target)) return;
    e.preventDefault();
    if (e.detail === 2) w.toggleMaximize(); else inicio = { x: e.screenX, y: e.screenY };
  });
  document.addEventListener("mousemove", (e) => {
    if (!inicio) return;
    if (!(e.buttons & 1)) { inicio = null; return; }
    if (Math.abs(e.screenX - inicio.x) + Math.abs(e.screenY - inicio.y) >= 3) { inicio = null; w.startDragging(); }
  });
  document.addEventListener("mouseup", () => { inicio = null; });
  window.addEventListener("blur", () => raizHtml.toggleAttribute("data-inativa", true));
  window.addEventListener("focus", () => raizHtml.toggleAttribute("data-inativa", false));
})();

// ---------- utilidades ----------
// as pastas do projeto seguem o padrão da engine (em inglês); na janela aparecem em português
const NOME_PASTA = { Characters: "Personagens", Enemies: "Inimigos", World: "Mundo", Audio: "Áudio", Music: "Música", Weapons: "Armas",
  Props: "Objetos", Items: "Itens", Concept: "Conceito", Concepts: "Conceitos", Scripts: "Código", UI: "Interface", Textures: "Texturas",
  Animations: "Animações", Cutscenes: "Cenas", GameDesign: "Design do jogo", VFX: "Efeitos visuais" };
const BASE_DEV = "http://127.0.0.1:" + (new URLSearchParams(location.search).get("porta") || "11480");
async function api(method, path, body) {
  let status, corpo;
  if (tauri) {
    const r = await tauri.invoke("api", { method, path, body: body ?? null });
    status = r.status; corpo = r.corpo;
  } else {
    let r;
    try {
      r = await fetch(BASE_DEV + path, { method, headers: { "content-type": "application/json", "x-fornalha-cliente": "pessoa" }, body: body ? JSON.stringify(body) : undefined });
    } catch (_) {
      // o navegador só diz "Failed to fetch" (em inglês): explica em português o que houve
      const e = new Error("Não consegui falar com a Fornalha neste computador. Ela está aberta? (perto do relógio)");
      e.codigo = "sem_conexao";
      throw e;
    }
    status = r.status; corpo = await r.json().catch(() => ({}));
  }
  if (status >= 400) {
    const e = new Error((corpo && corpo.erro && (corpo.erro.mensagem || corpo.erro)) || ("Erro " + status));
    e.codigo = corpo && corpo.erro && corpo.erro.codigo;
    throw e;
  }
  return corpo;
}
const ferramenta = async (nome, args) => (await api("POST", "/fornalha/ferramentas/" + nome, args || {})).resultado;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const gbDeMb = (v) => (v == null ? "—" : v >= 1024 ? (v / 1024).toFixed(1).replace(".", ",") + " GB" : Math.round(v) + " MB");
const kb = (b) => (b >= 1048576 ? (b / 1048576).toFixed(1).replace(".", ",") + " MB" : Math.round(b / 1024) + " KB");
const numero = (n, casas = 0) => Number(n).toLocaleString("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: casas });
function pinta(el, html) { if (el._html !== html) { el.innerHTML = html; el._html = html; } }
function mensagem(texto, nivel) {
  $("aviso-texto").textContent = texto;
  $("aviso").className = "aviso" + (nivel ? " " + nivel : "");
  $("aviso").hidden = false;
  clearTimeout(mensagem._t);
  if (nivel !== "erro") mensagem._t = setTimeout(() => { $("aviso").hidden = true; }, 7000);
}
$("aviso-fechar").addEventListener("click", () => { $("aviso").hidden = true; });
function calor(ligado) { $("calor").classList.toggle("forjando", ligado); }
async function dataUrl(caminho) {
  if (!tauri || !caminho) return null;
  try { const r = await tauri.invoke("ler_arquivo", { caminho }); return `data:${r.mime};base64,${r.base64}`; } catch { return null; }
}
async function urlDoModelo(caminho) {
  if (!tauri || !caminho) return null;
  try {
    const r = await tauri.invoke("ler_arquivo", { caminho });
    const bin = atob(r.base64), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return URL.createObjectURL(new Blob([bytes], { type: "model/gltf-binary" }));
  } catch { return null; }
}
/** O arquivo inteiro em bytes (para o Estúdio 3D abrir o glb). */
async function lerBytes(caminho) {
  if (!tauri || !caminho) return null;
  const r = await tauri.invoke("ler_arquivo", { caminho });
  const bin = atob(r.base64), bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}
// ponte para o Estúdio 3D (módulo à parte, estudio.js)
window.Fornalha = { ferramenta, mensagem, calor, esc, pinta, dataUrl, lerBytes, raiz: () => raiz };
let urlVisualizador = null;
async function abrirVisualizador(caminho) {
  const url = await urlDoModelo(caminho);
  if (!url) return mensagem("Não deu para abrir o modelo (é grande demais ou está fora do projeto).", "alerta");
  if (urlVisualizador) URL.revokeObjectURL(urlVisualizador);
  urlVisualizador = url;
  const mv = $("vis-modelo");
  $("vis-nome").textContent = nomeArquivo(caminho);
  mv.src = url;
  mv.addEventListener("load", () => {
    const lista = mv.availableAnimations || [];
    pinta($("vis-animacao"), lista.length ? lista.map((n) => `<option ${n === "parado" ? "selected" : ""}>${esc(n)}</option>`).join("") : "<option>sem animação</option>");
    if (lista.includes("parado")) mv.animationName = "parado";
    mv.play();
  }, { once: true });
  $("visualizador").showModal();
}
$("vis-animacao").addEventListener("change", (e) => { const mv = $("vis-modelo"); mv.animationName = e.target.value; mv.play(); });
$("vis-fechar").addEventListener("click", () => $("visualizador").close());
async function abrirArquivo(caminho) {
  if (!tauri) return mensagem(caminho);
  try { await tauri.invoke("abrir_arquivo", { caminho }); } catch (e) { mensagem(String(e), "erro"); }
}
async function abrirPasta(caminho) {
  if (!tauri) return mensagem(caminho);
  try { await tauri.invoke("abrir_pasta", { caminho }); } catch (e) { mensagem(String(e), "erro"); }
}
const escolherPasta = (titulo) => (tauri ? tauri.invoke("escolher_pasta", { titulo }) : null);
const escolherArquivo = (titulo) => (tauri ? tauri.invoke("escolher_arquivo", { titulo }) : null);
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (a) { e.preventDefault(); tauri ? tauri.invoke("abrir_link", { url: a.dataset.link }).catch((x) => mensagem(String(x), "erro")) : window.open(a.dataset.link); }
  const c = e.target.closest("[data-copiar]");
  if (c) navigator.clipboard.writeText(c.dataset.copiar).then(() => mensagem("Copiado."), () => mensagem("Não consegui copiar.", "erro"));
  const v = e.target.closest("[data-abrir]");
  if (v) abrirArquivo(v.dataset.abrir);
  const ir = e.target.closest("[data-ir]");
  if (ir) irPara(ir.dataset.ir);
});
const NOME_NIVEL = { leve: "Leve", equilibrado: "Equilibrado", qualidade: "Qualidade", maximo: "Máximo" };
const nomeArquivo = (p) => String(p || "").split(/[\\/]/).pop();

// ---------- navegação ----------
function irPara(s) {
  estacao = s;
  for (const b of document.querySelectorAll("[data-estacao]")) b.classList.toggle("ativa", b.dataset.estacao === s);
  for (const el of document.querySelectorAll(".estacao")) el.hidden = el.id !== "est-" + s;
  $("principal").scrollTop = 0;
  carregar(s);
}
for (const b of document.querySelectorAll("[data-estacao]")) b.addEventListener("click", () => irPara(b.dataset.estacao));

async function carregarBase() {
  [info, estado] = await Promise.all([api("GET", "/janela/info").catch(() => null), ferramenta("get_status").catch((e) => { mensagem(e.message, "erro"); return null; })]);
  biblia = null; raiz = null; recibos = [];
  if (estado && estado.projeto_atual) {
    const [p, r] = await Promise.all([ferramenta("get_project").catch(() => null), ferramenta("list_receipts").catch(() => ({ recibos: [] }))]);
    if (p) { biblia = p.biblia; raiz = p.raiz; }
    recibos = r.recibos || [];
  }
  pintarColuna();
}

async function carregar(s) {
  try {
    await carregarBase();
    if (s === "projeto") await pintarProjeto();
    else if (s === "forjar") pintarForjar();
    else if (s === "movimento") await pintarMovimento();
    else if (s === "mapa") pintarMapa();
    else if (s === "galeria") await pintarGaleria();
    else if (s === "testar") pintarTestar();
    else if (s === "licencas") await pintarLicencas();
    else if (s === "maquina") await pintarMaquina();
    else if (s === "agentes") await pintarAgentes();
    else if (s === "ajustes") pintarAjustes();
  } catch (e) { mensagem(e.message, "erro"); }
}

// ---------- coluna da bíblia ----------
function pintarColuna() {
  if (!biblia) {
    pinta($("biblia-projeto"), `<p class="biblia-nome">Sem projeto aberto</p><p class="biblia-sub">Crie um jogo novo ou abra um existente na estação Projeto.</p>`);
  } else {
    const c = biblia.conceito || {};
    const pal = (biblia.guia_visual && biblia.guia_visual.paleta) || [];
    const ini = recibos.filter((r) => r.arquivo.startsWith("Enemies/") && r.arquivo.endsWith(".glb")).length;
    const pers = (biblia.personagens || []).length;
    pinta($("biblia-projeto"), `
      <p class="biblia-nome selecionavel">${esc(biblia.nome)}</p>
      <p class="biblia-sub">${esc([c.genero, c.camera].filter(Boolean).join(", ") || "Sem gênero definido")}</p>
      <div class="paleta ${pal.length ? "" : "sem"}" title="${pal.length ? "Paleta do guia visual" : "Sem paleta: defina na estação Projeto"}">${pal.map((h) => `<i style="background:${esc(h)}"></i>`).join("")}</div>
      <dl class="contagens">
        <div><dt>personagens</dt><dd>${pers - ini < 0 ? 0 : pers - ini}</dd></div>
        <div><dt>inimigos</dt><dd>${ini}</dd></div>
        <div><dt>áreas</dt><dd>${((biblia.mundo || {}).areas || []).length}</dd></div>
        <div><dt>recibos</dt><dd>${recibos.length}</dd></div>
      </dl>
      <p style="margin:14px 0 0"><span class="selo ${biblia.comercial ? "venda" : "teste"}">${biblia.comercial ? "Jogo à venda" : "Projeto de teste"}</span> <span class="selo cobre">${biblia.engine === "erethea" ? "Erethea Engine" : "Godot"}</span></p>`);
  }
  const ig = (estado && estado.ignis) || {};
  const rec = (estado && estado.recursos_ignis) || {};
  const prog = (estado && estado.programas) || {};
  const linha = (ok, nome, detalhe) => `<div class="estado"><span class="luz ${ok ? "ok" : ""}"></span><strong>${esc(nome)}</strong><small>${esc(detalhe)}</small></div>`;
  const partesIgnis = [];
  if ((rec.conversa || []).length) partesIgnis.push("cérebro");
  if ((rec.imagem || []).length) partesIgnis.push("imagem");
  if ((rec.voz || []).length) partesIgnis.push("voz");
  const engine = biblia && biblia.engine === "erethea" ? prog.erethea : prog.godot;
  pinta($("ferramentas-estado"), `<h3>Oficina</h3>
    ${linha(ig.conectado, "Ignis", ig.conectado ? (partesIgnis.length ? partesIgnis.join(", ") : "aberto, sem modelos preparados") : "fechado: sem cérebro, imagem e voz")}
    ${linha(prog.blender && prog.blender.achado, "Blender", prog.blender && prog.blender.achado ? prog.blender.versao || "achado" : "não encontrado")}
    ${linha(engine && engine.achado, engine ? engine.nome : "Engine", engine && engine.achado ? engine.versao || "achada" : "não encontrada")}`);
  if (estado) pinta($("rodape"), `<strong>Pronta para agentes</strong><span class="mono">${esc(estado.endereco_mcp.replace("http://", ""))}</span>`);
}

// ---------- Projeto ----------
async function pintarProjeto() {
  const lista = await ferramenta("list_projects");
  if (!$("novo-pasta").value) $("novo-pasta").value = lista.pasta_projetos || "";
  const rec = lista.recentes || [];
  pinta($("recentes"), rec.length ? rec.map((p) => `<div class="item"><div><strong>${esc(p.nome || "Projeto não encontrado")}</strong><small class="mono">${esc(p.raiz)}</small></div>
    <div class="lado">${p.existe ? `<button class="botao" data-abrir-projeto="${esc(p.raiz)}">Abrir</button>` : ""}</div></div>`).join("") : `<p class="vazio">Nenhum projeto ainda.</p>`);
  if (!biblia) { pinta($("editor-biblia"), `<p class="vazio">Abra ou crie um projeto para editar a bíblia.</p>`); return; }
  const c = biblia.conceito || {}, g = biblia.guia_visual || {};
  const areas = (biblia.mundo || {}).areas || [];
  const tiposArea = ["vila", "floresta", "montanha", "masmorra", "arena", "caverna", "castelo", "ruinas", "pantano", "vulcao"];
  $("editor-biblia")._html = null;
  $("editor-biblia").innerHTML = `<form id="form-biblia" class="formulario">
    <div class="lado-a-lado">
      <label class="campo"><span>Gênero</span><input type="text" name="genero" value="${esc(c.genero)}"></label>
      <label class="campo"><span>Câmera</span><input type="text" name="camera" value="${esc(c.camera)}"></label>
      <label class="campo"><span>Estilo</span><input type="text" name="estilo" value="${esc(c.estilo)}" placeholder="estilizado, realista"></label>
    </div>
    <label class="campo"><span>Guia visual (vai junto em toda imagem)</span><textarea name="texto_de_estilo" placeholder="low poly, cores quentes, contornos marcados">${esc(g.texto_de_estilo)}</textarea></label>
    <div class="campo"><span>Paleta</span><div class="paleta-editor" id="paleta-editor">${(g.paleta || []).map((h) => `<input type="color" value="${esc(h)}">`).join("")}<button type="button" class="botao leve" id="paleta-mais">Adicionar cor</button></div></div>
    <label class="campo"><span>Evitar (separe por vírgula)</span><input type="text" name="evitar" value="${esc((g.evitar || []).join(", "))}"></label>
    <div class="campo"><span>Áreas do mundo</span><div id="areas" class="lista">${areas.map((a, i) => areaLinha(a, i, tiposArea)).join("")}</div><button type="button" class="botao leve" id="area-mais">Adicionar área</button></div>
    <div class="lado-a-lado">
      <label class="campo"><span>Engine</span><select name="engine"><option value="godot" ${biblia.engine !== "erethea" ? "selected" : ""}>Godot</option><option value="erethea" ${biblia.engine === "erethea" ? "selected" : ""}>Erethea Engine</option></select></label>
      <label class="chave" style="align-self:end"><input type="checkbox" name="comercial" ${biblia.comercial ? "checked" : ""}><span>Jogo à venda</span></label>
    </div>
    <div class="acoes"><button type="submit" class="botao quente">Salvar a bíblia</button><button type="button" class="botao" id="abrir-pasta-atual">Abrir a pasta</button></div>
  </form>`;
  $("paleta-mais").onclick = () => { const i = document.createElement("input"); i.type = "color"; i.value = "#888888"; $("paleta-mais").before(i); };
  $("area-mais").onclick = () => { const d = document.createElement("div"); d.innerHTML = areaLinha({ id: "", nome: "", tipo: "floresta" }, Date.now(), tiposArea); $("areas").append(d.firstElementChild); };
  $("abrir-pasta-atual").onclick = () => abrirPasta(raiz);
  $("form-biblia").onsubmit = salvarBiblia;
}
function areaLinha(a, i, tipos) {
  return `<div class="item area"><div class="lado-a-lado" style="flex:1"><input type="text" class="area-nome" value="${esc(a.nome || a.id)}" placeholder="Nome da área">
    <select class="area-tipo">${tipos.map((t) => `<option ${t === a.tipo ? "selected" : ""}>${t}</option>`).join("")}</select></div>
    <button type="button" class="botao leve" onclick="this.closest('.area').remove()">Tirar</button></div>`;
}
async function salvarBiblia(e) {
  e.preventDefault();
  const f = e.target;
  const slug = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "area";
  const areas = [...document.querySelectorAll("#areas .area")].map((d) => {
    const nome = d.querySelector(".area-nome").value.trim();
    return { id: slug(nome), nome, tipo: d.querySelector(".area-tipo").value };
  }).filter((a) => a.nome);
  const alteracoes = {
    comercial: f.comercial.checked, engine: f.engine.value,
    conceito: { genero: f.genero.value.trim(), camera: f.camera.value.trim(), estilo: f.estilo.value.trim() },
    guia_visual: { texto_de_estilo: f.texto_de_estilo.value.trim(), paleta: [...document.querySelectorAll("#paleta-editor input[type=color]")].map((i) => i.value), evitar: f.evitar.value.split(",").map((s) => s.trim()).filter(Boolean) },
    mundo: { areas },
  };
  try { await ferramenta("update_project", { alteracoes }); mensagem("Bíblia salva."); carregar("projeto"); }
  catch (err) { mensagem(err.message, "erro"); }
}
$("form-novo").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("criar").disabled = true;
  try {
    const r = await ferramenta("create_project", { nome: $("novo-nome").value.trim(), comercial: $("novo-comercial").checked, pasta_pai: $("novo-pasta").value.trim() || undefined,
      genero: $("novo-genero").value.trim() || undefined, camera: $("novo-camera").value.trim() || undefined });
    mensagem(`Projeto "${r.biblia.nome}" criado.`);
    $("novo-nome").value = "";
    carregar("projeto");
  } catch (err) { mensagem(err.message, "erro"); } finally { $("criar").disabled = false; }
});
$("escolher-pasta").addEventListener("click", async () => { const p = await escolherPasta("Onde criar o projeto"); if (p) $("novo-pasta").value = p; });
$("abrir-projeto").addEventListener("click", async () => { const p = await escolherPasta("Pasta do projeto (com o game.project.json)"); if (p) abrirProjeto(p); });
document.addEventListener("click", (e) => { const b = e.target.closest("[data-abrir-projeto]"); if (b) abrirProjeto(b.dataset.abrirProjeto); });
async function abrirProjeto(caminho) {
  try { const r = await ferramenta("open_project", { caminho }); mensagem(`Projeto "${r.biblia.nome}" aberto.`); carregar(estacao); }
  catch (err) { mensagem(err.message, "erro"); }
}

// ---------- Forjar ----------
const I = {
  personagem: '<circle cx="12" cy="6" r="3"/><path d="M6 21v-5a6 6 0 0 1 12 0v5M9 12l-3 4M15 12l3 4"/>',
  inimigo: '<path d="M7 4l2 3h6l2-3M5 9a7 7 0 0 0 14 0"/><path d="M9 11h.01M15 11h.01M9 16c2 1.5 4 1.5 6 0"/><path d="M8 20h8"/>',
  arma: '<path d="M14 4l6 0 0 6-9 9-3-3z"/><path d="M8 16l-4 4M6 13l5 5"/>',
  objeto: '<path d="M4 8l8-4 8 4-8 4z"/><path d="M4 8v8l8 4 8-4V8M12 12v8"/>',
  mundo: '<path d="M3 18l5-8 4 5 3-4 6 7z"/><circle cx="17" cy="6" r="2"/>',
  efeitos: '<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12"/>',
  musica: '<path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
  fala: '<path d="M4 5h16v10H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
  conceito: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 17l-5-5-9 8"/>',
};
const ARMAS = ["espada", "machado", "lanca", "martelo", "adaga", "cajado", "escudo"];
const OBJETOS = ["barril", "caixa", "bau", "arvore", "pedra", "casa", "tocha", "cerca", "pocao"];
const TIPOS = ["", "humano", "elfo", "anao", "orc", "goblin", "esqueleto", "zumbi", "demonio", "dragao"];
const sel = (nome, opcoes, rotulo, padrao) => `<label class="campo"><span>${rotulo}</span><select name="${nome}">${opcoes.map((o) => `<option value="${o}" ${o === padrao ? "selected" : ""}>${o || "o cérebro escolhe"}</option>`).join("")}</select></label>`;
const txt = (nome, rotulo, ph = "") => `<label class="campo"><span>${rotulo}</span><input type="text" name="${nome}" placeholder="${esc(ph)}"></label>`;
const MOLDES = {
  personagem: { titulo: "Personagem", desc: "Ficha, conceito, 3D com esqueleto, 9 animações e fala", ferramenta: "create_character",
    campos: () => txt("nome", "Nome", "Aren") + txt("descricao", "Como ele é", "ferreiro que luta com machado") + `<div class="lado-a-lado">${sel("tipo", TIPOS, "Tipo", "")}${sel("arma", ["", ...ARMAS, "nenhuma"], "Arma", "")}${sel("armadura", ["", "nenhuma", "leve", "pesada"], "Armadura", "")}</div>` + txt("fala", "Fala para dublar", "Ninguém passa por esta ponte.") + `<label class="chave"><input type="checkbox" name="video"><span>Vídeo das animações</span></label><label class="chave"><input type="checkbox" name="por_partes" checked><span>Ver o conceito antes do 3D (aceitar ou refazer)</span></label>`,
    args: (f) => ({ papel: "protagonista", nome: f.nome.value || undefined, descricao: f.descricao.value || undefined, tipo: f.tipo.value || undefined, arma: f.arma.value || undefined, armadura: f.armadura.value || undefined, fala: f.fala.value || undefined, video: f.video.checked, parar_no_conceito: f.por_partes.checked || undefined }) },
  inimigo: { titulo: "Inimigo", desc: "Igual ao personagem, com IA na engine; pode já testar no jogo", ferramenta: "create_character",
    campos: () => txt("descricao", "Como ele é", "orc grandalhão com martelo") + `<div class="lado-a-lado">${sel("tipo", TIPOS, "Tipo", "")}${sel("arma", ["", ...ARMAS], "Arma", "")}</div>` + txt("fala", "Grito de guerra", "") + `<label class="chave"><input type="checkbox" name="testar" checked><span>Montar na engine e testar no fim</span></label>`,
    args: (f) => ({ papel: "inimigo", descricao: f.descricao.value || undefined, tipo: f.tipo.value || undefined, arma: f.arma.value || undefined, fala: f.fala.value || undefined, testar_na_engine: f.testar.checked }) },
  arma: { titulo: "Arma", desc: "Low-poly no estilo do jogo, com colisão", ferramenta: "generate_3d",
    campos: () => sel("modelo", ARMAS, "Arma", "espada") + txt("nome", "Nome", ""), args: (f) => ({ tipo: "arma", modelo: f.modelo.value, nome: f.nome.value || undefined }) },
  objeto: { titulo: "Objeto", desc: "Barril, baú, árvore, casa e outros", ferramenta: "generate_3d",
    campos: () => sel("modelo", OBJETOS, "Objeto", "barril") + txt("nome", "Nome", ""), args: (f) => ({ tipo: "objeto", modelo: f.modelo.value, nome: f.nome.value || undefined }) },
  mundo: { titulo: "Mundo", desc: "As áreas da bíblia viram um mapa em blocos jogável", ferramenta: "generate_blockout",
    campos: () => `<p class="nota">Usa as áreas da bíblia (estação Projeto). Sem áreas, faz vila e floresta.</p><label class="campo"><span>Semente</span><input type="number" name="seed" value="7" min="0"></label>`, args: (f) => ({ seed: Number(f.seed.value) }) },
  efeitos: { titulo: "Efeitos", desc: "Passos por chão, golpes, impacto, pulo, dano", ferramenta: "generate_sfx",
    campos: () => `<p class="nota">Gera o pacote que o jogo usa, com variações de cada som.</p>`, args: () => ({}) },
  musica: { titulo: "Música", desc: "Trilha em loop por área e situação", ferramenta: "generate_music",
    campos: () => sel("situacao", ["exploracao", "vila", "floresta", "combate", "chefe", "masmorra"], "Situação", "exploracao") + `<label class="campo"><span>Compassos</span><input type="number" name="compassos" value="16" min="2" max="64"></label>`, args: (f) => ({ situacao: f.situacao.value, compassos: Number(f.compassos.value) }) },
  fala: { titulo: "Fala", desc: "Dublagem em português com a curva da boca", ferramenta: "generate_voice",
    campos: () => txt("texto", "Texto", "Bem-vindo à Vila de Brasa.") + txt("personagem", "De quem é", "aren"), args: (f) => ({ texto: f.texto.value, personagem: f.personagem.value || undefined }) },
  conceito: { titulo: "Conceito", desc: "Imagem com o guia visual do jogo", ferramenta: "generate_concept",
    campos: () => txt("descricao", "O que desenhar", "vila medieval ao entardecer"), args: (f) => ({ descricao: f.descricao.value }) },
};
let moldeAtual = null;
const SITUACAO_FILA = { esperando: ["", "Esperando"], rodando: ["cobre", "Rodando"], feita: ["venda", "Feita"], falhou: ["erro", "Falhou"], cancelada: ["", "Cancelada"] };
let vigiaFila = null;
async function pintarFila() {
  let f;
  try { f = await ferramenta("list_queue"); } catch { return; }
  const n = f.noite;
  pinta($("noite-info"), `Tarefas "para a noite" rodam das ${n.inicio_hora}h às ${n.fim_hora}h${n.agora_e_noite ? " (agora é noite: elas já estão rodando)" : ""}. Uma por vez.`);
  const lista = (f.tarefas || []).slice().reverse();
  pinta($("fila"), lista.length ? lista.map((t) => {
    const [cor, nome] = SITUACAO_FILA[t.situacao] || ["", t.situacao];
    const quando = t.quando === "noite" ? "à noite" : "agora";
    const detalhe = t.erro ? esc(t.erro) : t.situacao === "feita" && t.resultado && t.resultado.ficha ? esc(t.resultado.ficha.nome) : esc(t.descricao || "");
    return `<div class="item"><div><strong>${esc(t.ferramenta)}</strong><small>${detalhe}${detalhe ? " · " : ""}${quando}, pedido por ${esc(t.quem)}</small></div>
      <div class="lado"><span class="selo ${cor}">${nome}</span>${t.situacao === "esperando" ? `<button class="botao" data-cancelar="${esc(t.id)}">Cancelar</button>` : ""}</div></div>`;
  }).join("") : `<p class="vazio">Nada na fila.</p>`);
  clearTimeout(vigiaFila);
  if (lista.some((t) => t.situacao === "rodando" || (t.situacao === "esperando" && (t.quando === "agora" || n.agora_e_noite))))
    vigiaFila = setTimeout(() => { if (!$("est-forjar").hidden) pintarFila(); }, 4000);
}
$("fila").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-cancelar]");
  if (!b) return;
  try { await ferramenta("cancel_job", { id: b.dataset.cancelar }); pintarFila(); } catch (err) { mensagem(err.message, "erro"); }
});
$("limpar-fila").addEventListener("click", async () => { try { await ferramenta("cancel_job", { limpar: true }); pintarFila(); } catch (err) { mensagem(err.message, "erro"); } });
$("form-pedido").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!biblia) return mensagem("Abra ou crie um projeto antes do pedido.", "alerta");
  const executar = (e.submitter && e.submitter.dataset.executar) || "agora";
  const pedido = e.target.pedido.value.trim();
  if (!pedido) return mensagem("Escreva o pedido.", "alerta");
  pinta($("plano"), `<p class="nota">Planejando…</p>`);
  try {
    const r = await ferramenta("plan_request", { pedido, executar });
    const origem = r.origem === "cerebro" ? "Plano do cérebro (Ignis)" : "Plano pelas regras da Fornalha";
    pinta($("plano"), `<p class="nota">${origem}${r.quando === "so_o_plano" ? "" : r.quando === "noite" ? ", na fila para a noite" : ", na fila"}:</p>
      <ol class="passos">${r.passos.map((p) => `<li><strong>${esc(p.ferramenta)}</strong> <small>${esc(p.motivo || "")}</small></li>`).join("")}</ol>
      ${(r.avisos || []).map((a) => `<p class="nota">${esc(a)}</p>`).join("")}`);
    pintarFila();
  } catch (err) { pinta($("plano"), ""); mensagem(err.message, "erro"); }
});

function pintarForjar() {
  pintarFila();
  pinta($("moldes"), Object.entries(MOLDES).map(([id, m]) => `<button class="molde ${id === moldeAtual ? "escolhido" : ""}" data-molde="${id}"><svg viewBox="0 0 24 24" aria-hidden="true">${I[id]}</svg><strong>${m.titulo}</strong><small>${m.desc}</small></button>`).join(""));
}
$("moldes").addEventListener("click", (e) => {
  const b = e.target.closest("[data-molde]");
  if (!b) return;
  if (!biblia) return mensagem("Abra ou crie um projeto antes de forjar.", "alerta");
  moldeAtual = b.dataset.molde;
  const m = MOLDES[moldeAtual];
  $("painel-molde").hidden = false;
  $("form-molde").innerHTML = `<h2>${m.titulo}</h2>${m.campos()}<div class="acoes"><button type="submit" class="botao quente">Forjar</button></div>`;
  pintarForjar();
});
$("form-molde").addEventListener("submit", async (e) => {
  e.preventDefault();
  const m = MOLDES[moldeAtual];
  const botao = e.target.querySelector("button[type=submit]");
  botao.disabled = true; botao.textContent = "Forjando…"; calor(true);
  const inicio = Date.now();
  try {
    const args = m.args(e.target);
    const r = await ferramenta(m.ferramenta, args);
    if (r.situacao === "conceito_pronto") {
      await mostrarConceito(m, args, r);
      mensagem("Conceito pronto: aceite para fazer o 3D, ou refaça.");
    } else {
      await mostrarSaida(m, r, (Date.now() - inicio) / 1000);
      mensagem(`${m.titulo} forjado.`);
      carregarBase();
    }
  } catch (err) { mensagem(err.message, "erro"); }
  finally { botao.disabled = false; botao.textContent = "Forjar"; calor(false); }
});
// por partes: o conceito de corpo inteiro aparece antes do 3D, para aceitar (faz o 3D dele) ou refazer
async function mostrarConceito(m, args, r) {
  const url = r.arquivos && r.arquivos.conceito_3d ? await dataUrl(r.arquivos.conceito_3d) : null;
  const div = document.createElement("div");
  div.className = "peca";
  const base = { ...args, nome: (r.ficha && r.ficha.nome) || args.nome, parar_no_conceito: undefined, refazer_conceito: undefined };
  div.innerHTML = `<div class="miniatura">${url ? `<img src="${url}" alt="">` : m.titulo}</div>
    <div><strong>${esc((r.ficha && r.ficha.nome) || "Conceito")}</strong><small>Conceito de corpo inteiro: é ele que vira o 3D.</small>${(r.avisos || []).map((a) => `<small class="avisos">${esc(a)}</small>`).join("")}</div>
    <div class="lado"><button class="botao" data-refazer>Refazer</button><button class="botao quente" data-aceitar>Aceitar e fazer o 3D</button></div>`;
  div.querySelector("[data-aceitar]").addEventListener("click", () => forjarCom(m, base, div));
  div.querySelector("[data-refazer]").addEventListener("click", () =>
    forjarCom(m, { ...base, parar_no_conceito: true, refazer_conceito: true, seed: Math.floor(Math.random() * 1e6) }, div));
  const saida = $("saida");
  if (saida.querySelector(".vazio")) saida.innerHTML = "";
  saida.prepend(div);
}
async function forjarCom(m, args, cartao) {
  cartao.querySelectorAll("button").forEach((b) => (b.disabled = true));
  calor(true);
  const inicio = Date.now();
  try {
    const r = await ferramenta(m.ferramenta, args);
    cartao.remove();
    if (r.situacao === "conceito_pronto") await mostrarConceito(m, args, r);
    else { await mostrarSaida(m, r, (Date.now() - inicio) / 1000); mensagem(`${m.titulo} forjado.`); carregarBase(); }
  } catch (err) { mensagem(err.message, "erro"); cartao.querySelectorAll("button").forEach((b) => (b.disabled = false)); }
  finally { calor(false); }
}
async function mostrarSaida(m, r, segundos) {
  const arquivos = r.arquivos || (r.arquivo ? { arquivo: r.arquivo } : {});
  const lista = Array.isArray(arquivos) ? arquivos : Object.values(arquivos);
  const imagem = arquivos.previa || arquivos.folha || arquivos.conceito || arquivos.mapa || (typeof r.arquivo === "string" && r.arquivo.endsWith(".png") ? r.arquivo : null);
  const url = imagem ? await dataUrl(imagem) : null;
  const titulo = (r.ficha && r.ficha.nome) || r.situacao || nomeArquivo(lista[0]);
  const det = [];
  if (r.estatisticas && r.estatisticas.triangulos) det.push(`${numero(r.estatisticas.triangulos)} triângulos`);
  if (r.estatisticas && r.estatisticas.animacoes && r.estatisticas.animacoes.length) det.push(`${r.estatisticas.animacoes.length} animações`);
  if (r.bpm) det.push(`${r.bpm} bpm, ${numero(r.segundos, 1)} s em loop`);
  if (Array.isArray(r.arquivos)) det.push(`${r.arquivos.length} arquivos`);
  det.push(`${numero(segundos, 1)} s`);
  const teste = r.teste ? `<small>${r.teste.passou ? "Teste na engine: passou" : "Teste na engine: falhou"} · inimigo ${r.teste.inimigos.perseguiram ? "reagiu" : "não reagiu"}</small>` : "";
  const avisos = (r.avisos || []).map((a) => `<small class="avisos">${esc(a)}</small>`).join("");
  const audio = lista.find((x) => String(x).endsWith(".wav"));
  const div = document.createElement("div");
  div.className = "peca";
  div.innerHTML = `<div class="miniatura">${url ? `<img src="${url}" alt="">` : m.titulo}</div>
    <div><strong>${esc(titulo)}</strong><small>${esc(m.titulo)} · ${esc(det.join(" · "))}</small>${teste}${avisos}</div>
    <div class="lado">${audio ? `<button class="botao" data-tocar="${esc(audio)}">Ouvir</button>` : ""}${arquivos.video ? `<button class="botao" data-abrir="${esc(arquivos.video)}">Vídeo</button>` : ""}</div>`;
  const saida = $("saida");
  if (saida.querySelector(".vazio")) saida.innerHTML = "";
  saida.prepend(div);
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-tocar]");
  if (!b) return;
  const url = await dataUrl(b.dataset.tocar);
  if (url) { const a = new Audio(url); a.play(); }
});

// ---------- Galeria ----------
let filtroGaleria = "";
async function pintarGaleria() {
  if (!biblia) { pinta($("galeria"), `<p class="vazio">Abra um projeto para ver os assets.</p>`); pinta($("filtros-galeria"), ""); return; }
  const atuais = new Map();
  for (const r of recibos) atuais.set(r.arquivo, r);
  const todos = [...atuais.values()].filter((r) => !/\.(previa|folha|mapa)\.png$/.test(r.arquivo));
  const pastas = [...new Set(todos.map((r) => r.arquivo.split("/")[0]))].sort();
  pinta($("filtros-galeria"), [["", "Tudo"], ...pastas.map((p) => [p, NOME_PASTA[p] || p])].map(([v, n]) => `<button data-filtro="${esc(v)}" class="${v === filtroGaleria ? "ativo" : ""}">${esc(n)}</button>`).join(""));
  const lista = todos.filter((r) => !filtroGaleria || r.arquivo.startsWith(filtroGaleria + "/"));
  if (!lista.length) { pinta($("galeria"), `<p class="vazio">Nada forjado ainda. Vá até Forjar.</p>`); return; }
  $("galeria")._html = null;
  $("galeria").innerHTML = lista.map((r, i) => {
    const venda = r.modelo.uso_comercial === "sim";
    const ver3d = r.arquivo.endsWith(".glb") ? `<button class="botao ver-3d" data-ver3d="${esc(raiz + "/" + r.arquivo)}">Ver em 3D</button>` : "";
    return `<div class="cartao-asset"><div class="vitrine" id="vit-${i}">${ver3d}${r.arquivo.endsWith(".wav") ? `<button class="botao" data-tocar="${esc(raiz + "/" + r.arquivo)}">Ouvir</button>` : "carregando"}</div>
      <div class="info"><strong>${esc(nomeArquivo(r.arquivo))}</strong><small>${esc(r.modelo.nome)}</small>
      <span><span class="selo ${venda ? "venda" : "teste"}">${venda ? "Pode vender" : esc(r.modelo.licenca)}</span>${foraDoGuia.has(r.arquivo) ? ` <span class="selo teste">Fora do guia</span>` : ""}</span></div></div>`;
  }).join("");
  lista.forEach(async (r, i) => {
    const el = $("vit-" + i);
    if (!el || r.arquivo.endsWith(".wav")) return;
    let alvo = null;
    if (r.arquivo.endsWith(".png")) alvo = r.arquivo;
    else if (r.arquivo.endsWith(".glb")) alvo = r.arquivo.replace(/\.glb$/, ".previa.png");
    else if (/\.(mp4|avi)$/.test(r.arquivo)) { el.innerHTML = `<button class="botao" data-abrir="${esc(raiz + "/" + r.arquivo)}">Abrir vídeo</button>`; return; }
    const url = alvo ? await dataUrl(raiz + "/" + alvo) : null;
    el.innerHTML = url ? `<img src="${url}" alt="">` : "sem prévia";
  });
}
let foraDoGuia = new Set();
$("conferir-estilo").addEventListener("click", async () => {
  if (!biblia) return mensagem("Abra um projeto antes.", "alerta");
  try {
    const r = await ferramenta("check_style", {});
    foraDoGuia = new Set(r.fora_do_guia || []);
    pinta($("resultado-estilo"), `<section class="painel"><p style="margin:0">${r.aprovados} de ${r.conferidos} dentro da paleta ${r.paleta.map((c) => `<span class="amostra" style="background:${esc(c)}"></span>`).join("")}</p>
      ${r.fora_do_guia.length ? `<p class="nota">Fora do guia: ${r.fora_do_guia.map(esc).join(", ")}.</p>` : ""}<p class="nota">${esc(r.nota)}</p></section>`);
    pintarGaleria();
  } catch (err) { mensagem(err.message, err.codigo === "sem_paleta" ? "alerta" : "erro"); }
});
$("galeria").addEventListener("click", (e) => { const b = e.target.closest("[data-ver3d]"); if (b) abrirVisualizador(b.dataset.ver3d); });
$("filtros-galeria").addEventListener("click", (e) => { const b = e.target.closest("[data-filtro]"); if (b) { filtroGaleria = b.dataset.filtro; pintarGaleria(); } });

// ---------- Movimento ----------
const ETIQUETAS_MOV = ["andar", "correr", "ataque", "espada", "soco", "chute", "defesa", "esquiva", "dano", "morte", "zumbi", "agachado", "de_costas", "de_lado", "pular", "gesto"];
let etiquetaMov = "";
let buscaMov = "";
function personagensDoProjeto() {
  const vistos = new Set();
  return recibos.map((r) => r.arquivo).filter((a) => /^(Characters|Enemies)\/.+\.glb$/.test(a) && !vistos.has(a) && vistos.add(a));
}
// ===== Mapa =====
let ultimoMapa = null;
function pintarMapa() {
  if (ultimoMapa) mostrarMapa(ultimoMapa);
}
async function mostrarMapa(r) {
  const imgs = await Promise.all(["mapa", "vista_alta", "vista_chegada"].map((k) => dataUrl((r.arquivos || {})[k])));
  const med = r.medidas || { itens: [] };
  const linhas = med.itens.map((i) => `<div class="item"><div><strong>${esc(i.nome.replaceAll("_", " "))}</strong><small>${esc(i.explica)}</small></div>
    <div class="lado"><span class="selo ${i.ok ? "venda" : "erro"}">${esc(typeof i.valor === "object" ? JSON.stringify(i.valor) : String(i.valor))}${i.ok ? "" : " · reprovado"}</span></div></div>`).join("");
  const st = r.estatisticas || {};
  $("mapa-resultado").innerHTML = `<p class="nota">${med.aprovado ? "Aprovado pelas medidas (a régua não achou o que mede; olhe as imagens)." : "Reprovado: veja os itens em vermelho."}
    ${numero(st.arvores || 0, 0)} árvores · ${numero(st.arbustos || 0, 0)} arbustos · ${numero(st.pedras || 0, 0)} pedras · ${st.pontes || 0} ponte(s)</p>
    <div class="capturas">${imgs.filter(Boolean).map((u) => `<img src="${u}" alt="Mapa">`).join("")}</div>
    ${(r.avisos || []).length ? `<p class="nota">${r.avisos.map(esc).join("<br>")}</p>` : ""}
    <div class="lista">${linhas}</div><p class="nota">${esc(r.proximo || "")}</p>`;
}
async function gerarMapa(botao, novaSemente) {
  if (!biblia) return mensagem("Abra um projeto antes.", "alerta");
  const mudar = {};
  if ($("mapa-tamanho").value) mudar.tamanho_m = Number($("mapa-tamanho").value);
  if ($("mapa-relevo").value) mudar.relevo = { estilo: $("mapa-relevo").value };
  if ($("mapa-clima").value) mudar.clima = $("mapa-clima").value;
  if ($("mapa-hora").value) mudar.hora = $("mapa-hora").value;
  const args = { mudar };
  if (novaSemente) args.seed = Math.floor(Math.random() * 100000);
  const texto = botao.textContent;
  botao.disabled = true; botao.textContent = "Gerando…"; calor(true);
  try { ultimoMapa = await ferramenta("generate_map", args); await mostrarMapa(ultimoMapa); }
  catch (err) { mensagem(err.message, "erro"); }
  finally { botao.disabled = false; botao.textContent = texto; calor(false); }
}
$("mapa-gerar").addEventListener("click", () => gerarMapa($("mapa-gerar"), false));
$("mapa-semente").addEventListener("click", () => gerarMapa($("mapa-semente"), true));

async function pintarMovimento() {
  const sel = $("mov-personagem");
  const lista = biblia ? personagensDoProjeto() : [];
  const atual = sel.value;
  pinta(sel, lista.length ? lista.map((a) => `<option value="${esc(a)}" ${a === atual ? "selected" : ""}>${esc(a)}</option>`).join("") : `<option value="">Nenhum personagem com esqueleto</option>`);
  pinta($("mov-etiquetas"), [["", "Tudo"], ...ETIQUETAS_MOV.map((e) => [e, e.replace("_", " ")])].map(([v, n]) => `<button data-etiqueta="${esc(v)}" class="${v === etiquetaMov ? "ativo" : ""}">${esc(n)}</button>`).join(""));
  if (biblia) await pintarBanco();
}
async function pintarBanco() {
  pinta($("mov-banco"), `<p class="vazio">Lendo o banco (a primeira vez cataloga as capturas no Blender)…</p>`);
  try {
    const r = await ferramenta("list_motions", { busca: buscaMov || undefined, etiquetas: etiquetaMov ? [etiquetaMov] : [], limite: 40 });
    pinta($("mov-fontes"), r.fontes.map((f) => `<strong>${esc(f.nome)}</strong> · ${esc(f.licenca)} · ${f.clipes} clipes${f.credito ? ` · crédito: ${esc(f.credito)}` : ""}`).join("<br>")
      + ((r.pacotes_que_faltam || []).length ? `<br>Para ter mais: Máquina → Pacotes (${r.pacotes_que_faltam.map(esc).join(", ")}).` : ""));
    if (!r.clipes.length) { pinta($("mov-banco"), `<p class="vazio">Nada no banco com esse filtro.</p>`); return; }
    $("mov-banco")._html = null;
    $("mov-banco").innerHTML = r.clipes.map((c) => `<div class="item"><div><strong>${esc(c.nome)}</strong>
        <small>${esc(c.fonte)} · ${numero(c.segundos || 0, 1)} s${c.laco ? " · laço" : ""} · ${esc((c.etiquetas || []).join(", "))}</small></div>
      <div class="lado"><input type="text" value="${esc((c.etiquetas || [])[0] || "")}" data-como="${esc(c.id)}" style="width:130px" title="Nome da animação no jogo">
        <button class="botao" data-aplicar="${esc(c.id)}" data-ciclo="${(c.etiquetas || []).some((e) => e === "andar" || e === "correr") && !c.laco ? "1" : ""}">Pôr no personagem</button></div></div>`).join("")
      + `<p class="nota">${esc(r.total)} clipes no total. ${esc(r.dica)}</p>`;
  } catch (e) { pinta($("mov-banco"), `<p class="vazio">${esc(e.message)}</p>`); }
}
async function mostrarConferencia(r, titulo) {
  if (window.FornalhaEstudio) window.FornalhaEstudio.marcar(r);
  const anims = r.animacoes || [];
  const ok = anims.filter((a) => a.aprovado).length;
  const img = r.arquivos && r.arquivos.imagem ? await dataUrl(r.arquivos.imagem) : null;
  const linhas = anims.map((a) => `<div class="item"><div><strong>${esc(a.nome)}</strong>
      <small>${a.problemas.length ? a.problemas.slice(0, 3).map((p) => esc(p.explicacao)).join("<br>") : "Nada que a régua mede passou do limite."}</small></div>
    <div class="lado"><span class="selo ${a.aprovado ? "venda" : "erro"}">${a.aprovado ? "Aprovada pela régua" : "Reprovada"}</span></div></div>`).join("");
  const corrigidas = r.correcoes ? Object.keys(r.correcoes) : [];
  $("mov-resultado").innerHTML = `
    <div class="veredito ${r.aprovado ? "passou" : "falhou"}"><strong>${esc(titulo)}: ${ok} de ${anims.length} sem defeito medido</strong>
      <span>${corrigidas.length ? "Corrigidas sozinhas: " + corrigidas.map(esc).join(", ") : ""}</span>
      ${r.arquivos && r.arquivos.video ? `<button class="botao" data-abrir="${esc(r.arquivos.video)}" style="margin-left:auto">Abrir vídeo</button>` : ""}</div>
    ${(r.creditos_obrigatorios || []).length ? `<p class="nota">Créditos obrigatórios: ${r.creditos_obrigatorios.map(esc).join("; ")}</p>` : ""}
    ${img ? `<div class="capturas"><img src="${img}" alt="Conferência: o pior quadro de cada animação, ossos ruins em vermelho"></div>` : ""}
    <div class="lista">${linhas}</div><p class="nota">${esc(r.dica || "")}</p>`;
}
async function acaoMovimento(botao, nome, args, titulo) {
  if (!biblia) return mensagem("Abra um projeto antes.", "alerta");
  const arquivo = $("mov-personagem").value;
  if (!arquivo) return mensagem("Crie um personagem antes (Forjar).", "alerta");
  const texto = botao.textContent;
  botao.disabled = true; botao.textContent = "Trabalhando…"; calor(true);
  try {
    const r = await ferramenta(nome, { arquivo, ...args });
    if (nome === "show_skeleton") {
      const img = await dataUrl(r.imagem);
      $("mov-resultado").innerHTML = `${img ? `<div class="capturas"><img src="${img}" alt="Esqueleto com os ossos numerados"></div>` : ""}
        ${(r.avisos || []).length ? `<p class="nota">${r.avisos.map(esc).join("<br>")}</p>` : `<p class="nota">Nenhum aviso no esqueleto.</p>`}
        <div class="lista">${r.ossos.map((o) => `<div class="item"><div><strong>${o.n}. ${esc(o.nome)}</strong><small>pai: ${esc(o.pai || "—")} · ${numero(o.comprimento_cm, 1)} cm${o.mola ? " · mola" : ""}</small></div>
          <div class="lado"><span class="selo">${o.vertices_que_carrega} vértices</span></div></div>`).join("")}</div>`;
    } else await mostrarConferencia(r, titulo);
    return r;
  } catch (err) { mensagem(err.message, err.codigo === "precisa_aceite" ? "alerta" : "erro"); return null; }
  finally { botao.disabled = false; botao.textContent = texto; calor(false); }
}
$("mov-conferir").addEventListener("click", () => acaoMovimento($("mov-conferir"), "check_motion", { imagens: "todas" }, "Conferência"));
$("mov-corrigir").addEventListener("click", () => acaoMovimento($("mov-corrigir"), "check_motion", { imagens: "todas", corrigir: true }, "Conferência com correção"));
$("mov-esqueleto").addEventListener("click", () => acaoMovimento($("mov-esqueleto"), "show_skeleton", {}, "Esqueleto"));
$("mov-vestir").addEventListener("click", async () => {
  const roupa = await escolherArquivo("Roupa ou armadura (glb, obj, fbx)");
  if (!roupa) return;
  const r = await acaoMovimento($("mov-vestir"), "dress_character", { roupa, rigido: $("mov-rigido").value, encaixar: $("mov-encaixar").checked }, "Roupa vestida");
  if (r && r.roupa) mensagem(`Roupa vestida: ${r.roupa.ilhas_rigidas} placas rígidas, ${r.roupa.ilhas_de_pano} partes de pano.`);
});
$("mov-etiquetas").addEventListener("click", (e) => { const b = e.target.closest("[data-etiqueta]"); if (b) { etiquetaMov = b.dataset.etiqueta; pintarMovimento(); } });
let esperaBusca = null;
$("mov-busca").addEventListener("input", (e) => { clearTimeout(esperaBusca); esperaBusca = setTimeout(() => { buscaMov = e.target.value.trim(); pintarBanco(); }, 400); });
$("mov-banco").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-aplicar]");
  if (!b) return;
  const como = (document.querySelector(`[data-como="${CSS.escape(b.dataset.aplicar)}"]`) || {}).value || "";
  if (!como.trim()) return mensagem("Diga o nome da animação no jogo.", "alerta");
  await acaoMovimento(b, "apply_motion", { clipes: [{ id: b.dataset.aplicar, como: como.trim(), ciclo: !!b.dataset.ciclo }], video: true }, `"${como.trim()}" no personagem`);
});

// ---------- Testar ----------
let ultimoTeste = null;
function pintarTestar() {
  const prog = (estado && estado.programas) || {};
  const quer = biblia && biblia.engine === "erethea" ? "erethea" : "godot";
  const e = prog[quer] || {};
  const outra = prog[quer === "godot" ? "erethea" : "godot"] || {};
  pinta($("motor"), `<div><strong>${esc(e.nome || "Engine")}${e.achado ? " " + esc(e.versao || "") : ""}</strong>
    <small>${e.achado ? esc(e.caminho) : outra.achado ? `Não encontrada; a Fornalha usa a ${esc(outra.nome)} (o projeto abre igual nas duas).` : "Nenhuma engine encontrada: instale a Godot ou a Erethea, ou escolha o executável em Máquina."}</small></div>
    <span class="selo ${e.achado || outra.achado ? "venda" : "erro"}">${e.achado || outra.achado ? "Pronta" : "Falta a engine"}</span>`);
  if (ultimoTeste) mostrarTeste(ultimoTeste);
}
async function acaoEngine(botao, nome, args) {
  if (!biblia) return mensagem("Abra um projeto antes.", "alerta");
  const texto = botao.textContent;
  botao.disabled = true; botao.textContent = "Trabalhando…"; calor(true);
  try { return await ferramenta(nome, args); }
  catch (err) { mensagem(err.message, "erro"); return null; }
  finally { botao.disabled = false; botao.textContent = texto; calor(false); }
}
$("montar").addEventListener("click", async () => {
  const r = await acaoEngine($("montar"), "import_to_engine", {});
  if (r) mensagem(`Cenas montadas na ${r.engine}: ${r.cenas.length} cenas.${(r.avisos || []).length ? " " + r.avisos.join(" ") : ""}`);
});
$("rodar-teste").addEventListener("click", async () => {
  const r = await acaoEngine($("rodar-teste"), "run_test", { video: true });
  if (r) { ultimoTeste = r; mostrarTeste(r); }
});
async function mostrarTeste(r) {
  const passou = r.passou;
  const capturas = await Promise.all((r.capturas || []).slice(0, 4).map(dataUrl));
  const assets = (r.assets || []).map((a) => `<div class="item"><div><strong class="mono">${esc(a.arquivo)}</strong></div><div class="lado"><span>${numero(a.triangulos)} triângulos</span><span class="selo">${kb(a.bytes)}</span></div></div>`).join("");
  $("resultado-teste").innerHTML = `
    <div class="veredito ${passou ? "passou" : "falhou"}"><strong>${passou ? "O jogo passou no teste" : "O jogo não passou"}</strong>
      <span>${esc(r.engine && r.engine.string ? "Engine " + r.engine.string : "")} · ${esc(r.modo || "")}</span>
      ${r.video ? `<button class="botao" data-abrir="${esc(r.video)}" style="margin-left:auto">Abrir vídeo</button>` : ""}</div>
    <dl class="medidas">
      <div><dt>erros da engine</dt><dd>${(r.erros || []).length}</dd></div>
      <div><dt>jogador andou</dt><dd>${numero((r.jogador || {}).andou_m || 0, 1)} m</dd></div>
      <div><dt>inimigos que reagiram</dt><dd>${(r.inimigos || {}).perseguiram || 0} de ${(r.inimigos || {}).total || 0}</dd></div>
      <div><dt>quadros por segundo</dt><dd>${numero(r.fps_medio || 0, 0)}</dd></div>
    </dl>
    ${(r.erros || []).length ? `<section class="painel"><h2>Erros da engine</h2><div class="erros-engine">${esc(r.erros.join("\n"))}</div></section>` : ""}
    <div class="capturas">${capturas.filter(Boolean).map((u) => `<img src="${u}" alt="Captura do jogo">`).join("")}</div>
    <section class="painel"><h2>Modelos no jogo</h2><div class="lista">${assets || '<p class="vazio">Nenhum modelo.</p>'}</div></section>`;
}

// ---------- Licenças ----------
const SITUACAO = { liberado: ["venda", "Pode vender"], bloqueado: ["erro", "Bloqueado"], precisa_aceite: ["teste", "Precisa do seu aceite"], precisa_receita: ["teste", "Informe a receita"] };
let modelos = null;
async function pintarLicencas() {
  modelos = await ferramenta("list_models");
  $("painel-pendencias").hidden = !biblia;
  if (biblia) {
    const p = await ferramenta("check_licenses");
    $("pendencias-titulo").textContent = `Antes de vender ${biblia.nome}`;
    const itens = [
      ...p.bloqueiam_venda.map((x) => ["erro", x.arquivo, `Bloqueia a venda (${x.modelo}). ${x.motivo}`]),
      ...p.precisam_atencao.map((x) => ["teste", x.arquivo, `Precisa de atenção (${x.modelo}). ${x.motivo}`]),
      ...p.sem_recibo.map((a) => ["teste", a, "Sem recibo de licença."]),
      ...p.alterados.map((a) => ["", a, "Mudou depois do recibo (só aviso)."]),
      ...p.sumidos.map((a) => ["", a, "Tem recibo, mas o arquivo sumiu (só aviso)."]),
    ];
    pinta($("pendencias"), itens.length ? itens.map(([c, a, t]) => `<div class="item"><div><strong class="mono">${esc(a)}</strong><small>${esc(t)}</small></div><span class="selo ${c}">${c === "erro" ? "Bloqueia" : c ? "Atenção" : "Aviso"}</span></div>`).join("")
      : `<p class="vazio">Tudo certo: todos os assets têm recibo e licença que deixa vender.</p>`);
  }
  const est = (info && info.estudio) || { receita_anual_usd: null, licencas_aceitas: [] };
  const grupos = (info && info.grupos_de_aceite) || modelos.grupos_de_aceite || {};
  const pode = !!info;
  pinta($("estudio"), `<div class="item"><div><strong>Receita anual do estúdio (US$)</strong><small>Algumas licenças são grátis só até um teto de receita.</small></div>
      <input type="number" min="0" step="1000" id="receita" style="width:160px" value="${est.receita_anual_usd ?? ""}" placeholder="não informada" ${pode ? "" : "disabled"}></div>
    ${Object.entries(grupos).map(([id, g]) => `<div class="item"><div><strong>${esc(g.nome)}</strong><small>${esc(g.texto)}</small></div>
      <label class="chave"><input type="checkbox" data-aceite="${esc(id)}" ${est.licencas_aceitas.includes(id) ? "checked" : ""} ${pode ? "" : "disabled"}><span>Aceito</span></label></div>`).join("")}`);
  const filtro = $("filtro-funcao");
  if (filtro.options.length === 1) for (const f of modelos.funcoes) filtro.add(new Option(f.nome, f.id));
  pintarCatalogo();
}
function pintarCatalogo() {
  if (!modelos) return;
  const so = $("filtro-funcao").value;
  pinta($("catalogo"), modelos.funcoes.filter((f) => !so || f.id === so).map((f) => {
    const ms = modelos.modelos.filter((m) => m.funcao === f.id);
    return ms.length ? `<div class="grupo-catalogo">${esc(f.nome)}</div>` + ms.map((m) => {
      const [cor, rotulo] = SITUACAO[m.situacao.situacao] || ["", m.situacao.situacao];
      const extra = [m.requer_cuda ? "precisa de CUDA" : "", m.onde === "api" ? "serviço pago" : "", m.onde === "fornalha" ? "da própria Fornalha" : ""].filter(Boolean).join(", ");
      const motivo = m.situacao.motivo || m.situacao.texto || (m.obrigacoes || []).join(" ") || m.nota || "";
      return `<div class="item"><div><strong>${esc(m.nome)}</strong><small><a href="#" data-link="${esc(m.url_licenca)}">${esc(m.licenca)}</a>${extra ? ", " + esc(extra) : ""}</small>${motivo ? `<small>${esc(motivo)}</small>` : ""}</div><span class="selo ${cor}">${rotulo}</span></div>`;
    }).join("") : "";
  }).join(""));
}
$("filtro-funcao").addEventListener("change", pintarCatalogo);
$("estudio").addEventListener("change", async (e) => {
  if (!e.target.matches("#receita, [data-aceite]")) return;
  const receita = $("receita").value.trim();
  const aceitas = [...document.querySelectorAll("[data-aceite]")].filter((c) => c.checked).map((c) => c.dataset.aceite);
  try { await api("POST", "/janela/estudio", { receita_anual_usd: receita === "" ? null : Math.max(0, Math.floor(Number(receita))), licencas_aceitas: aceitas }); mensagem("Decisões do estúdio salvas."); carregar("licencas"); }
  catch (err) { mensagem(err.message, "erro"); }
});
$("exportar-creditos").addEventListener("click", async () => {
  try { const r = await ferramenta("export_credits"); mensagem(`Créditos salvos em ${r.arquivo}.`); } catch (err) { mensagem(err.message, "erro"); }
});

// ---------- Máquina ----------
let vigiaProgramas = null;
async function pintarMaquina() {
  const [det, niveis] = await Promise.all([ferramenta("detect_gpu"), ferramenta("list_quality_levels")]);
  const s = det.sugestao, a = s.aceleradores;
  const g = (det.placas || []).find((x) => x.nome === s.placa) || (det.placas || [])[0];
  pinta($("placa"), `<h2>${esc(s.placa || "Sem placa de vídeo dedicada")}</h2>
    <p class="nota" style="margin-top:0">${esc(s.motivo)}</p>
    <p><span class="selo cobre">Sugerido: ${esc(NOME_NIVEL[s.nivel])}</span> ${[["CUDA", a.cuda], ["ROCm", a.rocm], ["Vulkan", a.vulkan]].map(([n, ok]) => `<span class="selo ${ok ? "venda" : ""}">${n}${ok ? "" : ": não"}</span>`).join(" ")}</p>
    <dl class="contagens"><div><dt>memória de vídeo</dt><dd>${gbDeMb(s.vram_mb)}</dd></div><div><dt>RAM</dt><dd>${gbDeMb(det.ram_total_mb)}</dd></div></dl>
    <p class="nota">${esc((g && g.versao_driver) ? "Driver " + g.versao_driver + ". " : "")}${esc(det.sistema.nome)}.</p>
    ${(s.avisos || []).map((x) => `<p class="nota">${esc(x)}</p>`).join("")}`);
  const prog = (estado && estado.programas) || {};
  const baixando = (estado && estado.downloads_de_programas) || {};
  pinta($("programas"), ["blender", "godot", "erethea"].map((id) => {
    const p = prog[id] || {}, d = baixando[id];
    const situacao = d && d.baixando ? `Baixando ${d.versao}… ${d.mb ? d.mb + " MB" : ""}`
      : p.achado ? p.caminho : d && d.ultima && d.ultima.includes("ERRO") ? d.ultima : "Não encontrado";
    // Blender e Godot: a Fornalha baixa a versão testada (soma conferida); a Erethea é do criador
    const baixar = p.achado || (d && d.baixando) ? ""
      : d ? `<button class="botao" data-baixar-programa="${id}">Baixar ${esc(d.versao)} (${esc(d.tamanho)})</button>`
      : `<a href="#" data-link="${esc(p.pagina || "")}">Baixar</a>`;
    return `<div class="item"><div><strong>${esc(p.nome || id)}${p.achado && p.versao ? " " + esc(p.versao) : ""}</strong><small class="mono">${esc(situacao)}</small></div>
      <div class="lado">${baixar}<button class="botao" data-programa="${id}">Escolher</button></div></div>`;
  }).join(""));
  clearTimeout(vigiaProgramas);
  if (Object.values(baixando).some((d) => d.baixando)) vigiaProgramas = setTimeout(() => { if (!$("est-maquina").hidden) carregar("maquina"); }, 3000);
  pintarModelosDePlaca(a.cuda);
  pintarComfyUI();
  pintarApis();
  pintarPacotes();
  $("nivel-maquina").value = (info && info.nivel_da_maquina) || "auto";
  const emUso = niveis.nivel_em_uso;
  const cab = `<thead><tr><th>Função</th>${niveis.tabela.map((l) => `<th class="${l.nivel === emUso ? "em-uso" : ""}">${esc(l.nome)}<small>${esc(l.faixa)}</small></th>`).join("")}</tr></thead>`;
  const linhas = niveis.funcoes.map((f) => `<tr><th>${esc(f.nome)}</th>${niveis.tabela.map((l) => {
    const e = l.funcoes.find((x) => x.funcao === f.id), cls = l.nivel === emUso ? "em-uso" : "";
    if (!e || !e.modelo) return `<td class="${cls}"><span class="sem" title="${esc(e && e.recusados.length ? e.recusados.map((r) => r.motivo).join("\n") : "Sem modelo neste nível.")}">—</span></td>`;
    const desceu = e.nivel_usado && e.nivel_usado !== l.nivel ? `<span class="desceu">opção do ${esc(NOME_NIVEL[e.nivel_usado])}</span>` : "";
    return `<td class="${cls}">${esc(e.modelo.nome)}${desceu}</td>`;
  }).join("")}</tr>`).join("");
  pinta($("tabela-niveis"), cab + "<tbody>" + linhas + "</tbody>");
}
let vigiaPacotes = null;
function pintarPacotes() {
  const lista = (estado && estado.pacotes) || [];
  pinta($("pacotes"), lista.map((p) => {
    const situacao = p.baixando ? "Baixando…" : p.instalado ? "Instalado" : `Não baixado (${p.tamanho})`;
    const ultima = p.log && p.log.length ? p.log[p.log.length - 1] : "";
    return `<div class="item"><div><strong>${esc(p.nome)}</strong><small>${esc(situacao)}</small>${p.baixando && ultima ? `<small class="mono">${esc(ultima)}</small>` : ""}</div>
      <div class="lado">${p.baixando ? "" : `<button class="botao${p.instalado ? "" : " quente"}" data-pacote="${esc(p.id)}">${p.instalado ? "Baixar de novo" : "Baixar"}</button>`}</div></div>`;
  }).join(""));
  clearTimeout(vigiaPacotes);
  if (lista.some((p) => p.baixando)) vigiaPacotes = setTimeout(() => { if (!$("est-maquina").hidden) carregar("maquina"); }, 4000);
}
$("pacotes").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-pacote]");
  if (!b) return;
  b.disabled = true;
  try { await api("POST", "/janela/pacote", { id: b.dataset.pacote }); mensagem("Download começou."); } catch (err) { mensagem(err.message, "erro"); }
  carregar("maquina");
});
let vigiaModelos = null;
function pintarModelosDePlaca(cuda) {
  const lista = (estado && estado.modelos_de_placa) || [];
  const aceitas = (info && info.estudio && info.estudio.licencas_aceitas) || [];
  pinta($("modelos-placa"), lista.map((m) => {
    const falta = !cuda ? "Precisa de placa NVIDIA (CUDA)." : m.aceite && !aceitas.includes(m.aceite) ? "Aceite a licença da Tencent em Licenças antes de instalar." : "";
    const situacao = m.instalando ? "Instalando…" : m.verificado ? (m.sem.includes("nvdiffrast") ? "Pronto e verificado sem o nvdiffrast" : "Pronto e verificado") : m.instalado ? "Instalado, falta verificar" : "Não instalado";
    const ultima = m.log && m.log.length ? m.log[m.log.length - 1] : "";
    const botoes = m.instalando ? "" : m.instalado
      ? `<button class="botao" data-modelo="${esc(m.id)}" data-acao="verificar">Verificar</button>`
      : `<button class="botao" data-modelo="${esc(m.id)}" data-acao="instalar" ${falta ? "disabled" : ""}>Instalar</button>`;
    return `<div class="item"><div><strong>${esc(m.nome)}</strong><small>${esc(falta || situacao)}</small>${ultima && (m.instalando || !m.instalado) ? `<small class="mono">${esc(ultima)}</small>` : ""}</div><div class="lado">${botoes}</div></div>`;
  }).join(""));
  clearTimeout(vigiaModelos);
  if (lista.some((m) => m.instalando)) vigiaModelos = setTimeout(() => { if (!$("est-maquina").hidden) carregar("maquina"); }, 5000);
}
let vigiaComfy = null;
function pintarComfyUI() {
  const c = (estado && estado.comfyui) || {};
  const e = c.estado || {};
  const inst = c.instalacao || {};
  const cam = c.caminho || {};
  const placas = (e.dispositivos || []).map((d) => d.nome).filter(Boolean).join(", ");
  const vk = c.vulkan;
  const placaVk = vk ? (vk.dispositivos || []).map((d) => d.split("\t")[1] || d).join(", ") : "";
  const situacao = e.conectado ? `Aberto${e.versao ? " (" + e.versao + ")" : ""}${placas ? " — " + placas : ""}`
    : inst.instalando ? "Instalando…"
    : vk ? `Motor Vulkan pronto (stable-diffusion.cpp)${placaVk ? " — " + placaVk : ""}`
    : inst.instalado ? "Instalado (fechado)" : "Não instalado";
  const modelo = c.modelo_de_imagem ? `Imagem: ${c.modelo_de_imagem.id}`
    : vk ? `Imagem: ${vk.id_do_modelo} (roda na hora de gerar, não fica aberto)`
    : e.conectado ? "Sem modelo de imagem de licença comercial instalado" : "";
  const ultima = inst.log && inst.log.length ? inst.log[inst.log.length - 1] : "";
  // placa sem CUDA nem ROCm (RX 580): o 3D pela IA fica num ComfyUI à parte, no processador
  const t3 = c.tres_d_no_processador;
  const tem3d = t3 ? !!t3.instalado : !!(inst.instalacao && (inst.instalacao.modelos || []).some((m) => m.includes("trellis_2")));
  const botoes = inst.instalando ? "" : (!inst.instalado
    ? `<button class="botao" data-comfy="instalar">Instalar</button>`
    : e.conectado || vk ? "" : `<button class="botao" data-comfy="abrir">Abrir</button>`)
    + (tem3d || (t3 && t3.instalando) ? "" : ` <button class="botao" data-comfy="instalar_3d" title="TRELLIS.2 + DINOv3, ~8,5 GB; precisa do aceite da licença do DINOv3 em Licenças">Instalar o 3D pela IA${t3 ? " (no processador)" : ""}</button>`);
  const ultima3 = t3 && t3.log && t3.log.length ? t3.log[t3.log.length - 1] : "";
  pinta($("comfyui"), `<div class="item"><div><strong>${esc(situacao)}</strong>`
    + `<small>${esc(cam.backend ? "Caminho nesta máquina: " + cam.backend + " — " + (cam.motivo || "") : "")}</small>`
    + (modelo ? `<small>${esc(modelo)}</small>` : "")
    + (ultima && (inst.instalando || !inst.instalado) ? `<small class="mono">${esc(ultima)}</small>` : "")
    + `</div><div class="lado">${botoes}</div></div>`
    + (t3 ? `<div class="item"><div><strong>3D pela IA no processador: ${t3.instalando ? "instalando…" : t3.instalado ? "instalado" : "não instalado"}</strong>`
      + `<small>Esta placa não roda o TRELLIS.2 (sem CUDA nem ROCm): ele roda no processador, ao lado do motor de imagem, que continua na placa. Leva de 2 a 4 horas por personagem num processador de 6 núcleos; peça na fila da noite. A qualidade é a mesma da placa, só demora.</small>`
      + (ultima3 && t3.instalando ? `<small class="mono">${esc(ultima3)}</small>` : "") + `</div></div>` : ""));
  clearTimeout(vigiaComfy);
  if (inst.instalando || (t3 && t3.instalando)) vigiaComfy = setTimeout(() => { if (!$("est-maquina").hidden) carregar("maquina"); }, 5000);
}
function pintarApis() {
  const lista = (estado && estado.apis_3d) || [];
  pinta($("apis"), lista.map((a) => `<div class="item"><div><strong>${esc(a.nome)}${a.ligada ? " — ligada" : ""}</strong>
      <small>${esc(a.preco)}</small><small>${esc(a.licenca)} <a href="#" data-link="${esc(a.url_licenca)}">Termos</a> · <a href="#" data-link="${esc(a.url_chave)}">Onde pegar a chave</a></small>
      <span style="display:flex;gap:8px;margin-top:6px"><input type="password" id="chave-${esc(a.id)}" placeholder="${a.tem_chave ? "chave guardada" : "cole a chave aqui"}" autocomplete="off" style="flex:1;min-width:0">
      <button class="botao" data-api-chave="${esc(a.id)}">Salvar chave</button></span></div>
      <div class="lado"><label class="chave"><input type="checkbox" data-api-ligar="${esc(a.id)}" ${a.ligada ? "checked" : ""} ${a.tem_chave ? "" : "disabled"}><span>Ligada</span></label></div></div>`).join(""));
}
$("apis").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-api-chave]");
  if (!b) return;
  const id = b.dataset.apiChave, campo = $("chave-" + id);
  try { await api("POST", "/janela/api", { provedor: id, chave: campo.value }); campo.value = ""; mensagem("Chave guardada neste computador."); carregar("maquina"); }
  catch (err) { mensagem(err.message, "erro"); }
});
$("apis").addEventListener("change", async (e) => {
  const c = e.target.closest("[data-api-ligar]");
  if (!c) return;
  try { await api("POST", "/janela/api", { provedor: c.dataset.apiLigar, ligada: c.checked }); mensagem(c.checked ? "API ligada: o Personagem sai por ela." : "API desligada."); carregar("maquina"); }
  catch (err) { mensagem(err.message, "erro"); c.checked = !c.checked; }
});
$("comfyui").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-comfy]");
  if (!b) return;
  b.disabled = true;
  try {
    if (b.dataset.comfy === "instalar") {
      await api("POST", "/janela/comfyui", { acao: "instalar" });
      mensagem("Instalação do motor de imagem começou (alguns GB). Dá para continuar usando a Fornalha.");
    } else if (b.dataset.comfy === "instalar_3d") {
      await api("POST", "/janela/comfyui", { acao: "instalar_3d" });
      mensagem("Instalação do 3D pela IA começou (~8,5 GB). Depois, o Personagem sai da IA: imagem → malha → esqueleto.");
    } else {
      mensagem("Abrindo o ComfyUI…");
      await api("POST", "/janela/comfyui", { acao: "abrir" });
      mensagem("ComfyUI aberto.");
    }
  } catch (err) { mensagem(err.message, "erro"); }
  carregar("maquina");
});
$("bruto-rodar").addEventListener("click", async (e) => {
  const b = e.target;
  const nivel = $("bruto-nivel").value;
  b.disabled = true;
  $("bruto-situacao").textContent = "Rodando… (vários minutos; dá para continuar usando a Fornalha)";
  pinta($("bruto-resultado"), "");
  try {
    const r = await ferramenta("run_brute_test", { nivel });
    const linhas = (r.casos || []).map((c) => `<div class="item"><div><strong>${c.passou ? "✓" : "✗"} ${esc(c.titulo)}</strong>`
      + `<small>${Math.round(c.segundos)} s${c.erro ? " — " + esc(c.erro) : ""}</small>`
      + (c.passou ? "" : `<small class="mono">${esc((c.verificacoes || []).filter((v) => !v.ok).map((v) => v.nome + ": " + v.detalhe).join(" | "))}</small>`)
      + `</div></div>`);
    if (r.engine) linhas.push(`<div class="item"><div><strong>${r.engine.passou ? "✓" : "✗"} Jogo na engine</strong><small>${Math.round(r.engine.segundos || 0)} s</small></div></div>`);
    (r.gerais || []).forEach((g) => linhas.push(`<div class="item"><div><strong>${g.ok ? "✓" : "✗"} ${esc(g.nome)}</strong><small>${esc(g.detalhe || "")}</small></div></div>`));
    pinta($("bruto-resultado"), linhas.join(""));
    $("bruto-situacao").textContent = r.passou ? `Passou em ${Math.round(r.segundos / 60)} min. Relatório em ${r.projeto}/testes/teste_bruto.json` : "Algum caso falhou: veja abaixo (o relatório está na pasta testes do projeto).";
  } catch (err) { $("bruto-situacao").textContent = err.message; mensagem(err.message, "erro"); }
  b.disabled = false;
});
$("modelos-placa").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-modelo]");
  if (!b) return;
  b.disabled = true;
  try {
    if (b.dataset.acao === "instalar") {
      await api("POST", "/janela/modelo-de-placa", { id: b.dataset.modelo, acao: "instalar" });
      mensagem("Instalação começou. São vários GB; dá para continuar usando a Fornalha.");
    } else {
      mensagem("Verificando com uma geração de teste…");
      await api("POST", "/janela/modelo-de-placa", { id: b.dataset.modelo, acao: "verificar" });
      mensagem("Modelo verificado.");
    }
  } catch (err) { mensagem(err.message, "erro"); }
  carregar("maquina");
});
$("programas").addEventListener("click", async (e) => {
  const bx = e.target.closest("[data-baixar-programa]");
  if (bx) {
    bx.disabled = true;
    try {
      await api("POST", "/janela/programa", { id: bx.dataset.baixarPrograma });
      mensagem("Download começou. Dá para continuar usando a Fornalha.");
    } catch (err) { mensagem(err.message, "erro"); }
    carregar("maquina");
    return;
  }
  const b = e.target.closest("[data-programa]");
  if (!b) return;
  const caminho = await escolherArquivo(`Executável do ${b.dataset.programa}`);
  if (!caminho) return;
  try { await api("POST", "/janela/ajustes", { programa: { nome: b.dataset.programa, caminho } }); mensagem("Programa salvo."); carregar("maquina"); }
  catch (err) { mensagem(err.message, "erro"); }
});
$("nivel-maquina").addEventListener("change", async (e) => {
  try { await api("POST", "/janela/ajustes", { nivel: e.target.value }); mensagem("Nível desta máquina salvo."); carregar("maquina"); } catch (err) { mensagem(err.message, "erro"); }
});

// ---------- Agentes ----------
async function pintarAgentes() {
  const mcp = (estado && estado.endereco_mcp) || BASE_DEV + "/mcp";
  const c = (info && info.comandos) || { claude_http: `claude mcp add --transport http fornalha ${mcp}`, claude_stdio: "claude mcp add fornalha -- fornalha --mcp", codex: "codex mcp add fornalha -- fornalha --mcp" };
  const blocos = [
    ["Claude Code, com a Fornalha aberta", "Usa a Fornalha que está perto do relógio.", c.claude_http],
    ["Claude Code, mesmo com o app fechado", "O Claude Code abre a Fornalha sem janela quando precisar.", c.claude_stdio],
    ["Codex", "O mesmo servidor MCP, pelo Codex.", c.codex],
    ["API local", "Para scripts: lista as ferramentas; chame com POST /fornalha/ferramentas/{nome}.", mcp.replace("/mcp", "/fornalha/ferramentas")],
  ];
  pinta($("comandos"), blocos.map(([t, s, cmd]) => `<div class="comando"><div class="item"><div><strong>${esc(t)}</strong><small>${esc(s)}</small></div><button class="botao" data-copiar="${esc(cmd)}">Copiar</button></div><pre>${esc(cmd)}</pre></div>`).join(""));
  const lista = await api("GET", "/fornalha/ferramentas").catch(() => ({ ferramentas: [] }));
  pinta($("ferramentas"), lista.ferramentas.map((f) => `<div class="item"><div><strong class="mono">${esc(f.nome)}</strong><small>${esc(f.titulo)}</small></div></div>`).join(""));
}

// ---------- Ajustes ----------
function temaAtual() { try { return localStorage.getItem("fornalha.tema") || "auto"; } catch (_) { return "auto"; } }
$("tema").addEventListener("change", (e) => {
  const t = e.target.value;
  try { localStorage.setItem("fornalha.tema", t); } catch (_) { /* sem armazenamento: vale só agora */ }
  if (t === "auto") delete document.documentElement.dataset.tema; else document.documentElement.dataset.tema = t;
});
function pintarAjustes() {
  $("tema").value = temaAtual();
  if (!info) { $("versao").textContent = "Fora do aplicativo (modo navegador)."; return; }
  $("estilo-janela").value = info.estilo_janela || "auto";
  $("ajuste-pasta").textContent = info.pasta_projetos;
  const n = info.noite || { inicio_hora: 23, fim_hora: 7 };
  $("noite-inicio").value = n.inicio_hora; $("noite-fim").value = n.fim_hora;
  $("versao").textContent = `Fornalha ${info.versao} · ${info.exe}`;
}
$("estilo-janela").addEventListener("change", async (e) => {
  try { await api("POST", "/janela/ajustes", { estilo_janela: e.target.value }); if (window.montarBotoesJanela) window.montarBotoesJanela(e.target.value); } catch (err) { mensagem(err.message, "erro"); }
});
for (const id of ["noite-inicio", "noite-fim"]) $(id).addEventListener("change", async () => {
  const inicio_hora = Math.min(23, Math.max(0, parseInt($("noite-inicio").value || "23", 10)));
  const fim_hora = Math.min(23, Math.max(0, parseInt($("noite-fim").value || "7", 10)));
  try { await api("POST", "/janela/ajustes", { noite: { inicio_hora, fim_hora } }); info.noite = { inicio_hora, fim_hora }; mensagem("Horário da noite salvo."); } catch (err) { mensagem(err.message, "erro"); }
});
$("ajuste-escolher-pasta").addEventListener("click", async () => {
  const p = await escolherPasta("Pasta dos projetos novos");
  if (!p) return;
  try { await api("POST", "/janela/ajustes", { pasta_projetos: p }); $("novo-pasta").value = p; pintarAjustes(); mensagem("Pasta salva."); } catch (err) { mensagem(err.message, "erro"); }
});
$("abrir-registros").addEventListener("click", () => abrirPasta("registros"));

// ---------- começo ----------
irPara("projeto");
document.addEventListener("visibilitychange", () => { if (!document.hidden) carregar(estacao); });
