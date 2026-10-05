# Pocketful stage 1 — run

From this directory (`stage-1`):

```sh
docker build -t pocketful-s1 . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-s1
```

The service listens on `http://0.0.0.0:8080` (override with `-e PORT=` and matching `-p`).

No manual setup beyond the command above.
