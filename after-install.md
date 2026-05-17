# Hermes Wiki Installed

Run dependency setup in the Hermes runtime:

```bash
hermes wiki deps --install all
hermes gateway restart
```

For Docker deployments with separate Agent and WebUI Python environments, run dependency setup in both runtimes if WebUI imports the plugin directly.
