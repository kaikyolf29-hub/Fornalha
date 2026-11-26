// Estúdio 3D da estação Movimento: a pessoa (e a IA, pelas mesmas ferramentas) vê o personagem se mexer,
// com os ossos reprovados em vermelho, o rastro da mão, do pé e da ponta da arma, chão em quadrados de
// 25 cm, e mexe num osso num quadro. O ajuste aparece aqui igual ao que o Blender grava (edit_motion):
// o giro vale inteiro no quadro e some em cosseno nos quadros vizinhos.
// Leve em repouso: só desenha quando algo muda (sem laço parado gastando a placa).
import * as THREE from "./vendor/three/three.module.min.js";
import { OrbitControls } from "./vendor/three/OrbitControls.js";
import { TransformControls } from "./vendor/three/TransformControls.js";
import { GLTFLoader } from "./vendor/three/GLTFLoader.js";

const F = window.Fornalha;
const FPS = 30;
const el = (id) => document.getElementById(id);
const I = new THREE.Quaternion();
const CORES = { mao_d: 0xff7a1a, mao_e: 0x2aa6ff, pe_d: 0xf2d62a, pe_e: 0x3ee06a, arma: 0xffffff };
const PONTAS = {
  mao_d: ["hand_r", "RightHand", "mixamorigRightHand"], mao_e: ["hand_l", "LeftHand", "mixamorigLeftHand"],
  pe_d: ["foot_r", "RightFoot", "mixamorigRightFoot"], pe_e: ["foot_l", "LeftFoot", "mixamorigLeftFoot"],
};

const e = {
  pronto: false, arquivo: null, raiz: null, mixer: null, clipes: [], clipe: null, acao: null, tempo: 0, tocando: false,
  ossos: [], porNome: {}, malhas: [], armas: [], originais: new Map(), contornos: [], estilo: "material",
  selecionado: null, modo: "girar", edicoes: [], problemas: {}, arrasto: null, pedido: false, ultimo: 0, velocidade: 1,
};

// ---------- palco ----------
function montarPalco() {
  const tela = el("est-tela");
  e.renderer = new THREE.WebGLRenderer({ canvas: tela, antialias: true, powerPreference: "high-performance" });
  e.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  e.renderer.outputColorSpace = THREE.SRGBColorSpace;
  e.renderer.toneMapping = THREE.ACESFilmicToneMapping;
  e.renderer.shadowMap.enabled = true;
  e.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  e.cena = new THREE.Scene();
  e.cena.background = new THREE.Color(0x15120f);
  e.camera = new THREE.PerspectiveCamera(35, 1, 0.02, 200);
  e.camera.position.set(2.2, 1.5, 3.4);
  e.cena.add(new THREE.HemisphereLight(0xfff1e0, 0x2a2520, 1.4));
  const sol = new THREE.DirectionalLight(0xffffff, 2.4);
  sol.position.set(-2.5, 4.5, 3.5);
  sol.castShadow = true;
  sol.shadow.mapSize.set(2048, 2048);
  Object.assign(sol.shadow.camera, { left: -3, right: 3, top: 3, bottom: -3, near: 0.5, far: 20 });
  sol.shadow.bias = -0.0004;
  e.cena.add(sol);
  const contra = new THREE.DirectionalLight(0xd8e4ff, 0.9);
  contra.position.set(3, 2.5, -3);
  e.cena.add(contra);
  // chão: quadrados de 25 cm (o pé parado que muda de quadrado está escorregando)
  e.chao = new THREE.Group();
  const placa = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.MeshStandardMaterial({ color: 0x2b2723, roughness: 0.95 }));
  placa.rotation.x = -Math.PI / 2;
  placa.receiveShadow = true;
  const grade = new THREE.GridHelper(8, 32, 0x8a7a63, 0x4a4239);
  grade.position.y = 0.001;
  e.chao.add(placa, grade);
  e.cena.add(e.chao);
  e.orbita = new OrbitControls(e.camera, tela);
  e.orbita.target.set(0, 1, 0);
  e.orbita.enableDamping = false;
  e.orbita.addEventListener("change", pedirQuadro);
  e.gizmo = new TransformControls(e.camera, tela);
  e.gizmo.setSpace("world");
  e.gizmo.setSize(0.8);
  e.gizmo.addEventListener("change", pedirQuadro);
  e.gizmo.addEventListener("dragging-changed", (ev) => { e.orbita.enabled = !ev.value; ev.value ? comecarArrasto() : terminarArrasto(); });
  e.cena.add(e.gizmo.getHelper ? e.gizmo.getHelper() : e.gizmo);
  e.esqueleto = new THREE.Group();
  e.esqueleto.renderOrder = 10;
  e.cena.add(e.esqueleto);
  e.rastros = new THREE.Group();
  e.cena.add(e.rastros);
  new ResizeObserver(redimensionar).observe(tela.parentElement);
  tela.addEventListener("pointerdown", escolherPeloClique);
  redimensionar();
  e.pronto = true;
}

