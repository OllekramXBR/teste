# Deploying Chordsmith on Unraid

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
