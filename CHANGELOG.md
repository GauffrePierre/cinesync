# Changelog

Notable changes in each SynCiné version (named CinéSync up to 1.0.2). Each section also becomes the version's page in
[GitHub Releases](https://github.com/GauffrePierre/syncine/releases). Docker image: `ghcr.io/gauffrepierre/syncine`
(from 1.1.0). The database is migrated automatically when a new version starts.

## 1.3.2 - 2026-11-09

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