function redimensionar() {
  const caixa = el("est-tela").parentElement.getBoundingClientRect();
  const w = Math.max(200, Math.floor(caixa.width)), h = Math.max(200, Math.floor(caixa.height));
  e.renderer.setSize(w, h, false);
  e.camera.aspect = w / h;
  e.camera.updateProjectionMatrix();
  pedirQuadro();
}

function pedirQuadro() {
  if (e.pedido) return;
  e.pedido = true;
  requestAnimationFrame(desenhar);
}

function desenhar(agora) {
  e.pedido = false;
  if (e.tocando && e.clipe) {
    const dt = e.ultimo ? Math.min(0.1, (agora - e.ultimo) / 1000) : 0;
    e.tempo = (e.tempo + dt * e.velocidade) % Math.max(e.clipe.duration, 1 / FPS);
    posar();
    pedirQuadro();
  }
  e.ultimo = e.tocando ? agora : 0;
  e.renderer.render(e.cena, e.camera);
}

// ---------- modelo ----------
async function abrir(arquivo, animacao) {
  if (!e.pronto) montarPalco();
  F.calor(true);
  el("est-estado").textContent = "Abrindo o modelo…";
  try {
    const bytes = await F.lerBytes(F.raiz() + "/" + arquivo);
    if (!bytes) throw new Error("Não deu para ler o modelo (é grande demais ou está fora do projeto).");
    const gltf = await new Promise((ok, falha) => new GLTFLoader().parse(bytes, "", ok, falha));
    limpar();
    e.arquivo = arquivo;
    e.raiz = gltf.scene;
    e.cena.add(e.raiz);
    e.malhas = [];
    e.armas = [];
    const vistos = new Set();
    e.raiz.traverse((o) => {
      if (o.isMesh) {
        o.castShadow = true;
        o.frustumCulled = false;
        e.malhas.push(o);
        e.originais.set(o, o.material);
        if (!o.isSkinnedMesh && o.parent && o.parent.isBone) e.armas.push(o);
      }
      if (o.isSkinnedMesh) for (const b of o.skeleton.bones) if (!vistos.has(b)) { vistos.add(b); }
    });
    e.ossos = [...vistos];
    e.porNome = Object.fromEntries(e.ossos.map((b) => [b.name, b]));
    e.mixer = new THREE.AnimationMixer(e.raiz);
    e.clipes = [...gltf.animations].sort((a, b) => a.name.localeCompare(b.name));
    F.pinta(el("est-animacao"), e.clipes.length ? e.clipes.map((c) => `<option value="${F.esc(c.name)}">${F.esc(c.name)} · ${Math.round(c.duration * FPS)} q</option>`).join("") : `<option value="">sem animação</option>`);
    F.pinta(el("est-osso-lista"), `<option value="">— escolha um osso —</option>` + e.ossos.map((b) => `<option>${F.esc(b.name)}</option>`).join(""));
    montarEsqueleto();
    enquadrar();
    aplicarEstilo(e.estilo);
    const alvo = animacao && e.clipes.find((c) => c.name === animacao) ? animacao : (e.clipes.find((c) => c.name === "parado") || e.clipes[0] || {}).name;
    if (alvo) { el("est-animacao").value = alvo; trocarClipe(alvo); }
    el("est-estado").textContent = `${e.ossos.length} ossos · ${e.clipes.length} animações · ${e.armas.length ? e.armas.length + " arma(s) presa(s) na mão" : "sem arma presa"}`;
    el("est-area").hidden = false;
    redimensionar();
  } catch (err) {
    el("est-estado").textContent = "";
    F.mensagem(err.message || String(err), "erro");
  } finally { F.calor(false); }
}

