# Getting started: server edition, administrator

> On first start, an **assistant** walks you through a few screens: language and country, TMDB key, platforms, cinemas, Plex server and accounts, notifications. Every member you add gets one too. You can run it again later (Profile → Appearance → Run the setup assistant again).

You're installing SynCiné for your family: you set up the services once for everyone, then add the accounts. About 20 minutes.

> Requirements: SynCiné installed with `CINESYNC_MODE=server` (the default) and, if your family uses it outside your home, an **HTTPS** address set in `PUBLIC_URL` (see the [README](../../README.en.md#https-access-and-mobile-app)).

## 1. Create the administrator account

On first launch, the **Welcome to SynCiné** screen asks for a **setup code**. It is printed in the container logs:

```bash
docker logs cinesync 2>&1 | grep "code pour créer"
```

On Unraid: container icon → **Logs**. Enter the code, choose your **username** and **password** (12+ characters if SynCiné is on the Internet).

## 2. Server services (shared by everyone)

These are set **once, by you**, in **Profile → Connections**. Members don't see them and can't change them.

| Service | Why | How |
|---|---|---|
| **TMDB** (required) | Title pages, trending, releases, availability | Free key: [themoviedb.org](https://www.themoviedb.org/settings/api) → Settings → API, then **Test connection** |
| **Plex** | Library, "Play on Plex", members signing in with Plex | **Sign in with Plex** → code at plex.tv/link → pick your server |
| **Trakt** (app) | Lets everyone link **their own** Trakt account | Create an app at [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications/new) (redirect URI `urn:ietf:wg:oauth:2.0:oob`) and paste its **Client ID**. Each member then connects their own account |
| **Seerr** | Requests to add titles to your library | Address + API key (Seerr → Settings → General) |
| **JustWatch** | Direct links, new arrivals, charts | **Enable JustWatch** |

Your **personal** settings (country, services, cinemas, your Trakt account, Letterboxd, sync) work as in the [personal edition](personal-edition.md#4-your-country-services-and-cinemas): every member has their own.

## 3. Add family members

**Profile → Admin settings → Family accounts** (or **Admin area → Users**).

### With their Plex account
For people your Plex server is already shared with:

1. The **Plex accounts on the server** section lists them automatically.
2. Click **Allow** next to the person. Optional:
   - **Requests sent straight to Seerr**: their requests skip your queue;
   - **Also allow signing in with a username and password**: a temporary password to pass on.
3. Send them SynCiné's address: they sign in with **Sign in with Plex**. Everyone gets their own watched titles and Plex progress.

### Without a Plex account
These accounts see nothing of your Plex server (library, server name, watched titles) and can't make add requests.

1. **SynCiné accounts → Add**.
2. Choose a **username** and a **temporary password** (**Generate** button), tick the options you need.
3. Pass on the address, username and password: they change the password when they first sign in.

Later, an account's **⋯** menu lets you give or renew a password, make someone administrator, disable or delete the account.

## 4. Family requests

When a member requests a title:
- with **Requests sent straight to Seerr**, it goes to Seerr;
- otherwise it lands in **Admin area → Requests** and you get a notification. You can **send it to Seerr**, **mark it available** or **decline** it: the member is notified.

## 5. Plex dashboard

**Admin area → Plex** (or **Profile → Admin settings → Plex server**): what's playing (who, bandwidth, transcoding), libraries with **Scan**, statistics for the last 30 days.

## 6. Security checklist

- [ ] Long, unique administrator password.
- [ ] **Two-factor authentication** on (Profile → My account → Enable), recovery codes kept somewhere safe. If a member loses their phone: their account's **⋯** menu → **Reset two-factor authentication**.
- [ ] Internet access only over **HTTPS** (reverse proxy or Tailscale), `PUBLIC_URL` set.
- [ ] Automatic backups on (**Admin area → Backups**, on by default), and now and then a downloaded copy kept off the server: it holds the services' tokens.
- [ ] Updates: `git pull && docker compose up -d --build`, or the published image.

---
Members have their own guide: [Family member](server-member.md).
