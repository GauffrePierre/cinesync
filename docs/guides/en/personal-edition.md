# Getting started: personal edition

> On first start, an **assistant** walks you through a few screens: language and country, platforms, cinemas, accounts (Plex, Jellyfin, Trakt, Letterboxd) and notifications. You can skip it and run it again later (Profile → Appearance → Run the setup assistant again).

For one person: no accounts, no mandatory sign-in. About 10 minutes.

> Requirement: SynCiné installed with `CINESYNC_MODE=personal` in `.env` (see the [README](../../README.en.md#installation)).

## 1. First launch

Open SynCiné's address in your browser: the app shows up straight away, with no sign-in screen.

## 2. Protect access (recommended)

Until a password is set, **anyone who opens the address gets into your SynCiné**. If it can be reached from outside your home, protect it:

1. **Profile → My account → Protect with a password**.
2. Choose a **username** and a **password** (at least 8 characters; 12+ if SynCiné is on the Internet).
3. Copy the **security code** SynCiné has just written to the server logs (container logs; on Unraid: container icon → **Logs**), on a line reading “Protection de l'accès : code pour définir le mot de passe”. Access is still open at this point, so the code proves it is you, who controls the server, and not a visitor. It is valid for 30 minutes; reopen the dialog to get a new one.
4. This device stays signed in; other devices will show the **Sign in** screen.

You can go back to open access later: **My account → Password → Remove password protection**.

## 3. The TMDB key (required)

Without it, SynCiné shows demo data.

1. Create a free account on [themoviedb.org](https://www.themoviedb.org/signup), then go to **Settings → API** and request a key (personal use).
2. In SynCiné: **Profile → Connections → TMDB**, paste the key (v3) or read access token (v4), then **Test connection**.

## 4. Your country, services and cinemas

- **Region & Language**: your **country** (availability and releases), the **content language** (titles, synopses) and the **interface language** (French, English, Italian, German or Spanish).
- **Platforms**: tick your subscriptions. They drive badges, filters, the "Watch on…" button and notifications.
- **Cinemas**: search for the cinemas you go to (France, Germany, Spain, Turkey, Mexico). Their showtimes appear in **Upcoming → Cinema releases** and in Discover.

## 5. Your services (optional)

Add them from **Profile → Connections** with the **+** button ("Add a service"):

| Service | What it brings | How |
|---|---|---|
| **Trakt** | Watchlist, history, ratings, recommendations | Create an app at [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications/new) (redirect URI `urn:ietf:wg:oauth:2.0:oob`), paste its **Client ID**, then **Sign in with Trakt** and enter the code at trakt.tv/activate |
| **Letterboxd** | Your film diary | Your Letterboxd username (public profile) |
| **JustWatch** | Direct links to each service, new arrivals, charts | Tick **Enable JustWatch** (unofficial source) |
| **Plex** | Your library, "Play on Plex", history | **Sign in with Plex**, enter the code at plex.tv/link; SynCiné finds your server |
| **Jellyfin / Emby** | Your library, "Play", watched titles | Server address (local IP, not `localhost` under Docker) and API key (Jellyfin: Dashboard → API Keys), then **Link the server** and **Link my account** for your watched titles |
| **Seerr** | Request titles for your library | Seerr address + API key (Seerr → Settings → General) |

## 6. Sync your lists

**Profile → Sync**:

1. **Sync now** gathers your watchlist, watched titles and ratings from Trakt, Plex and Letterboxd.
2. To keep Trakt and Plex identical automatically, tick **Automatic Trakt ⇄ Plex sync**: a preview shows what will change before it's turned on.

## 7. The rest, at your own pace

- **Notifications**: a watchlist title lands on one of your services, a new episode is out, a service is down.
- **Film News**: pick your sources (**Sources** button); you can paste the address of any website or YouTube channel.
- **Swipe mode**, **Tonight**, **Statistics**: all in the menu.

## 8. Install the app on your phone

Installing requires an **HTTPS** address (see the [README](../../README.en.md#https-access-and-mobile-app)).

- **iPhone / iPad**: Safari → **Share → Add to Home Screen**.
- **Android**: Chrome offers to install it (or menu ⋮ → **Install app**).

---
Something wrong? Open an issue on GitHub. For a security issue, see [SECURITY.md](../../SECURITY.md).
