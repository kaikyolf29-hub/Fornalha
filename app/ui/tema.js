// Fornalha 3D: o tema escolhido em Ajustes (guardado neste computador) vale antes da primeira pintura.
// auto: segue o sistema (forja escura ou pergaminho claro); escuro, claro ou pb (preto e branco).
(function () {
  try {
    const t = localStorage.getItem("fornalha.tema");
    if (t && t !== "auto") document.documentElement.dataset.tema = t;
  } catch (_) { /* sem armazenamento: segue o sistema */ }
})();
