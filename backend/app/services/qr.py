"""QR codes en SVG, générés sur le serveur (le contenu ne part chez aucun service tiers)."""

import io


def svg(data: str) -> str:
    """QR code noir sur fond blanc, prêt à afficher en <img src="data:image/svg+xml,…">."""
    import segno

    out = io.BytesIO()
    segno.make(data, error="m").save(out, kind="svg", scale=5, border=2, dark="#000", light="#fff", xmldecl=False, svgns=True)
    return out.getvalue().decode()
