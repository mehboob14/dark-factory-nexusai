# Pocketful stage-1 acceptance suite

Independent black-box HTTP checks for requirement lines R1–R159.
Derived from `REQUIREMENTS.md` and `spec/stage-1.md`. Does not copy harness samples.

## One command

From this directory, against a container built exactly as `../RUN.md`:

```
python run.py
```

That command installs this folder's Python dependencies if needed, builds
`docker build -t pocketful-s1 .` in `stage-1`, starts the image with
`-e PORT=8080` and a host port mapping (no Compose), waits for `GET /health`,
runs every check, then stops the container.

If a container is already running that way:

```
python run.py --base-url http://127.0.0.1:8080
```

Checks are named `test_R<n>_…` so coverage of R1–R159 can be counted.