function limpar() {
  if (e.raiz) e.cena.remove(e.raiz);
  e.gizmo.detach();
  e.selecionado = null;
  for (const c of e.contornos) c.parent && c.parent.remove(c);
  e.contornos = [];
  e.originais.clear();
  e.esqueleto.clear();
  e.rastros.clear();
}

function enquadrar() {
  const caixa = new THREE.Box3().setFromObject(e.raiz);
  const alto = Math.max(0.5, caixa.max.y - caixa.min.y);
  const centro = caixa.getCenter(new THREE.Vector3());
  e.altura = alto;
  e.orbita.target.set(centro.x, caixa.min.y + alto * 0.55, centro.z);
  e.camera.position.set(centro.x + alto * 0.95, caixa.min.y + alto * 0.85, centro.z + alto * 1.75);
  e.orbita.update();
}

// ---------- animação e ajustes ----------
function trocarClipe(nome) {
  e.mixer.stopAllAction();
  e.clipe = e.clipes.find((c) => c.name === nome) || null;
  e.tempo = 0;
  if (!e.clipe) return;
  e.acao = e.mixer.clipAction(e.clipe);
  e.acao.play();
  const total = Math.max(1, Math.round(e.clipe.duration * FPS));
  el("est-tempo").max = String(total);
  el("est-tempo").value = "0";
  posar();
  pintarLinhaDoTempo();
  pintarAjustes();
  pintarEsqueleto();
  refazerRastro();
}

function quadroAtual() { return Math.round(e.tempo * FPS); }

function peso(ed, q) {
  const k = ed.suavizar, d = Math.abs(q - ed.quadro);
  if (k === 0) return d < 0.5 ? 1 : 0;
  return d > k ? 0 : 0.5 * (1 + Math.cos((Math.PI * d) / (k + 1)));
}

/** A pose do quadro: a animação e, por cima, os ajustes na ordem em que foram feitos (como o Blender grava). */
function posar(semAjustes) {
  if (!e.mixer || !e.clipe) return;
  // no último quadro o laço voltaria para o primeiro: segura um fio antes do fim
  e.mixer.setTime(Math.min(e.tempo, Math.max(0, e.clipe.duration - 1e-4)));
  e.raiz.updateMatrixWorld(true);
  if (!semAjustes) {
    const q = e.tempo * FPS;
    for (const ed of e.edicoes) {
      if (ed.animacao !== e.clipe.name) continue;
      const w = peso(ed, q);
      if (w <= 1e-4) continue;
      const b = e.porNome[ed.osso];
      if (!b) continue;
      if (ed.giro) {
        const qw = b.getWorldQuaternion(new THREE.Quaternion());
        const dq = new THREE.Quaternion().slerpQuaternions(I, new THREE.Quaternion(...ed.giro), w);
        const pai = b.parent.getWorldQuaternion(new THREE.Quaternion()).invert();
        b.quaternion.copy(pai.multiply(dq.multiply(qw)));
      }
      if (ed.mover) {
        const p = b.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(...ed.mover).multiplyScalar(w));
        b.position.copy(b.parent.worldToLocal(p));
      }
      b.updateMatrixWorld(true);
    }
  }
  atualizarEsqueleto();
  el("est-quadro").textContent = `quadro ${quadroAtual()} de ${el("est-tempo").max}`;
  if (!e.tocando) el("est-tempo").value = String(quadroAtual());
}

function irPara(q) {
  e.tempo = Math.max(0, Math.min(e.clipe ? e.clipe.duration : 0, q / FPS));
  posar();
  pedirQuadro();
}

function tocar(sim) {
  e.tocando = sim;
  el("est-tocar").textContent = sim ? "Pausar" : "Tocar";
  if (sim) e.gizmo.detach();
  else { e.tempo = Math.round(e.tempo * FPS) / FPS; posar(); if (e.selecionado) e.gizmo.attach(e.selecionado); }
  pedirQuadro();
}

function comecarArrasto() {
  if (e.tocando) tocar(false);
  const b = e.selecionado;
  if (!b) return;
  e.arrasto = { osso: b.name, q: b.getWorldQuaternion(new THREE.Quaternion()), p: b.getWorldPosition(new THREE.Vector3()) };
}

