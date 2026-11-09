"""Parcours principaux dans un vrai navigateur : pages, Profil et administration, compte membre, téléphone."""

import re

from playwright.sync_api import expect

from conftest import ADMIN, open_page

# Page -> titre principal attendu, ou (pour les pages sans titre) un texte qui lui est propre
PAGES = [("/", "text", "Données de démonstration"), ("/upcoming", "h1", "À venir"), ("/news", "h1", "Actu Ciné"),
         ("/tonight", "h1", "Pour ce soir"), ("/watchlist", "h1", "Watchlist"), ("/stats", "h1", "Statistiques"),
         ("/swipe", "text", "Raccourcis"), ("/profile", "h1", "Profil et paramètres")]


def test_main_pages_load_without_errors(admin_page):
    for path, how, text in PAGES:
        admin_page.goto(path)
        if how == "h1":
            expect(admin_page.get_by_role("heading", level=1).first).to_contain_text(text)
        else:
            expect(admin_page.get_by_text(text).first).to_be_visible()
        assert admin_page.errors == [], f"{path} : {admin_page.errors}"


def test_profile_tabs_search_backup_and_language(admin_page, server):
    page = admin_page
    page.goto("/profile")
    tabs = page.get_by_role("tablist").first
    for name in ("Compte", "Connexions", "Préférences", "Admin"):
        expect(tabs.get_by_role("tab", name=name)).to_be_visible()
    # Onglet Admin : sous-onglets, sauvegarde immédiate
    tabs.get_by_role("tab", name="Admin").click()
    expect(page).to_have_url(re.compile(r"tab=admin"))
    page.get_by_role("tab", name="Sauvegardes").click()
    page.get_by_role("button", name="Sauvegarder maintenant").click()
    expect(page.get_by_text(re.compile(r"syncine-\d{8}-\d{6}\.db\.gz"))).to_be_visible()
    # L'ancienne adresse de l'espace admin mène au même endroit
    page.goto("/admin?tab=users")
    expect(page).to_have_url(re.compile(r"tab=admin&section=users"))
    # La recherche parcourt tous les onglets
    page.goto("/profile")
    page.get_by_placeholder("Rechercher un réglage…").fill("cinémas")
    expect(page.get_by_role("heading", name="Cinémas")).to_be_visible()
    # Langue de l'interface : anglais puis retour au français
    page.goto("/profile?tab=prefs")
    page.get_by_label("Langue de l'interface").select_option("en")
    expect(page.get_by_role("heading", level=1)).to_have_text("Profile & settings")
    page.get_by_label("Interface language").select_option("fr")
    expect(page.get_by_role("heading", level=1)).to_have_text("Profil et paramètres")
    assert page.errors == []


def test_member_signs_in_and_has_no_admin_access(admin_page, browser, server):
    temp, final = "temp-pass-4567", "member-pass-8910"
    r = admin_page.request.post("/api/admin/users", data={"username": "alice", "password": temp, "display_name": "Alice"},
                                headers={"Origin": server["base"]})
    assert r.ok, r.text()
    page = open_page(browser, server)
    page.goto("/")
    page.get_by_label("Identifiant").fill("alice")
    page.locator("input[type=password]").fill(temp)
    page.get_by_role("button", name="Se connecter").click()
    # Mot de passe provisoire : à changer dès la première connexion
    expect(page.get_by_text("Choisis ton mot de passe")).to_be_visible()
    if page.locator("input[autocomplete=current-password]").count():
        page.locator("input[autocomplete=current-password]").fill(temp)
    page.locator("input[autocomplete=new-password]").nth(0).fill(final)
    page.locator("input[autocomplete=new-password]").nth(1).fill(final)
    page.get_by_role("button", name="Continuer").click()
    page.get_by_role("button", name="Passer l’assistant").click()
    page.goto("/profile")
    tabs = page.get_by_role("tablist").first
    expect(tabs.get_by_role("tab", name="Préférences")).to_be_visible()
    expect(tabs.get_by_role("tab", name="Admin")).to_have_count(0)
    assert page.request.get("/api/admin/users").status == 403
    assert page.errors == []
    page.context.close()


def test_phone_layout(pw, browser, server, admin_state):
    page = open_page(browser, server, state=str(admin_state), device=pw.devices["iPhone 13"])
    for path in ("/", "/tonight", "/watchlist", "/profile", "/profile?tab=admin"):
        page.goto(path)
        expect(page.locator("nav").last.get_by_text("Découvrir")).to_be_visible()  # barre du bas
        page.wait_for_timeout(300)
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"{path} : la page déborde de {overflow} px en largeur"
    # Les quatre onglets du Profil tiennent sur la largeur
    page.goto("/profile")
    admin_tab = page.get_by_role("tablist").first.get_by_role("tab", name="Admin")
    box = admin_tab.bounding_box()
    assert box and box["x"] + box["width"] <= page.viewport_size["width"]
    assert page.errors == []
    page.context.close()
