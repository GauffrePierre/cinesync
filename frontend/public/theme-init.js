// Applique le thème enregistré avant le premier rendu (évite un flash clair / sombre)
try {
  var t = JSON.parse(localStorage.getItem('cinesync-settings') || '{}').state?.theme
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t
} catch (e) {}
