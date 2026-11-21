// Janela da Fornalha. Fala com o núcleo pelo Tauri (sem rede); fora do Tauri
// (desenvolvimento no navegador), usa a API local em 127.0.0.1:11480.
// A barra de título integrada veio do Ignis.
"use strict";

const tauri = window.__TAURI__ && window.__TAURI__.core;
const $ = (id) => document.getElementById(id);
let secao = "inicio";
let info = null;     // /janela/info (só no app)
let estado = null;   // get_status
let niveis = null;   // list_quality_levels
let deteccao = null; // detect_gpu
let modelos = null;  // list_models

// ---------- comportamento de aplicativo (não de página) ----------
document.addEventListener("contextmenu", (e) => {
  if (!e.target.closest("input, textarea, pre, code")) e.preventDefault();
});
document.addEventListener("keydown", (e) => {
  const k = e.key.toLowerCase();
  const ctrl = e.ctrlKey || e.metaKey;
  if (k === "f5" || (ctrl && ["r", "p", "u", "+", "-", "=", "0"].includes(k)) || (ctrl && e.shiftKey && k === "i")) e.preventDefault();
});
document.addEventListener("wheel", (e) => { if (e.ctrlKey) e.preventDefault(); }, { passive: false });
document.addEventListener("dragstart", (e) => { if (!e.target.closest("input, textarea")) e.preventDefault(); });

// ---------- barra de título integrada (do Ignis) ----------
document.documentElement.dataset.so = /windows/i.test(navigator.userAgent) ? "windows" : /mac os/i.test(navigator.userAgent) ? "mac" : "linux";
const ICONES_JANELA = {
  windows: { caixa: 10,
    minimize: '<path d="M0 5.5h10"/>',
    maximize: '<rect x=".5" y=".5" width="9" height="9" rx="1"/>',
    restaurar: '<path d="M2.5 2.5V1.5a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-1"/><rect x=".5" y="2.5" width="7" height="7" rx="1"/>',
    close: '<path d="M.5.5l9 9M9.5.5l-9 9"/>' },
  gnome: { caixa: 16,
    minimize: '<path d="M4.5 11.5h7"/>',
    maximize: '<rect x="4" y="4" width="8" height="8" rx="1.5"/>',
    restaurar: '<rect x="3.5" y="6" width="6.5" height="6.5" rx="1.2"/><path d="M6 4h5a1 1 0 0 1 1 1v5"/>',
    close: '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>' },
  kde: { caixa: 16,
    minimize: '<path d="M4 6.5l4 4 4-4"/>',
    maximize: '<path d="M4 10l4-4 4 4"/>',
    restaurar: '<path d="M8 3.5l4.5 4.5L8 12.5 3.5 8z"/>',
    close: '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>' },
  mac: { caixa: 12,
    minimize: '<path d="M2.8 6h6.4"/>',
    maximize: '<path d="M3.4 3.3h3.3L3.4 6.6zM8.6 8.7H5.3l3.3-3.3z" fill="currentColor" stroke="none"/>',
    restaurar: '<path d="M5.7 5.7H2.9l2.8-2.8zM6.3 6.3h2.8L6.3 9.1z" fill="currentColor" stroke="none"/>',
    close: '<path d="M3.7 3.7l4.6 4.6M8.3 3.7L3.7 8.3"/>' },
};
ICONES_JANELA.matsu = ICONES_JANELA.mac;
const NOMES_JANELA = { minimize: "Minimizar", maximize: "Maximizar", close: "Fechar (a Fornalha continua perto do relógio)" };

