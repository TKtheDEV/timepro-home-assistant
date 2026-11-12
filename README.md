# TimePRO for Home Assistant

Your time-management companion, hosted beside Home Assistant. Configure it in HA;
use the native Android app throughout your day.

[![Add to My Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FTKtheDEV%2Ftimepro-home-assistant)

Or add this repository URL in **Settings → Apps/Add-ons → Store → Repositories**:

```text
https://github.com/TKtheDEV/timepro-home-assistant
```

Install **TimePRO**, set your timezone, start and open Web UI.
[Full setup and HTTPS instructions](timepro/DOCS.md).

* HA-authenticated setup page, Nextcloud calendar connection and rotating phone QR.
* Optional local Qwen model on CPU, with selectable Ollama/compatible providers.
* Persistent tasks, settings and paired devices across ordinary add-on updates.
* Dedicated HTTPS phone API; no privileged mode, HA token or Companion dependency.
* amd64 and aarch64 runtime bundles verified by SHA-256 during installation.

The local model's first download is 1.12 GB and needs at least 2.5 GB **available**
RAM beyond HA's own needs. It is disabled by default. No automatic cloud fallback.
An existing HA host with 16 GB is suitable for trying this small model, subject
to what else is running. Manual calendar sync only in this preview.

This is a development preview: travel/weather planning, wake-word detection,
hosted E2EE and full phone enforcement are not implemented. Installing the add-on
does not migrate an unreachable old server or automatically configure DNS/TLS.

The public repository contains hosting/setup files and released server binaries.
No private calendar data, signing keys or deployment credentials are included.