function terminarArrasto() {
  const a = e.arrasto;
  e.arrasto = null;
  if (!a || !e.selecionado) return;
  const b = e.selecionado;
  const q = b.getWorldQuaternion(new THREE.Quaternion());
  const dq = q.multiply(a.q.clone().invert()).normalize();
  const dp = b.getWorldPosition(new THREE.Vector3()).sub(a.p);
  registrar(b.name, e.modo === "mover" ? null : dq, e.modo === "mover" ? dp : null);
}

/** Um ajuste: o quanto o osso gira (ou anda) no mundo, no quadro de agora. */
function registrar(osso, dq, dp) {
  const temGiro = dq && 2 * Math.acos(Math.min(1, Math.abs(dq.w))) > 0.002;
  const temMover = dp && dp.length() > 0.0005;
  if (!temGiro && !temMover) return;
  e.edicoes.push({
    animacao: e.clipe.name, osso, quadro: quadroAtual(), suavizar: Number(el("est-suavizar").value),
    giro: temGiro ? [dq.x, dq.y, dq.z, dq.w].map((v) => +v.toFixed(6)) : undefined,
    mover: temMover ? [dp.x, dp.y, dp.z].map((v) => +v.toFixed(5)) : undefined,
  });
  posar();
  pintarAjustes();
  pintarLinhaDoTempo();
  refazerRastro();
  pedirQuadro();
}

/** Giro exato pelos botões (5° em volta de um eixo do mundo): mais preciso que arrastar. */
function girarPorBotao(eixo, graus) {
  const b = e.selecionado;
  if (!b || !e.clipe) return F.mensagem("Escolha um osso (clique na bolinha ou na lista).", "alerta");
  if (e.tocando) tocar(false);
  const v = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] }[eixo];
  registrar(b.name, new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(...v), (graus * Math.PI) / 180), null);
}

function selecionar(b) {
  e.selecionado = b || null;
  if (b && !e.tocando) e.gizmo.attach(b); else e.gizmo.detach();
  el("est-osso-lista").value = b ? b.name : "";
  const raiz = b && !(b.parent && b.parent.isBone);
  el("est-modo-mover").disabled = !raiz;
  if (!raiz && e.modo === "mover") trocarModo("girar");
  const probs = b ? (e.problemas[e.clipe?.name] || []).filter((p) => p.osso === b.name) : [];
  el("est-osso-info").innerHTML = b ? `<strong>${F.esc(b.name)}</strong>${probs.length ? probs.map((p) => `<small class="ruim">q${p.quadro}: ${F.esc(p.explicacao)}</small>`).join("") : "<small>Nada reprovado neste osso.</small>"}` : `<small>Clique numa bolinha do esqueleto ou escolha na lista.</small>`;
  pintarEsqueleto();
  pedirQuadro();
}

function trocarModo(m) {
  e.modo = m;
  e.gizmo.setMode(m === "mover" ? "translate" : "rotate");
  el("est-modo-girar").classList.toggle("ativo", m === "girar");
  el("est-modo-mover").classList.toggle("ativo", m === "mover");
  pedirQuadro();
}

// ---------- esqueleto, rastro e estilo ----------
function montarEsqueleto() {
  e.esqueleto.clear();
  const geo = new THREE.SphereGeometry(1, 12, 8);
  e.bolinhas = e.ossos.map((b) => {
    const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xefe6d8, depthTest: false, transparent: true, opacity: 0.9 }));
    m.renderOrder = 11;
    m.userData.osso = b;
    e.esqueleto.add(m);
    return m;
  });
  const pares = e.ossos.filter((b) => b.parent && b.parent.isBone);
  const pos = new Float32Array(pares.length * 6), cor = new Float32Array(pares.length * 6);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(cor, 3));
  e.varetas = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ vertexColors: true, depthTest: false, transparent: true, opacity: 0.95 }));
  e.varetas.renderOrder = 10;
  e.varetas.userData.pares = pares;
  e.varetas.frustumCulled = false;
  e.esqueleto.add(e.varetas);
  pintarEsqueleto();
}

function ehPano(n) { return /^(saia|capa|cabelo|rabo|mola_)/.test(n); }
function ehDedo(n) { return /(thumb|index|middle|ring|pinky|Thumb|Index|Middle|Ring|Little|ball)/.test(n); }

