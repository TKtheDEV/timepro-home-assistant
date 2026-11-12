# Install and connect

Requires Home Assistant OS with Supervisor and its app/add-on store. Plain Home
Assistant Container does not install add-ons. TimePRO needs no HA access token,
Companion integration, host networking, privileged mode or access to HA's config.

## Install from the App Store

1. Add `https://github.com/TKtheDEV/timepro-home-assistant` in the HA app/add-on store's repository menu, or use the **Add
   to My Home Assistant** button in the repository README.
2. Install **TimePRO**. The runtime uses released, checksum-verified binaries;
   no Rust/C++ compiler or private GitHub credentials are needed on your HA host.
3. Before the first start, set `initial_timezone` (Marshall University:
   `America/New_York`). Enable `built_in_model` if the host has sufficient RAM.
4. Start → Open Web UI. Choose the provider, connect calendars, set language,
   then configure a dedicated HTTPS phone origin and scan the pairing QR.

This is a personal-server preview. The installer repository and executable
releases are public; the application development repository is currently private.

## Model

Choose **Built-in local model** to keep interpretation inside this add-on. Enable
`built_in_model` in Configuration, restart, wait for **Local model: Ready**, then
choose it in the setup page and save. This option downloads Qwen2.5 1.5B Instruct
Q4_K_M (1.12 GB) from its pinned official Hugging Face revision and verifies its
SHA-256. No model is downloaded when the option is off; no silent cloud fallback.

Allow **at least 2.5 GB of available RAM in addition to Home Assistant's needs**
and 2 GB of free disk for weights/downloads. A 6–8 GB HA VM is a more practical
starting point than a small appliance. These are resource limits, not a latency
or understanding guarantee. CPU inference is limited to one request and 1–4
threads (default 2). A memory check refuses to start the model on a constrained
host while keeping the planner and setup available. The model stays loaded while
enabled. Disable it and restart to free its RAM. Model files are excluded from HA
backups and can be downloaded again.

The amd64 model runtime requires AVX2, FMA, F16C and BMI2 (Haswell-era or newer
Intel/AMD features). A Proxmox VM may need CPU type `host` to expose them. A
preflight check keeps the planner running and reports missing features instead
of starting an incompatible model binary. The aarch64 build uses its ARM baseline.

Alternatively choose a LAN Ollama endpoint using a literal private IP, e.g.
`http://192.168.50.20:11434`, or an HTTPS OpenAI-compatible provider. TimePRO's
server validates local HTTP opt-in and TLS. A small model can misunderstand a
request; review/clarification and deterministic scheduling checks remain active.

Qwen weights: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF
Runtime: https://github.com/ggml-org/llama.cpp (both Apache-2.0/MIT as applicable;
see upstream model card and runtime licenses).

## Phone HTTPS

HA ingress authenticates this setup page. Android needs a **dedicated HTTPS
origin** with no path, not the HA ingress URL or the main HA address.

Choose one:

* **`phone_access: tls`**: place a valid certificate and matching key in HA's
  `/ssl` folder. Configure `certfile` and `keyfile` as filenames (defaults
  `fullchain.pem` and `privkey.pem`), set `public_url` (for example
  `https://timepro.example.com:8443`), and map **8443/tcp** under Network to a free
  host port. Restart. DNS and any firewall/port forwarding must reach that port.
  The phone must trust the certificate; verification is never bypassed.
  Renew the files using your existing HA certificate app; TimePRO checks for
  changes once a minute and reloads nginx only after successful validation.
* **`phone_access: reverse_proxy`**: set `public_url` to a dedicated hostname on
  your existing TLS proxy/tunnel. Forward that hostname to this add-on's internal
  **8216/tcp** listener. For another add-on, use TimePRO's container hostname from
  its Info tab. For a proxy elsewhere, explicitly map 8216 to the host and restrict
  it to your trusted proxy/LAN. The hop to 8216 is HTTP; use a private link/VPN
  when it leaves the HA host. A Cloudflare tunnel terminates TLS at Cloudflare,
  which can read traffic. The TLS listener avoids that third-party endpoint.

Both phone ports are **unmapped and disabled by default**. The public listener
passes device authorization through unchanged; it cannot serve the ingress setup
page or inject an owner credential. Owner-only pairing endpoints still require
owner authentication. The QR contains a 120-second, single-use code rather than
the owner token; every paired phone gets a separately revocable credential.

Reverse-proxy example (Caddy on the same private network):

```caddyfile
timepro.example.com {
    reverse_proxy TIMEPRO_PRIVATE_UPSTREAM:8216
}
```

`public_url` must exactly match the origin the phone reaches, including a
nonstandard external port. HTTPS configuration does not automatically change DNS,
obtain a certificate, create a tunnel or modify your firewall. QUIC/HTTP3 is not
enabled in this first HA package.

## Calendars, data and updates

Save a Nextcloud URL, username and **app password** in the setup page. Select a
purpose for each discovered calendar and sync it: classes/appointments are fixed
time; Blackboard is deadlines. This preview performs calendar sync on request,
not on an automatic timer. Deadlines do not infer how much homework you have done.

Tasks, history, provider/calendar credentials, device registrations and the owner
token live in **`/data/timepro`**, outside the image. Restarting or rebuilding the
same installed add-on preserves them. `/data/models` caches weights. Full HA
backups include private planner data (excluding model weights); use encrypted
backups and protect the HA host. Uninstalling an add-on can delete its data.

This creates a new planner unless an existing backup is restored. It does not
copy data from an unreachable Proxmox CT. Never copy live SQLite files one by
one: stop the old server first or create consistent SQLite backups of **both**
`timepro.sqlite3` and `timepro.engine.sqlite3`, together with `auth.token`. Restore
to `/data/timepro` while this add-on is stopped, with directory 0700, files 0600
and owner UID/GID 10001. Never run two copies against the same writable database.
If restored, existing device tokens remain valid but devices may need to pair
again when their server URL changes. The initial timezone only seeds new data;
restored data keeps its original timezone.

## Troubleshooting

* **No add-on store:** Home Assistant Container cannot host add-ons; use HAOS or
  run the TimePRO container as a separate service.
* **Setup page fails:** inspect the add-on log. Invalid options/certificates fail
  closed and retain existing data. Restore the previous settings and restart.
* **Model downloading:** the planner stays available; first download takes time.
  An error can be retried by restarting after fixing disk/network/RAM. No cloud
  inference is selected on failure.
* **Phone pairing fails:** first verify the dedicated public HTTPS URL and valid
  certificate from the phone's network. HA ingress working alone is insufficient.
* **An update fails:** keep the installed add-on and `/data`; restore the HA
  backup or previous image. Do not clear app storage or uninstall the Android app.
