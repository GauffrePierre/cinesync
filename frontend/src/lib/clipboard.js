// Copie dans le presse-papiers. navigator.clipboard n'existe qu'en contexte sécurisé (HTTPS, localhost) et peut être
// refusé par le navigateur : repli sur une zone de texte temporaire, qui marche aussi sur une adresse en HTTP simple.
// Renvoie true si le texte a bien été copié (à vérifier avant d'annoncer « copié »).
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* refusé : on essaie l'autre méthode */
  }
  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    // Dans une fenêtre ouverte, la zone doit y être placée (le focus n'en sort pas)
    const host = document.querySelector('[role="dialog"]') || document.body
    host.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    area.remove()
    return ok
  } catch {
    return false
  }
}