function pintarEsqueleto() {
  if (!e.varetas) return;
  const ruins = new Set((e.problemas[e.clipe?.name] || []).map((p) => p.osso));
  const H = e.altura || 1.8;
  const c = new THREE.Color();
  for (const m of e.bolinhas) {
    const n = m.userData.osso.name;
    const r = (ehDedo(n) ? 0.006 : ehPano(n) ? 0.005 : 0.011) * H * (m.userData.osso === e.selecionado ? 1.8 : 1);
    m.scale.setScalar(r);
    m.material.color.set(m.userData.osso === e.selecionado ? 0xe0622b : ruins.has(n) ? 0xff2a12 : ehPano(n) ? 0x6f7d92 : 0xefe6d8);
  }
  const cor = e.varetas.geometry.attributes.color;
  e.varetas.userData.pares.forEach((b, i) => {
    c.set(ruins.has(b.name) ? 0xff2a12 : ehPano(b.name) ? 0x56627a : 0xc9a25e);
    cor.setXYZ(2 * i, c.r, c.g, c.b);
    cor.setXYZ(2 * i + 1, c.r, c.g, c.b);
  });
  cor.needsUpdate = true;
  e.esqueleto.visible = el("est-ver-ossos").checked;
}

function atualizarEsqueleto() {
  if (!e.varetas) return;
  const v = new THREE.Vector3();
  for (const m of e.bolinhas) m.userData.osso.getWorldPosition(m.position);
  const pos = e.varetas.geometry.attributes.position;
  e.varetas.userData.pares.forEach((b, i) => {
    b.parent.getWorldPosition(v); pos.setXYZ(2 * i, v.x, v.y, v.z);
    b.getWorldPosition(v); pos.setXYZ(2 * i + 1, v.x, v.y, v.z);
  });
  pos.needsUpdate = true;
}

function escolherPeloClique(ev) {
  if (!e.raiz || !el("est-ver-ossos").checked || e.gizmo.dragging || ev.button !== 0) return;
  const r = ev.target.getBoundingClientRect();
  const ponto = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  const raio = new THREE.Raycaster();
  raio.setFromCamera(ponto, e.camera);
  const achou = raio.intersectObjects(e.bolinhas, false)[0];
  if (achou) selecionar(achou.object.userData.osso);
}

let esperaRastro = null;
function refazerRastro() {
  clearTimeout(esperaRastro);
  esperaRastro = setTimeout(() => {
    e.rastros.clear();
    if (!e.clipe || !el("est-ver-rastro").checked) return pedirQuadro();
    const t0 = e.tempo;
    const alvos = Object.entries(PONTAS).map(([k, nomes]) => [k, nomes.map((n) => e.porNome[n]).find(Boolean)]).filter(([, b]) => b);
    const pontas = e.armas.map((a) => {
      const p = a.geometry.attributes.position;
      let melhor = 0, idx = 0;
      for (let i = 0; i < p.count; i++) { const d = p.getX(i) ** 2 + p.getY(i) ** 2 + p.getZ(i) ** 2; if (d > melhor) { melhor = d; idx = i; } }
      return [a, new THREE.Vector3(p.getX(idx), p.getY(idx), p.getZ(idx))];
    });
    const linhas = Object.fromEntries([...alvos.map(([k]) => [k, []]), ...pontas.map((_, i) => ["arma" + i, []])]);
    const total = Math.max(1, Math.round(e.clipe.duration * FPS));
    for (let q = 0; q <= total; q++) {
      e.tempo = q / FPS;
      posar();
      for (const [k, b] of alvos) {
        const p = b.getWorldPosition(new THREE.Vector3());
        if (k.startsWith("mao") && b.children[0] && b.children[0].isBone) p.lerp(b.children[0].getWorldPosition(new THREE.Vector3()), 0.5);
        linhas[k].push(p);
      }
      pontas.forEach(([a, local], i) => { a.updateWorldMatrix(true, false); linhas["arma" + i].push(local.clone().applyMatrix4(a.matrixWorld)); });
    }
    e.tempo = t0;
    posar();
    for (const [k, pts] of Object.entries(linhas)) {
      const linha = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: CORES[k.startsWith("arma") ? "arma" : k], depthTest: false, transparent: true, opacity: 0.9 }));
      linha.renderOrder = 9;
      linha.frustumCulled = false;
      e.rastros.add(linha);
    }
    pedirQuadro();
  }, 120);
}

