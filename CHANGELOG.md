# Changelog

Notable changes in each SynCiné version (named CinéSync up to 1.0.2). Each section also becomes the version's page in
[GitHub Releases](https://github.com/GauffrePierre/syncine/releases). Docker image: `ghcr.io/gauffrepierre/syncine`
(from 1.1.0). The database is migrated automatically when a new version starts.

## 1.4.1 - 2026-11-10

- New SynCiné logo (popcorn and sync arrows): app icon on the home screen and in the browser tab, sign-in screens,
  sidebar and top bar, notifications and README. The name follows the light or dark theme.

## 1.4.0 - 2026-11-10

**Recommendations**
- Suggestions now use every signal you leave, whatever the service: ratings, favourites, watchlist, titles watched on
  Trakt, Plex, Jellyfin, Emby or Letterboxd, swipe choices. Recent tastes weigh more; titles you rated low or dismissed
  push similar ones down.
- Taste profile: directors, series creators, actors and genres that keep appearing in your favourites bring their other
  titles forward, with the reason shown ("Directed by …, whom you like").
- "More like this / Less like this" buttons on every suggestion.
- More variety: at most three suggestions from the same reference, one title per franchise, films and series mixed,
  references that change every day; titles shown again and again without interest make way for others.
- What you can watch on your services or in your library comes first, but at least a third of the list stays discovery;
  poorly rated or obscure titles are left out. Discover gets an "Only what I can watch" filter.
- Tonight learns your habits by day of the week (series or film first) and gets a "Finish up" row for series you have
  almost completed.

**Family (server edition)**
- Members can share their tastes (Profile → Preferences → Sharing, both sides must agree): "The family loved" in
  Discover, filterable by member, shows the favourites of relatives whose tastes are close to yours.
- Tonight with chosen members: pick one or several people; SynCiné shows your common watchlists, then what everyone
  will like and nobody has seen or rejected.
- "With the kids" in Tonight: set the ages of the household's children in Preferences (3-6, 7-10, 11-14); only family
  titles for the youngest child's age are kept, also in group evenings and themed moods.

**Other changes**
- Ratings by half star (4.5 stars).
- New episode notifications: choose each episode, the first or last of the season, or the full season.
- A running series shows its next episode with the day and time in your local time, and the service it comes out on.
- Profile overview counts from SynCiné's own history (all sources); service status dots use the same colours everywhere.

## 1.3.6 - 2026-11-09

- Unraid app store: SynCiné's page now shows six screenshots.

## 1.3.5 - 2026-11-09

- SynCiné is now in the Unraid app store (Community Applications): **Apps** tab, search for **SynCine**.
- Family members can share their watchlist with the administrator (Profile → Preferences). Admin → Requests gets two
  tabs: add requests and watchlists. Only the titles each person can watch neither on their streaming services nor in
  the library they have access to are shown, titles wanted by several people first; nothing else from their account.
- Request notifications ("your request is available on …") and the Seerr description name your media server (Plex,
  Jellyfin or Emby).

## 1.3.4 - 2026-11-09

- Unraid: the template is now named `SynCine` (no accent), because Unraid uses it as the Docker container name. SynCiné
  can then appear in the Community Applications store (Apps tab, search for SynCine).
- Install guide and README: the Apps store comes first on Unraid.

## 1.3.3 - 2026-11-09

**Security (Jellyfin and Emby)**
- Sign in with **Jellyfin Quick Connect**: SynCiné shows a 6-digit code that you approve in your Jellyfin app, so your
  Jellyfin password is never typed into SynCiné. When the server offers Quick Connect, password sign-in is refused. Linking
  your account works the same way. (Emby has no Quick Connect: it keeps the password form.)
- Linking a Jellyfin or Emby account no longer lets anyone sign in with it: signing in to SynCiné with a Jellyfin account
  must be allowed by the administrator (Admin → Accounts). Accounts that were already allowed must be allowed again.
- Linking an account asks for your SynCiné password and sends you a notification.
- Signing in with Jellyfin only contacts the server for allowed accounts, refuses empty passwords and allows at most two
  failures per account per day, so SynCiné cannot be used to test passwords or lock accounts on your server.
- Unlinking revokes the token on the server; changing or removing the server forgets every linked account. Jellyfin
  requests never follow redirects, and the image relay only passes real images.

**Other changes**
- "Added to the server" notifications also work with Jellyfin and Emby (new episodes and watchlist titles).
- Faster first load: pages are loaded on demand; the Resume row loads faster.
- The Docker image installs exact, hash-checked Python dependencies.
- Browser tests run before every image is published; no more warnings in the test suite.


- Every version now has a release page on GitHub with its notes, created automatically; earlier versions got theirs too.
- This changelog.

## 1.3.1 - 2026-11-09

- Jellyfin and Emby: plays of your linked account are imported into the viewing history and show in Statistics. These
  servers keep only the last play of each title: from now on SynCiné also keeps the earlier ones.
- Tonight: the Resume row works with Jellyfin and Emby (started titles with their progress, then the next episode of
  the series you are watching).

## 1.3.0 - 2026-11-09

**Jellyfin and Emby**
- Link a Jellyfin or Emby server: library, "Play" links, badges, watched titles synced both ways.
- Family members sign in with their Jellyfin or Emby account (allowed by the administrator) or link it from their
  profile, and can request titles.
- Server dashboard for Plex, Jellyfin and Emby (current playback, libraries and scans, 30-day statistics), with a
  switcher when several servers are linked.

**Interface**
- Italian, German and Spanish, push notifications included.
- The profile is split into four tabs: Account, Connections, Preferences and Admin. The admin area is now the Admin tab.
- Phone and tablet layout pass; tablets in portrait use the bottom bar.

**Discovery and notifications**
- Film pages show the cinema release date in your country and the first streaming release worldwide.
- Seen / Not seen filter per tab; with the "hide what I've seen" setting on, Discover starts on Not seen.
- Choose when to be told about new episodes and films: when they air, when they reach your platforms, or when they are
  added to Plex. Plex episode notifications are grouped per show.
- Tonight: moods for young children, kids and teens (by age rating), Christmas and Halloween.

**Installation**
- Install guides for Docker Compose, Unraid, TrueNAS, Proxmox and OpenMediaVault; the README installs from the
  published image.
- Unraid template renamed `unraid/syncine.xml` (new installs use `/mnt/user/appdata/syncine`), with the files needed
  for Community Applications.

## 1.2.0 - 2026-11-08

- Push notifications on phones and computers, in each account's language.
- First-run assistant for every new account: language and country, TMDB key, platforms, cinemas, accounts,
  notifications.
- Discover highlights recent releases from your watchlist (film in cinemas or streaming, new season, new episode) over
  a period you choose.
- Seen / Not seen filter on Discover, Watchlist and the library.
- More sort options (release date, date added, overall, critics, audience, year, title, your rating) and more Tonight
  moods; Tonight gets the seen filter and a "Watch again" row.
- Settings search in the profile; the desktop menu can be reordered by drag and drop, with a Requests tab for the
  administrator.

## 1.1.0 - 2026-11-08

- The app is now called SynCiné; the repository and the Docker image are now `syncine`.
- Optional two-factor authentication (authenticator app codes, recovery codes, reset by the administrator).
- Automatic daily database backups, managed from the admin area.
- Discovery setting to stop suggesting titles you have already seen.
- Plex links open the title in the Plex app on iPhone and Android.
- Fixes from an in-depth security review; dependency updates.
- Sync: account-level Plex writes outside the library are no longer repeated.

## 1.0.2 - 2026-11-08

- Accounts without Plex no longer see anything of the administrator's Plex server.

## 1.0.1 - 2026-11-08

- Fixed an app-wide outage: requests waiting on external services held database connections.
- Members see which services the server provides for them.
- Password sign-in everywhere; the app checks for a new version when opened and every hour.
- Custom feeds: protection against DNS rebinding.

## 1.0.0 - 2026-11-08

First public version, as CinéSync.

- Streaming availability (TMDB, JustWatch), local cinema showtimes, releases calendar, film news.
- Watchlist, watched titles, ratings and likes synced with Trakt, Plex and Letterboxd; series tracker by season and
  episode.
- Personal suggestions, swipe mode, Tonight, detailed viewing statistics.
- Server edition with family accounts, an admin area and requests sent to Seerr; personal edition for one person.
- Installable app (PWA) in French and English, with watch links that open the installed apps.