(function barraDeTitulo() {
  const w = window.__TAURI__ && window.__TAURI__.window && window.__TAURI__.window.getCurrentWindow();
  if (!w) return;
  const raiz = document.documentElement;
  const svg = (estilo, d) => { const c = ICONES_JANELA[estilo].caixa; return `<svg viewBox="0 0 ${c} ${c}" aria-hidden="true">${d}</svg>`; };
  const marcar = async () => {
    const max = await w.isMaximized().catch(() => false);
    raiz.toggleAttribute("data-maximizada", max);
    for (const b of document.querySelectorAll('[data-janela="maximize"]')) {
      const nome = max ? "Restaurar" : "Maximizar";
      b.title = nome;
      b.setAttribute("aria-label", nome);
    }
  };
  window.montarBotoesJanela = async (preferido) => {
    const b = await tauri.invoke("botoes_janela", { preferido: preferido || "auto" });
    const ic = ICONES_JANELA[b.estilo] || ICONES_JANELA.windows;
    raiz.dataset.botoes = b.estilo;
    raiz.toggleAttribute("data-botoes-esquerda", b.esquerda.length > 0);
    for (const [lado, lista] of [["esquerda", b.esquerda], ["direita", b.direita]]) {
      const caixa = $("controles-" + lado);
      caixa.innerHTML = lista.map((nome) => {
        const desenho = nome === "maximize"
          ? `<span class="i-max">${svg(b.estilo, ic.maximize)}</span><span class="i-rest">${svg(b.estilo, ic.restaurar)}</span>`
          : svg(b.estilo, ic[nome]);
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
  api("GET", "/janela/info")
    .then((c) => montarBotoesJanela(c.estilo_janela))
    .catch(() => montarBotoesJanela("auto"));
  marcar();
  w.onResized(marcar);

  // Arrastar e duplo clique (o arraste só começa depois de o mouse andar 3 px,
  // para o duplo clique não se perder no Linux).
  const clicavel = "a, button, input, select, textarea, label, summary, [contenteditable], [role=button], [role=tab], [tabindex]:not([tabindex='-1'])";
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
    if (e.detail === 2) w.toggleMaximize();
    else inicio = { x: e.screenX, y: e.screenY };
  });
  document.addEventListener("mousemove", (e) => {
    if (!inicio) return;
    if (!(e.buttons & 1)) { inicio = null; return; }
    if (Math.abs(e.screenX - inicio.x) + Math.abs(e.screenY - inicio.y) >= 3) {
      inicio = null;
      w.startDragging();
    }
  });
  document.addEventListener("mouseup", () => { inicio = null; });
  window.addEventListener("blur", () => raiz.toggleAttribute("data-inativa", true));
  window.addEventListener("focus", () => raiz.toggleAttribute("data-inativa", false));
})();

// ---------- utilidades ----------
const BASE_DEV = "http://127.0.0.1:" + (new URLSearchParams(location.search).get("porta") || "11480");

async function api(method, path, body) {
  let status, corpo;
  if (tauri) {
    const r = await tauri.invoke("api", { method, path, body: body ?? null });
    status = r.status; corpo = r.corpo;
  } else {
    const r = await fetch(BASE_DEV + path, {
      method, headers: { "content-type": "application/json", "x-fornalha-cliente": "pessoa" }, body: body ? JSON.stringify(body) : undefined,
    });
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
function pinta(el, html) { if (el._html !== html) { el.innerHTML = html; el._html = html; } }
function mensagem(texto, nivel) {
  const el = $("aviso");
  $("aviso-texto").textContent = texto;
  el.className = "aviso" + (nivel === "erro" ? " erro-nivel" : nivel === "aviso" ? " aviso-nivel" : "");
  el.hidden = false;
  clearTimeout(mensagem._t);
  if (nivel !== "erro") mensagem._t = setTimeout(() => { el.hidden = true; }, 6000);
}
$("aviso-fechar").addEventListener("click", () => { $("aviso").hidden = true; });
function abrirLink(url) {
  if (tauri) tauri.invoke("abrir_link", { url }).catch((e) => mensagem(String(e), "erro"));
  else window.open(url, "_blank");
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (a) { e.preventDefault(); abrirLink(a.dataset.link); }
  const c = e.target.closest("[data-copiar]");
  if (c) {
    navigator.clipboard.writeText(c.dataset.copiar).then(() => mensagem("Copiado."), () => mensagem("Não consegui copiar.", "erro"));
  }
});
async function abrirPasta(caminho) {
  if (!tauri) return mensagem(caminho);
  try { await tauri.invoke("abrir_pasta", { caminho }); } catch (e) { mensagem(String(e), "erro"); }
}
async function escolherPasta(titulo) {
  if (!tauri) return null;
  return tauri.invoke("escolher_pasta", { titulo });
}
const NOME_NIVEL = { leve: "Leve", equilibrado: "Equilibrado", qualidade: "Qualidade", maximo: "Máximo" };

// ---------- navegação ----------
function irPara(s) {
  secao = s;
  for (const b of document.querySelectorAll(".menu button")) b.classList.toggle("ativo", b.dataset.secao === s);
  for (const el of document.querySelectorAll(".secao")) el.hidden = el.id !== "sec-" + s;
  $("principal").scrollTop = 0;
  carregarSecao(s);
}
for (const b of document.querySelectorAll(".menu button")) b.addEventListener("click", () => irPara(b.dataset.secao));

// ---------- dados ----------
async function carregarBase() {
  [info, estado] = await Promise.all([
    api("GET", "/janela/info").catch(() => null),
    ferramenta("get_status").catch((e) => { mensagem(e.message, "erro"); return null; }),
  ]);
  pintarRodape();
}

function pintarRodape() {
  const ponto = $("rodape-ponto");
  if (!estado) {
    ponto.className = "ponto erro";
    $("rodape-titulo").textContent = "Sem núcleo";
    $("rodape-sub").textContent = "Reabra a Fornalha";
    return;
  }
  const apiOk = !info || info.api_ok;
  ponto.className = "ponto " + (apiOk ? "ok" : "alerta");
  $("rodape-titulo").textContent = apiOk ? "Pronta para agentes" : "Porta da API ocupada";
  $("rodape-sub").textContent = estado.endereco_api.replace("http://", "");
  if (info && info.api_erro) mensagem(info.api_erro, "aviso");
}

async function carregarSecao(s) {
  try {
    if (s === "inicio") await pintarInicio();
    else if (s === "projetos") await pintarProjetos();
    else if (s === "placa") await pintarPlaca();
    else if (s === "licencas") await pintarLicencas();
    else if (s === "agentes") pintarAgentes();
    else if (s === "ajustes") pintarAjustes();
  } catch (e) {
    mensagem(e.message, "erro");
  }
}

// ---------- Início ----------
async function pintarInicio() {
  await carregarBase();
  if (!estado) return;
  const p = estado.projeto_atual;
  const ig = estado.ignis || {};
  const cartoes = [
    `<div class="cartao"><div class="rotulo">Projeto aberto</div>
      <div class="valor">${p ? esc(p.nome) : "Nenhum"}</div>
      <div class="sub">${p ? (p.comercial ? "Comercial: só modelos que deixam vender" : "Teste (não comercial)") : "Crie ou abra um projeto para começar."}</div>
      <div class="acoes"><button class="botao pequeno" data-ir="projetos">${p ? "Ver projeto" : "Novo projeto"}</button></div></div>`,
    `<div class="cartao"><div class="rotulo">Placa e nível sugerido</div>
      <div class="valor">${esc(estado.placa || "Sem placa dedicada")}</div>
      <div class="sub">Nível ${esc(NOME_NIVEL[estado.nivel_sugerido] || estado.nivel_sugerido)}</div>
      <div class="acoes"><button class="botao pequeno" data-ir="placa">Ver níveis</button></div></div>`,
    `<div class="cartao"><div class="rotulo"><span class="ponto ${ig.conectado ? "ok" : ""}"></span>Ignis (o cérebro)</div>
      <div class="valor">${ig.conectado ? "Conectado" + (ig.versao ? " · " + esc(ig.versao) : "") : "Desligado"}</div>
      <div class="sub">${ig.conectado ? esc(ig.modelo ? "Modelo: " + ig.modelo : ig.fase || "") : esc(ig.erro || "")}</div></div>`,
    `<div class="cartao"><div class="rotulo">Agentes</div>
      <div class="valor">MCP e API locais</div>
      <div class="sub mono selecionavel">${esc(estado.endereco_mcp)}</div>
      <div class="acoes"><button class="botao pequeno" data-ir="agentes">Conectar o Claude Code</button></div></div>`,
  ];
  pinta($("inicio-cartoes"), cartoes.join(""));
  const fase = [
    ["Bíblia do jogo", "game.project.json com conceito, guia visual, personagens e mundo; pastas padrão de todo projeto."],
    ["Licenças e recibos", "Catálogo com a licença de cada modelo, roteador que barra o não comercial e recibo por asset."],
    ["Placa e 4 níveis", "Detecção da placa (NVIDIA, AMD, Intel ou só processador) e o modelo de cada função por nível."],
    ["API local e MCP", "Os mesmos comandos para você, o Claude Code e o Codex, por stdio ou HTTP."],
  ];
  pinta($("inicio-fase"), fase.map(([t, s]) =>
    `<div class="linha compacta"><span class="icone-estado ok"></span><div><div class="titulo">${t}</div><div class="sub">${s}</div></div><span></span></div>`).join(""));
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-ir]"); if (b) irPara(b.dataset.ir); });

// ---------- Projetos ----------
async function pintarProjetos() {
  await carregarBase();
  const lista = await ferramenta("list_projects");
  if (!$("novo-pasta").value) $("novo-pasta").value = lista.pasta_projetos || "";
  const atual = estado && estado.projeto_atual;
  $("grupo-atual").hidden = !atual;
  if (atual) {
    const r = await ferramenta("get_project", { projeto: atual.raiz });
    const b = r.biblia, c = b.conceito || {};
    const fatos = [
      ["Gênero", c.genero], ["Câmera", c.camera], ["Estilo", c.estilo],
      ["Venda", b.comercial ? "Comercial" : "Teste"], ["Nível", b.nivel ? NOME_NIVEL[b.nivel] : "O da máquina"],
      ["Personagens", (b.personagens || []).length], ["Áreas do mundo", ((b.mundo || {}).areas || []).length],
    ];
    pinta($("projeto-atual"), `<div class="placa-topo"><div><h2>${esc(b.nome)}</h2><p class="mono selecionavel">${esc(r.raiz)}</p></div>
      <span class="etiqueta ${b.comercial ? "ok" : "alerta"}">${b.comercial ? "Jogo à venda" : "Projeto de teste"}</span></div>
      <dl class="fatos">${fatos.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v === "" || v == null ? "—" : v)}</dd></div>`).join("")}</dl>`);
    $("abrir-pasta-atual").onclick = () => abrirPasta(r.raiz);
  }
  const rec = lista.recentes || [];
  pinta($("recentes"), rec.length ? rec.map((p) => `
    <div class="linha"><span class="icone-estado ${p.existe ? "ok" : ""}"></span>
      <div><div class="titulo">${esc(p.nome || "Projeto não encontrado")}</div><div class="sub mono">${esc(p.raiz)}</div></div>
      <div class="lado">${p.existe ? `<button class="botao pequeno" data-abrir-projeto="${esc(p.raiz)}">Abrir</button>` : ""}</div></div>`).join("")
    : `<div class="vazio"><strong>Nenhum projeto ainda.</strong>Crie o primeiro acima, ou peça ao Claude Code pelo MCP.</div>`);
}
$("form-novo").addEventListener("submit", async (e) => {
  e.preventDefault();
  const args = {
    nome: $("novo-nome").value.trim(),
    comercial: $("novo-comercial").checked,
    pasta_pai: $("novo-pasta").value.trim() || undefined,
    genero: $("novo-genero").value.trim() || undefined,
    camera: $("novo-camera").value.trim() || undefined,
    estilo: $("novo-estilo").value || undefined,
  };
  $("criar").disabled = true;
  try {
    const r = await ferramenta("create_project", args);
    mensagem(`Projeto "${r.biblia.nome}" criado em ${r.raiz}.`);
    $("novo-nome").value = ""; $("novo-genero").value = ""; $("novo-camera").value = "";
    await pintarProjetos();
  } catch (err) {
    mensagem(err.message, "erro");
  } finally {
    $("criar").disabled = false;
  }
});
$("escolher-pasta").addEventListener("click", async () => {
  const p = await escolherPasta("Onde criar o projeto");
  if (p) $("novo-pasta").value = p;
});
$("abrir-projeto").addEventListener("click", async () => {
  const p = await escolherPasta("Pasta do projeto (com o game.project.json)");
  if (p) abrirProjeto(p);
});
document.addEventListener("click", (e) => { const b = e.target.closest("[data-abrir-projeto]"); if (b) abrirProjeto(b.dataset.abrirProjeto); });
async function abrirProjeto(caminho) {
  try {
    const r = await ferramenta("open_project", { caminho });
    mensagem(`Projeto "${r.biblia.nome}" aberto.`);
    await pintarProjetos();
  } catch (err) { mensagem(err.message, "erro"); }
}

// ---------- Placa e níveis ----------
async function pintarPlaca() {
  [deteccao, niveis, info] = await Promise.all([ferramenta("detect_gpu"), ferramenta("list_quality_levels"), api("GET", "/janela/info").catch(() => null)]);
  const s = deteccao.sugestao;
  const g = (deteccao.placas || []).find((x) => x.nome === s.placa) || (deteccao.placas || [])[0];
  const acel = s.aceleradores;
  const etiquetas = [["CUDA", acel.cuda], ["ROCm", acel.rocm], ["Vulkan", acel.vulkan]]
    .map(([n, ok]) => `<span class="etiqueta ${ok ? "ok" : ""}">${n}${ok ? "" : ": não"}</span>`).join("");
  pinta($("placa-cartao"), `<div class="placa-topo"><div>
      <h2>${esc(s.placa || "Sem placa de vídeo dedicada")}</h2>
      <p>${esc(s.motivo)}</p></div>
      <span class="etiqueta brasa">Sugerido: ${esc(NOME_NIVEL[s.nivel])}</span></div>
    <div class="etiquetas" style="margin-top:12px">${etiquetas}</div>
    <dl class="fatos">
      <div><dt>Memória de vídeo</dt><dd>${gbDeMb(s.vram_mb)}</dd></div>
      <div><dt>Livre agora</dt><dd>${gbDeMb(g && g.vram_livre_mb)}</dd></div>
      <div><dt>Driver</dt><dd>${esc((g && g.versao_driver) || "—")}</dd></div>
      <div><dt>RAM</dt><dd>${gbDeMb(deteccao.ram_total_mb)}</dd></div>
      <div><dt>Sistema</dt><dd>${esc(deteccao.sistema.nome)}</dd></div>
    </dl>
    ${(s.avisos || []).map((a) => `<p class="nota">${esc(a)}</p>`).join("")}`);
  $("nivel-maquina").value = (info && info.nivel_da_maquina) || "auto";
  const emUso = niveis.nivel_em_uso;
  const cab = `<thead><tr><th>Função</th>${niveis.tabela.map((l) => `<th class="${l.nivel === emUso ? "em-uso" : ""}">${esc(l.nome)}<small>${esc(l.faixa)}</small></th>`).join("")}</tr></thead>`;
  const linhas = niveis.funcoes.map((f) => `<tr><th>${esc(f.nome)}</th>${niveis.tabela.map((l) => {
    const e = l.funcoes.find((x) => x.funcao === f.id);
    const cls = l.nivel === emUso ? "em-uso" : "";
    if (!e || !e.modelo) {
      const porque = e && e.recusados.length ? e.recusados.map((r) => r.motivo).join("\n") : "Sem modelo neste nível.";
      return `<td class="${cls}"><span class="sem" title="${esc(porque)}">—</span></td>`;
    }
    const desceu = e.nivel_usado && e.nivel_usado !== l.nivel ? `<span class="desceu">opção do ${esc(NOME_NIVEL[e.nivel_usado])}</span>` : "";
    return `<td class="${cls}">${esc(e.modelo.nome)}${desceu}</td>`;
  }).join("")}</tr>`).join("");
  pinta($("tabela-niveis"), cab + "<tbody>" + linhas + "</tbody>");
}
$("nivel-maquina").addEventListener("change", async (e) => {
  try { await api("POST", "/janela/ajustes", { nivel: e.target.value }); mensagem("Nível desta máquina salvo."); pintarPlaca(); }
  catch (err) { mensagem(err.message, "erro"); }
});

// ---------- Licenças ----------
const SITUACAO = {
  liberado: ["ok", "Pode vender"],
  bloqueado: ["erro", "Bloqueado"],
  precisa_aceite: ["alerta", "Precisa do seu aceite"],
  precisa_receita: ["alerta", "Informe a receita"],
};
async function pintarLicencas() {
  await carregarBase();
  [modelos, info] = await Promise.all([ferramenta("list_models"), api("GET", "/janela/info").catch(() => null)]);
  // Pendências do projeto aberto
  const atual = estado && estado.projeto_atual;
  $("grupo-pendencias").hidden = !atual;
  if (atual) {
    const p = await ferramenta("check_licenses");
    $("pendencias-titulo").textContent = `Antes de vender: ${atual.nome}`;
    const itens = [
      ...p.bloqueiam_venda.map((x) => ["erro", x.arquivo, `Bloqueia a venda (${x.modelo}). ${x.motivo}`]),
      ...p.precisam_atencao.map((x) => ["alerta", x.arquivo, `Precisa de atenção (${x.modelo}). ${x.motivo}`]),
      ...p.sem_recibo.map((a) => ["alerta", a, "Sem recibo de licença."]),
      ...p.alterados.map((a) => ["", a, "Mudou depois do recibo (só aviso)."]),
      ...p.sumidos.map((a) => ["", a, "Tem recibo, mas o arquivo sumiu (só aviso)."]),
    ];
    pinta($("pendencias"), itens.length ? itens.map(([c, a, t]) =>
      `<div class="linha compacta"><span class="icone-estado ${c}"></span><div><div class="titulo mono">${esc(a)}</div><div class="sub">${esc(t)}</div></div><span></span></div>`).join("")
      : `<div class="vazio"><strong>Tudo certo.</strong>Todos os assets têm recibo e licença que deixa vender.</div>`);
  }
  // Decisões do estúdio
  const est = (info && info.estudio) || { receita_anual_usd: null, licencas_aceitas: [] };
  const grupos = (info && info.grupos_de_aceite) || modelos.grupos_de_aceite || {};
  const podeEditar = !!info;
  pinta($("estudio"), `
    <div class="linha"><span></span>
      <div><div class="titulo">Receita anual do estúdio (US$)</div><div class="sub">Algumas licenças são grátis só até um teto de receita (ex.: Stable Audio Open, até US$ 1 milhão).</div></div>
      <div class="lado"><input type="number" min="0" step="1000" class="curto" id="receita" value="${est.receita_anual_usd ?? ""}" placeholder="não informada" ${podeEditar ? "" : "disabled"}></div></div>
    ${Object.entries(grupos).map(([id, g]) => `
    <div class="linha"><span></span>
      <div><div class="titulo">${esc(g.nome)}</div><div class="texto-licenca">${esc(g.texto)}</div></div>
      <div class="lado"><label class="interruptor-rotulo">Aceito<input type="checkbox" class="interruptor" data-aceite="${esc(id)}" ${est.licencas_aceitas.includes(id) ? "checked" : ""} ${podeEditar ? "" : "disabled"}></label></div></div>`).join("")}`);
  // Catálogo
  const filtro = $("filtro-funcao");
  if (filtro.options.length === 1) for (const f of modelos.funcoes) filtro.add(new Option(f.nome, f.id));
  pintarCatalogo();
}
function pintarCatalogo() {
  if (!modelos) return;
  const so = $("filtro-funcao").value;
  const html = modelos.funcoes.filter((f) => !so || f.id === so).map((f) => {
    const ms = modelos.modelos.filter((m) => m.funcao === f.id);
    if (!ms.length) return "";
    return `<div class="funcao-titulo">${esc(f.nome)}</div>` + ms.map((m) => {
      const [cor, rotulo] = SITUACAO[m.situacao.situacao] || ["", m.situacao.situacao];
      const extra = [m.requer_cuda ? "precisa de CUDA" : "", m.onde === "api" ? "serviço pago (modo turbo)" : ""].filter(Boolean).join(" · ");
      const motivo = m.situacao.motivo || m.situacao.texto || (m.obrigacoes || []).join(" ") || m.nota || "";
      return `<div class="linha compacta modelo-linha"><span class="icone-estado ${cor}"></span>
        <div><div class="titulo">${esc(m.nome)}</div>
          <div class="sub"><a href="#" data-link="${esc(m.url_licenca)}">${esc(m.licenca)}</a>${extra ? " · " + esc(extra) : ""}</div>
          ${motivo ? `<div class="texto-licenca">${esc(motivo)}</div>` : ""}</div>
        <div class="lado"><span class="etiqueta ${cor}">${rotulo}</span></div></div>`;
    }).join("");
  }).join("");
  pinta($("catalogo"), html);
}
$("filtro-funcao").addEventListener("change", pintarCatalogo);
async function salvarEstudio() {
  const receita = $("receita").value.trim();
  const aceitas = [...document.querySelectorAll("[data-aceite]")].filter((c) => c.checked).map((c) => c.dataset.aceite);
  try {
    await api("POST", "/janela/estudio", { receita_anual_usd: receita === "" ? null : Math.max(0, Math.floor(Number(receita))), licencas_aceitas: aceitas });
    mensagem("Decisões do estúdio salvas.");
    pintarLicencas();
  } catch (err) { mensagem(err.message, "erro"); }
}
$("estudio").addEventListener("change", (e) => { if (e.target.matches("#receita, [data-aceite]")) salvarEstudio(); });
$("exportar-creditos").addEventListener("click", async () => {
  try {
    const r = await ferramenta("export_credits");
    mensagem(`Relatório salvo em ${r.arquivo}.`);
  } catch (err) { mensagem(err.message, "erro"); }
});

// ---------- Agentes ----------
async function pintarAgentes() {
  if (!info) info = await api("GET", "/janela/info").catch(() => null);
  const mcp = (estado && estado.endereco_mcp) || BASE_DEV + "/mcp";
  const c = (info && info.comandos) || {
    claude_http: `claude mcp add --transport http fornalha ${mcp}`,
    claude_stdio: `claude mcp add fornalha -- fornalha --mcp`,
    codex: `codex mcp add fornalha -- fornalha --mcp`,
  };
  const blocos = [
    ["Claude Code (com a Fornalha aberta)", "Recomendado: usa a Fornalha que está rodando, perto do relógio.", c.claude_http],
    ["Claude Code (mesmo com o app fechado)", "O Claude Code abre a Fornalha sozinho, sem janela, quando precisar.", c.claude_stdio],
    ["Codex", "O mesmo servidor MCP, pelo Codex.", c.codex],
    ["API local", "Para scripts e outros programas: lista as ferramentas; chame com POST /fornalha/ferramentas/{nome}.", mcp.replace("/mcp", "/fornalha/ferramentas")],
  ];
  pinta($("comandos"), blocos.map(([t, s, cmd]) => `<div class="comando"><div class="comando-topo"><div><strong>${esc(t)}</strong><small>${esc(s)}</small></div>
    <button class="botao pequeno" data-copiar="${esc(cmd)}">Copiar</button></div><pre>${esc(cmd)}</pre></div>`).join(""));
  const lista = await api("GET", "/fornalha/ferramentas").catch(() => ({ ferramentas: [] }));
  pinta($("ferramentas"), lista.ferramentas.map((f) => `<div class="linha compacta"><span class="icone-estado ${f.so_leitura ? "" : "ok"}"></span>
    <div><div class="titulo mono">${esc(f.nome)}</div><div class="sub">${esc(f.titulo)}</div></div><span></span></div>`).join(""));
}

// ---------- Ajustes ----------
function pintarAjustes() {
  api("GET", "/janela/info").then((i) => {
    info = i;
    $("estilo-janela").value = i.estilo_janela || "auto";
    $("ajuste-pasta").textContent = i.pasta_projetos;
    $("versao").textContent = `Fornalha ${i.versao} · Fase ${i.fase} do plano · ${i.exe}`;
  }).catch(() => { $("versao").textContent = "Fora do aplicativo (modo navegador)."; });
}
$("estilo-janela").addEventListener("change", async (e) => {
  try {
    await api("POST", "/janela/ajustes", { estilo_janela: e.target.value });
    if (window.montarBotoesJanela) window.montarBotoesJanela(e.target.value);
  } catch (err) { mensagem(err.message, "erro"); }
});
$("ajuste-escolher-pasta").addEventListener("click", async () => {
  const p = await escolherPasta("Pasta dos projetos novos");
  if (!p) return;
  try { await api("POST", "/janela/ajustes", { pasta_projetos: p }); $("novo-pasta").value = p; pintarAjustes(); mensagem("Pasta salva."); }
  catch (err) { mensagem(err.message, "erro"); }
});
$("abrir-registros").addEventListener("click", () => abrirPasta("registros"));

// ---------- começo ----------
irPara("inicio");
document.addEventListener("visibilitychange", () => { if (!document.hidden) carregarSecao(secao); });