function aplicarEstilo(estilo) {
  e.estilo = estilo;
  for (const c of e.contornos) c.parent && c.parent.remove(c);
  e.contornos = [];
  const degraus = new THREE.DataTexture(new Uint8Array([90, 90, 90, 255, 255, 255, 255, 255]), 2, 1);
  degraus.minFilter = degraus.magFilter = THREE.NearestFilter;
  degraus.needsUpdate = true;
  for (const m of e.malhas) {
    const orig = e.originais.get(m);
    const lista = Array.isArray(orig) ? orig : [orig];
    const novos = lista.map((o) => {
      if (estilo === "material") return o;
      const alfa = { transparent: o.transparent, alphaTest: o.alphaTest, side: o.side };
      if (estilo === "barro") return new THREE.MeshStandardMaterial({ color: e.armas.includes(m) ? 0x707276 : 0x9a948c, roughness: 0.68, map: o.alphaTest > 0 || o.transparent ? o.map : null, ...alfa });
      return new THREE.MeshToonMaterial({ color: o.color ? o.color.clone() : new THREE.Color(0xffffff), map: o.map || null, gradientMap: degraus, ...alfa });
    });
    m.material = Array.isArray(orig) ? novos : novos[0];
    if (estilo === "anime" && m.isSkinnedMesh && !(novos[0].alphaTest > 0)) {
      const casco = new THREE.SkinnedMesh(m.geometry, contornoMaterial((e.altura || 1.8) * 0.004));
      casco.bind(m.skeleton, m.bindMatrix);
      casco.frustumCulled = false;
      m.parent.add(casco);
      casco.position.copy(m.position); casco.quaternion.copy(m.quaternion); casco.scale.copy(m.scale);
      e.contornos.push(casco);
    }
  }
  for (const b of document.querySelectorAll("[data-est-estilo]")) b.classList.toggle("ativo", b.dataset.estEstilo === estilo);
  pedirQuadro();
}

function contornoMaterial(espessura) {
  const m = new THREE.MeshBasicMaterial({ color: 0x080608, side: THREE.BackSide });
  m.onBeforeCompile = (s) => {
    s.vertexShader = s.vertexShader.replace("#include <skinning_vertex>", `#include <skinning_vertex>\n  transformed += normalize( objectNormal ) * ${espessura.toFixed(5)};`);
  };
  return m;
}

// ---------- painéis ----------
function pintarLinhaDoTempo() {
  const total = Math.max(1, Number(el("est-tempo").max));
  const probs = e.problemas[e.clipe?.name] || [];
  const eds = e.edicoes.filter((x) => x.animacao === e.clipe?.name);
  el("est-marcas").innerHTML = probs.map((p) => `<button class="marca ruim" style="left:${(100 * p.quadro) / total}%" data-q="${p.quadro}" data-osso="${F.esc(p.osso)}" title="q${p.quadro} · ${F.esc(p.explicacao)}"></button>`).join("")
    + eds.map((x) => `<button class="marca ajuste" style="left:${(100 * x.quadro) / total}%" data-q="${x.quadro}" data-osso="${F.esc(x.osso)}" title="ajuste em ${F.esc(x.osso)} no quadro ${x.quadro}"></button>`).join("");
}

function pintarAjustes() {
  const eds = e.edicoes.filter((x) => x.animacao === e.clipe?.name);
  el("est-ajustes").innerHTML = eds.length ? eds.map((x) => {
    const graus = x.giro ? (2 * Math.acos(Math.min(1, Math.abs(x.giro[3]))) * 180) / Math.PI : 0;
    return `<div class="item"><div><strong>${F.esc(x.osso)}</strong><small>quadro ${x.quadro} · ${x.giro ? `gira ${graus.toFixed(1).replace(".", ",")}°` : ""}${x.mover ? ` anda ${(Math.hypot(...x.mover) * 100).toFixed(1).replace(".", ",")} cm` : ""} · espalha ±${x.suavizar}</small></div></div>`;
  }).join("") : `<p class="vazio">Nenhum ajuste ainda. Pare num quadro, escolha um osso e gire.</p>`;
  el("est-salvar").disabled = el("est-salvar-como").disabled = !eds.length;
  el("est-desfazer").disabled = !eds.length;
}

