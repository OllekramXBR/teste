# Deploying Chordsmith on Unraid

If you want to **edit the code from your desktop while the app runs on Unraid**,
skip to [Development on an Unraid share](#development-on-an-unraid-share) — it is
a different setup from the three deployment options below.

Three options. Pick one.

- **Bind to the host's Tailscale interface (simplest).** If the Unraid box is
  already a node on your tailnet, this needs no auth key and no second Tailscale
  node — one `docker run`, reachable at `http://<tailnet-ip>:8000` and nowhere
  else. Start here.
- **Tailscale sidecar.** Gives the app its own tailnet hostname and HTTPS, at the
  cost of an auth key and a second node. Uses `docker-compose.yml`.
- **LAN / Unraid Docker tab.** Managed like any other Unraid container, reachable
  at `http://<tower-ip>:8000`. Uses `docker/chordsmith.unraid.xml`.

Everything below runs on the Unraid box itself — nothing in this repository can
reach your server on its own.

---

## Option 0 — Bind to the host's Tailscale interface

This works when Unraid already runs Tailscale (the Unraid plugin, say) and so
already has a `100.x.y.z` address.

```sh
mkdir -p /mnt/user/appdata/chordsmith/data
cd /mnt/user/appdata
git clone -b claude/chordfy-clone-v79xr7 https://github.com/OllekramXBR/teste.git chordsmith-src
cd chordsmith-src/chordsmith
docker build -t chordsmith:latest .
```

Find the host's tailnet address, then publish the port **on that interface
only**:

```sh
TS_IP=$(tailscale ip -4)          # e.g. 100.100.112.45

docker run -d --name chordsmith \
  -p "$TS_IP:8000:8000" \
  -v /mnt/user/appdata/chordsmith/data:/data \
  -e PUID=99 -e PGID=100 \
  --restart unless-stopped \
  chordsmith:latest
```

The `$TS_IP:` prefix is what matters. Without it Docker binds `0.0.0.0` and the
app is served on the LAN as well; with it, the listener exists only on the
Tailscale interface, so the only way in is through the tailnet.

Open `http://<tailnet-ip>:8000` from any device signed into your tailnet.

Plain HTTP, no certificate. That is fine here — Tailscale already encrypts
everything between nodes with WireGuard. If you want a real certificate and a
name instead of an IP, use Option 1.

Check it is bound where you expect:

```sh
docker port chordsmith          # should show 100.x.y.z:8000, not 0.0.0.0:8000
curl -sS http://$(tailscale ip -4):8000/api/health
```

---

## Option 1 — Tailscale sidecar

### 1. Get the code onto the server

```sh
mkdir -p /mnt/user/appdata/chordsmith
cd /mnt/user/appdata
git clone -b claude/chordfy-clone-v79xr7 https://github.com/OllekramXBR/teste.git chordsmith-src
cd chordsmith-src/chordsmith
```

The repository holds several projects; everything for this one lives in the
`chordsmith/` subdirectory, which is where every command below is run from.

### 2. Create a Tailscale auth key

At <https://login.tailscale.com/admin/settings/keys>, generate an auth key:

- **Reusable** — on, so the container can restart without a new key.
- **Ephemeral** — off, so the node is not removed when the container stops.
- **Tags** — optional, e.g. `tag:server`, if you use ACLs.

### 3. Write the `.env`

Next to `docker-compose.yml`:

```sh
cat > .env <<'EOF'
TS_AUTHKEY=tskey-auth-xxxxxxxxxxxx
TS_HOSTNAME=chordsmith
APPDATA=/mnt/user/appdata/chordsmith
PUID=99
PGID=100
MAX_UPLOAD_MB=60
ANALYSIS_WORKERS=2
EOF
chmod 600 .env
```

`PUID=99` / `PGID=100` are Unraid's `nobody:users`, which is what keeps the
files under `appdata` owned by something sane rather than by root.

### 4. Start it

```sh
docker compose up -d --build
```

The first build takes a few minutes — it compiles the frontend and installs
librosa and its numba dependency.

### 5. Enable HTTPS for the node

In the Tailscale admin console, turn on **MagicDNS** and **HTTPS Certificates**
(DNS → Features). The container's `serve.json` then publishes the app at:

```
https://chordsmith.<your-tailnet>.ts.net
```

Check it resolved correctly:

```sh
docker exec chordsmith-tailscale tailscale status
docker exec chordsmith-tailscale tailscale serve status
```

`tailscale serve status` should show `https://chordsmith.…ts.net (tailnet only)`
proxying to `http://127.0.0.1:8000`.

### Notes on this setup

- The app container runs with `network_mode: service:tailscale`, so it has no
  network interface of its own. Nothing listens on the LAN; the only way in is
  through the tailnet.
- Because the two containers share a network namespace, `docker compose down`
  and `up` should be done together — restarting only the Tailscale container
  will drop the app's networking with it.
- **Do not** add `"AllowFunnel"` entries to `docker/tailscale-serve.json` unless
  you specifically want the app on the public internet. Funnel exposes it to
  anyone with the URL; there is no login on this app.

---

## Option 2 — LAN, via the Unraid Docker tab

### 1. Build the image on the server

```sh
cd /mnt/user/appdata/chordsmith-src/chordsmith
docker build -t chordsmith:latest .
```

### 2. Install the template

```sh
cp docker/chordsmith.unraid.xml /boot/config/plugins/dockerMan/templates-user/my-chordsmith.xml
```

Then in the Unraid web UI: **Docker → Add Container → Template: my-chordsmith**.
Adjust the port and the data path if you want, and apply.

The UI lands at `http://<tower-ip>:8000/`.

To reach it remotely, install the **Tailscale** plugin from Community
Applications and use the tower's tailnet address — the container itself needs no
changes for that.

---

## Updating

```sh
cd /mnt/user/appdata/chordsmith-src/chordsmith
git pull
docker compose up -d --build     # or: docker build -t chordsmith:latest .
```

Uploaded audio and the analysis database live in the `/data` volume, so they
survive rebuilds.

## Backing up

Everything worth keeping is in one directory:

```sh
tar czf chordsmith-backup.tgz -C /mnt/user/appdata/chordsmith data
```

## Resource notes

- Analysis is CPU-bound and single-threaded per track. `ANALYSIS_WORKERS=2` is a
  reasonable default; raising it past your core count will not help.
- Expect roughly 5–10 seconds of analysis per minute of audio on a modern
  desktop CPU. The first analysis after a container start is slower because
  numba compiles its kernels — this is a one-time cost per container lifetime,
  and the app warms it up on startup.
- RAM peaks around 700 MB during analysis of a long track.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `TS_AUTHKEY` error on start | `.env` missing or key expired | Regenerate the key, rewrite `.env`, `docker compose up -d` |
| App unreachable but Tailscale is up | HTTPS certs not enabled | Turn on MagicDNS + HTTPS Certificates in the admin console |
| Upload rejected as unsupported | `.m4a`/AAC file | Convert to MP3, WAV, FLAC or OGG — the container has no ffmpeg |
| Analysis fails on one file | Corrupt or zero-length audio | The error is shown on the song page; re-upload or re-encode |
| Files under `appdata` owned by root | `PUID`/`PGID` unset | Set them in `.env` and recreate the container |

---

## Development on an Unraid share

The setup this covers: the source lives on an Unraid **user share**, you edit it
from your desktop over SMB (`A:\EasyChords`, say), and the app runs on the Unraid
box with hot reload. Nothing is installed on the desktop — no Python, no Node.

Uses `docker-compose.dev.yml`, which is separate from the production compose file
and configured differently on purpose.

### 1. Pick a share, not appdata

Put the code somewhere exported over SMB. `appdata` usually is not, and is meant
for container state rather than source:

```sh
mkdir -p /mnt/user/projetos/chordsmith
```

The **data** — uploaded audio and the database — stays out of the source tree,
on `appdata`, where it belongs:

```sh
mkdir -p /mnt/user/appdata/chordsmith/data
```

### 2. Clone from the Unraid terminal

Clone on the server, not from Windows. A clone made by Windows Git writes CRLF
line endings, and `entrypoint.sh` will not run inside the container with those —
it fails with a confusing `no such file or directory`.

```sh
cd /mnt/user/projetos/chordsmith
git clone -b claude/chordfy-clone-v79xr7 https://github.com/OllekramXBR/teste.git .
cd chordsmith
```

If you do end up editing shell scripts from Windows, set this once in the repo so
Git stops rewriting their endings:

```sh
git config core.autocrlf input
```

### 3. Configure and start

```sh
cat > .env <<'ENVFILE'
BIND_IP=100.100.112.45
DATA_DIR=/mnt/user/appdata/chordsmith/data
PUID=99
PGID=100
API_PORT=8010
WEB_PORT=5173
ENVFILE
```

`API_PORT` and `WEB_PORT` are the ports published on the host; they default to
8000 and 5173. On a busy Unraid box 8000 is often already taken — Portainer
publishes it, for one — so check before you start:

```sh
netstat -tln | awk '{print $4}' | sed 's/.*://' | sort -nu | tr '\n' ' '
```

Anything in that list is spoken for. Note that the ports the containers use
*internally* stay 8000 and 5173 whatever you pick, so Vite's proxy target is
unaffected.

Unraid does **not** ship Docker Compose V2 by default. Check before going
further:

```sh
docker compose version
```

If that fails with `unknown shorthand flag: 'f'` or `docker: 'compose' is not a
docker command`, pick one:

- **Install it** — Community Applications → **Docker Compose Manager**. This is
  the tidier route, and it also gives you a stack UI in the Unraid web
  interface. Then:

  ```sh
  docker compose -f docker-compose.dev.yml up -d --build
  ```

- **Skip Compose entirely** — `docker/dev-run.sh` does the same thing in plain
  `docker run`, reading the same `.env`:

  ```sh
  sh docker/dev-run.sh              # start
  sh docker/dev-run.sh stop         # stop and remove the containers
  ```

Older systems may have the V1 binary under its hyphenated name
(`docker-compose -f docker-compose.dev.yml up -d --build`), but V1 is
end-of-life and does not read every key used here — prefer one of the two above.

`BIND_IP` is the host's Tailscale address, so the dev servers are published on
the tailnet and nowhere else. Use `0.0.0.0` if you want them on the LAN too.

Two things are now running:

| URL | What |
| --- | --- |
| `http://<BIND_IP>:<WEB_PORT>` | The UI, with hot reload. **Use this one.** |
| `http://<BIND_IP>:<API_PORT>` | The API directly, plus `/docs` |

Vite proxies `/api` to the API container over the compose network, so the browser
only ever talks to one origin and CORS never comes up.

### 4. Edit from your desktop

Map the share to a drive letter and open it in your editor. Save a file under
`backend/` and uvicorn reloads; save one under `frontend/src/` and the browser
updates.

### Why this compose file differs from the production one

Two problems come with running from a share, and both are handled in
`docker-compose.dev.yml`:

- **`node_modules` never touches the share.** It lives in a named volume on the
  Docker disk. Thousands of small files over SMB/shfs is where this setup
  otherwise becomes unusable — `npm install` alone can take many minutes.
- **File watching is forced to polling** (`WATCHFILES_FORCE_POLLING` for uvicorn,
  `VITE_USE_POLLING` for Vite). inotify does not fire reliably through Unraid's
  shfs layer, so without this the reloaders never notice that you saved anything
  and you are left wondering why nothing changes.

The dev API image also builds only the `backend` stage of the Dockerfile — the
frontend is not built into it, because Vite is serving the UI.

### Running the tests against the running code

```sh
docker compose -f docker-compose.dev.yml exec api \
  sh -c "cd /app/backend && python -m pytest"
```

### Going back to production

When you are done iterating, stop the dev stack and start the real one. They bind
the same ports, so do not run both:

```sh
docker compose -f docker-compose.dev.yml down
docker compose up -d --build          # or the plain `docker run` from Option 0
```

The data directory is shared between the two, so your library survives the
switch.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `unknown shorthand flag: 'f' in -f` | Compose V2 not installed | Install Docker Compose Manager, or use `sh docker/dev-run.sh` |
| Edits do nothing | Polling not on | Check `.env` was picked up: `docker compose -f docker-compose.dev.yml config` |
| `entrypoint.sh: no such file or directory` | CRLF line endings from a Windows clone | Re-clone from the Unraid terminal, or `dos2unix docker/entrypoint.sh` |
| `npm install` never finishes | `node_modules` landed on the share | Confirm the `web-node-modules` volume exists: `docker volume ls` |
| `Bind for 0.0.0.0:8000 failed: port is already allocated` | Another container already publishes that port on **all** interfaces, so binding it on one specific address cannot work either — the message names 0.0.0.0 even when you set `BIND_IP` | Find the holder with `docker ps --format '{{.Names}} {{.Ports}}' \| grep :8000`, then set `API_PORT` to a free port in `.env` |
| Port already in use | The production stack is still up | `docker compose down`, or stop the `chordsmith` container |
| Files owned by root on the share | `PUID`/`PGID` unset | Set them in `.env` and recreate the containers |
