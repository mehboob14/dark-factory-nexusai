# Pocketful stage 2 — run

From this directory (`stage-2`):

```sh
docker build -t pocketful-s2 . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-s2
```

The service listens on `http://0.0.0.0:8080` (override with `-e PORT=` and matching `-p`).

No manual setup beyond the command above.