async function salvar(comoNova) {
  const eds = e.edicoes.filter((x) => x.animacao === e.clipe.name);
  if (!eds.length) return;
  let salvar_como;
  if (comoNova) {
    salvar_como = (el("est-novo-nome").value || "").trim() || `${e.clipe.name}_ajustado`;
    if (!/^[\p{L}\p{N}_]+$/u.test(salvar_como)) return F.mensagem("O nome da animação nova: só letras, números e _.", "alerta");
  }
  const botao = comoNova ? el("est-salvar-como") : el("est-salvar");
  const texto = botao.textContent;
  botao.disabled = true; botao.textContent = "Gravando no Blender…"; F.calor(true);
  try {
    const r = await F.ferramenta("edit_motion", {
      arquivo: e.arquivo, animacao: e.clipe.name, salvar_como,
      edicoes: eds.map(({ osso, quadro, giro, mover, suavizar }) => ({ osso, quadro, giro, mover, suavizar })),
    });
    e.edicoes = e.edicoes.filter((x) => x.animacao !== e.clipe.name);
    e.problemas[r.animacao] = (r.conferencia && r.conferencia.problemas) || [];
    await abrir(e.arquivo, r.animacao);
    const ok = r.aprovado_pela_regua;
    el("est-veredito").className = "veredito " + (ok ? "passou" : "falhou");
    el("est-veredito").innerHTML = `<strong>${ok ? "Gravado e sem defeito medido" : "Gravado, mas a régua reprovou"}</strong><span>${F.esc(r.animacao)}: ${ok ? "olhe tocando e em quadros grandes antes de dar por pronto." : e.problemas[r.animacao].slice(0, 3).map((p) => F.esc(p.explicacao)).join(" · ")}</span>`;
    el("est-veredito").hidden = false;
  } catch (err) { F.mensagem(err.message, "erro"); }
  finally { botao.textContent = texto; F.calor(false); pintarAjustes(); }
}

async function conferirAqui() {
  if (!e.clipe) return;
  const b = el("est-conferir"), texto = b.textContent;
  b.disabled = true; b.textContent = "Medindo…"; F.calor(true);
  try {
    const r = await F.ferramenta("check_motion", { arquivo: e.arquivo, animacoes: [e.clipe.name], imagens: "nenhuma" });
    marcar(r);
    const a = (r.animacoes || [])[0];
    el("est-veredito").className = "veredito " + (a && a.aprovado ? "passou" : "falhou");
    el("est-veredito").innerHTML = `<strong>${a && a.aprovado ? "Sem defeito medido" : "Reprovada pela régua"}</strong><span>${a && a.problemas.length ? a.problemas.slice(0, 3).map((p) => F.esc(p.explicacao)).join(" · ") : "A régua não julga peso, intenção nem estilo: olhe."}</span>`;
    el("est-veredito").hidden = false;
  } catch (err) { F.mensagem(err.message, "erro"); }
  finally { b.disabled = false; b.textContent = texto; F.calor(false); }
}

async function verGrande() {
  if (!e.clipe) return;
  const b = el("est-grande"), texto = b.textContent;
  b.disabled = true; b.textContent = "Renderizando…"; F.calor(true);
  try {
    const r = await F.ferramenta("show_motion", { arquivo: e.arquivo, animacao: e.clipe.name, estilo: e.estilo, angulos: ["tres_quartos", "lado"] });
    const imgs = await Promise.all((r.folhas || []).map((f) => F.dataUrl(f.arquivo)));
    el("est-folhas").innerHTML = (r.folhas || []).map((f, i) => imgs[i] ? `<figure><img src="${imgs[i]}" alt="${F.esc(f.mostra)}"><figcaption>${F.esc(f.mostra)}</figcaption></figure>` : "").join("");
    el("est-folhas").hidden = false;
  } catch (err) { F.mensagem(err.message, "erro"); }
  finally { b.disabled = false; b.textContent = texto; F.calor(false); }
}

/** Resultado do check_motion (desta janela ou da IA): ossos e quadros reprovados por animação. */
function marcar(r) {
  for (const a of r.animacoes || r.clipes || []) e.problemas[a.nome] = a.problemas || [];
  pintarEsqueleto();
  pintarLinhaDoTempo();
  if (e.selecionado) selecionar(e.selecionado);
  pedirQuadro();
}

