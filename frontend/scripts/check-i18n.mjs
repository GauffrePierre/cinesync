// Vérifie les traductions : clés t('…') sans entrée anglaise, et clés définies différemment dans deux dictionnaires.
// Usage : npm run check:i18n (dans frontend/) — aussi lancé par la CI
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
const src = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src')
const dir = path.join(src, 'i18n', 'en')
const names = fs.readdirSync(dir).filter((f) => f.endsWith('.js') && f !== 'index.js').map((f) => f.slice(0, -3))
const all = {}
let problems = 0
for (const n of names) {
  const d = (await import(path.join(dir, `${n}.js`))).default
  for (const [k, v] of Object.entries(d)) {
    if (all[k] && all[k].v !== v) {
      console.log(`CONFLIT ${JSON.stringify(k)} : ${all[k].n}=${JSON.stringify(all[k].v)} / ${n}=${JSON.stringify(v)}`)
      problems++
    }
    all[k] = { n, v }
  }
}
const files = []
const walk = (p) => fs.readdirSync(p, { withFileTypes: true }).forEach((e) => {
  const f = path.join(p, e.name)
  if (e.isDirectory()) e.name !== 'i18n' && walk(f)
  else if (/\.(jsx?|mjs)$/.test(e.name)) files.push(f)
})
walk(src)
const re = /\b(?:t|tNow|tx)\(\s*(['"])((?:\\.|(?!\1).)*)\1/g
for (const f of files) {
  const s = fs.readFileSync(f, 'utf8')
  let m
  while ((m = re.exec(s))) {
    const k = m[2].replace(/\\'/g, "'").replace(/\\"/g, '"')
    if (!(k in all) && /[a-zà-ÿ]/i.test(k)) {
      console.log(`MANQUANT ${path.relative(src, f)} ${JSON.stringify(k)}`)
      problems++
    }
  }
}
// Autres langues : mêmes clés et mêmes variables que l'anglais
for (const lang of ['it', 'de', 'es']) {
  const ldir = path.join(path.dirname(dir), lang)
  if (!fs.existsSync(ldir)) { console.log(`LANGUE ABSENTE ${lang}`); problems++; continue }
  const d = {}
  for (const n of names) Object.assign(d, (await import(path.join(ldir, n + '.js'))).default)
  for (const k of Object.keys(all)) {
    if (!(k in d)) { console.log(`MANQUANT (${lang}) ${JSON.stringify(k)}`); problems++; continue }
    const ph = (x) => (x.match(/\{\w+\}/g) || []).sort().join()
    if (ph(all[k].v) !== ph(d[k])) { console.log(`VARIABLES (${lang}) ${JSON.stringify(k)}`); problems++ }
  }
  for (const k of Object.keys(d)) if (!(k in all)) { console.log(`EN TROP (${lang}) ${JSON.stringify(k)}`); problems++ }
}
console.log(`${Object.keys(all).length} clés, ${problems} problème(s)`)
process.exit(problems ? 1 : 0)
