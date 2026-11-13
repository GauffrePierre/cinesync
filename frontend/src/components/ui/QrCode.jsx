import { useT } from '../../i18n'

// QR code fabriqué par le serveur (SVG), affiché en image : pas de balisage distant injecté dans la page
export default function QrCode({ svg, className = 'h-48 w-48' }) {
  const t = useT()
  return <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`} alt={t('QR code à scanner')} className={`mx-auto rounded-xl bg-white p-1 ${className}`} />
}
