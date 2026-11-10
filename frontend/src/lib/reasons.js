// Raison d'une suggestion (« Parce que tu as aimé … », « Réalisé par … ») dans la langue de l'interface.
// Le serveur envoie une clé et ses variables ; les anciennes réponses n'ont que le texte français.
export function reasonText(item, t) {
  if (!item?.reason) return ''
  if (item.reason_key) return t(item.reason_key, item.reason_params || {})
  const m = item.reason.match(/^Parce que tu as aimé (.+)$/)
  return m ? t('Parce que tu as aimé {title}', { title: m[1] }) : t(item.reason)
}