// ---------- ligações ----------
el("est-abrir").addEventListener("click", () => {
  const arquivo = el("mov-personagem").value;
  if (!arquivo) return F.mensagem("Crie um personagem com esqueleto antes (Forjar).", "alerta");
  abrir(arquivo);
});
el("est-animacao").addEventListener("change", (ev) => { if (e.tocando) tocar(false); trocarClipe(ev.target.value); });
el("est-tempo").addEventListener("input", (ev) => { if (e.tocando) tocar(false); irPara(Number(ev.target.value)); });
el("est-tocar").addEventListener("click", () => tocar(!e.tocando));
el("est-velocidade").addEventListener("change", (ev) => { e.velocidade = Number(ev.target.value); });
el("est-anterior").addEventListener("click", () => { if (e.tocando) tocar(false); irPara(quadroAtual() - 1); });
el("est-proximo").addEventListener("click", () => { if (e.tocando) tocar(false); irPara(quadroAtual() + 1); });
el("est-osso-lista").addEventListener("change", (ev) => selecionar(e.porNome[ev.target.value]));
el("est-modo-girar").addEventListener("click", () => trocarModo("girar"));
el("est-modo-mover").addEventListener("click", () => trocarModo("mover"));
for (const b of document.querySelectorAll("[data-girar]")) b.addEventListener("click", () => girarPorBotao(b.dataset.girar[0], Number(b.dataset.girar.slice(1))));
for (const b of document.querySelectorAll("[data-est-estilo]")) b.addEventListener("click", () => aplicarEstilo(b.dataset.estEstilo));
el("est-ver-ossos").addEventListener("change", () => { pintarEsqueleto(); if (!el("est-ver-ossos").checked) e.gizmo.detach(); pedirQuadro(); });
el("est-ver-rastro").addEventListener("change", refazerRastro);
el("est-ver-chao").addEventListener("change", () => { e.chao.visible = el("est-ver-chao").checked; pedirQuadro(); });
el("est-desfazer").addEventListener("click", () => {
  const i = e.edicoes.map((x) => x.animacao).lastIndexOf(e.clipe?.name);
  if (i >= 0) e.edicoes.splice(i, 1);
  posar(); pintarAjustes(); pintarLinhaDoTempo(); refazerRastro(); pedirQuadro();
});
el("est-salvar").addEventListener("click", () => salvar(false));
el("est-salvar-como").addEventListener("click", () => salvar(true));
el("est-conferir").addEventListener("click", conferirAqui);
el("est-grande").addEventListener("click", verGrande);
el("est-marcas").addEventListener("click", (ev) => {
  const m = ev.target.closest("[data-q]");
  if (!m) return;
  if (e.tocando) tocar(false);
  irPara(Number(m.dataset.q));
  if (e.porNome[m.dataset.osso]) selecionar(e.porNome[m.dataset.osso]);
});
document.addEventListener("keydown", (ev) => {
  if (el("est-area").hidden || el("est-movimento").hidden || ev.target.closest("input, select, textarea")) return;
  if (ev.key === " ") { ev.preventDefault(); tocar(!e.tocando); }
  else if (ev.key === "ArrowLeft") { if (e.tocando) tocar(false); irPara(quadroAtual() - 1); }
  else if (ev.key === "ArrowRight") { if (e.tocando) tocar(false); irPara(quadroAtual() + 1); }
  else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") el("est-desfazer").click();
});

// a janela (e os testes) falam com o estúdio por aqui
window.FornalhaEstudio = {
  abrir, marcar, irPara, selecionar: (n) => selecionar(e.porNome[n]), girar: girarPorBotao, trocarClipe: (n) => { el("est-animacao").value = n; trocarClipe(n); },
  estilo: aplicarEstilo, salvar,
  // medidas para conferir (teste de ponta a ponta: o que o estúdio mostra = o que o Blender grava)
  giroNoMundo: (n) => { const q = e.porNome[n].getWorldQuaternion(new THREE.Quaternion()); return [q.x, q.y, q.z, q.w]; },
  posicaoNaTela: (n) => { const p = e.porNome[n].getWorldPosition(new THREE.Vector3()).project(e.camera); const r = el("est-tela").getBoundingClientRect(); return [r.left + ((p.x + 1) / 2) * r.width, r.top + ((1 - p.y) / 2) * r.height]; },
  estado: () => ({ arquivo: e.arquivo, animacao: e.clipe?.name, quadro: quadroAtual(), ossos: e.ossos.length, armas: e.armas.length, edicoes: e.edicoes.length, selecionado: e.selecionado?.name || null, estilo: e.estilo, rastros: e.rastros.children.length }),
};
