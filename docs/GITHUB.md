# GitHub workflow (private repo khandanish7863/aeneas-align-api)

The code lives in a **private** GitHub repository, branch `main`. Each VM downloads it with its own read-only
"deploy key" and updates with one command: `aeneas-update`.
The token and settings (`.env`) are never in git.

## New VM
Use the one-line command in `README.md`. It makes the key, waits for you to add it on GitHub, then installs.

Add the key on GitHub: repo → **Settings → Deploy keys → Add deploy key** → title (e.g. `Aeneas VM 2`),
paste the `ssh-ed25519 …` line, leave **Allow write access** unticked → **Add key**.
Every VM gets its own key (a deploy key can be used by one repository only — the Mummy Video Editor key will not work here).

## Every update after that
```bash
aeneas-update
```
Shows the list of changes, installs, restarts. `aeneas-update --force` reinstalls even when nothing changed.

## Making changes
- **With Claude:** ask for the change in a Claude chat that has this repo attached. Claude tests it, commits
  to `main` and pushes. Then run `aeneas-update` on the VM.
- **Yourself on github.com:** open a file → pencil icon → edit → **Commit changes**. Then `aeneas-update`.

Bump `VERSION` for every release so `/health` shows which version is running.

## Going back to an earlier version
```bash
cd ~/aeneas-align-api && git log --oneline | head -20      # pick a version id, e.g. 1a2b3c4
git reset --hard 1a2b3c4 && sudo bash install.sh
# back to the newest:  aeneas-update --force
```

## Removing a VM's access
GitHub → repo → **Settings → Deploy keys** → delete that VM's key.
