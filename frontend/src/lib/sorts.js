// Options de tri communes (Bibliothèque, Watchlist, Pour ce soir). Libellés en français, traduits à l'affichage.
export const SORT_OPTIONS = [
  { value: 'added', label: 'Date d’ajout' },
  { value: 'release', label: 'Date de sortie' },
  { value: 'rating', label: 'Note globale' },
  { value: 'critics', label: 'Note de la critique' },
  { value: 'audience', label: 'Note du public' },
  { value: 'personal', label: 'Ma note' },
  { value: 'year', label: 'Année' },
  { value: 'title', label: 'Titre (A → Z)' },
]

// Pour ce soir : par défaut l'ordre de pertinence ; « ma note » n'a pas de sens pour des titres pas encore vus
export const TONIGHT_SORTS = [{ value: 'relevance', label: 'Pertinence' }, ...SORT_OPTIONS.filter((s) => s.value !== 'personal')]
