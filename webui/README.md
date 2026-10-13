# StreamCap Web UI

A new interface for StreamCap. It drives the same recording core as the Flet app, through a
small HTTP/WebSocket API (`app/api/control/`), and leaves the original Flet UI untouched.

## Run

```bash
pip install -r requirements-webui.txt       # once
cd webui && npm install && npm run build    # once, and after pulling UI changes
cd .. && python serve.py --open             # http://127.0.0.1:6008
```

`serve.py` takes `--host` / `--port` (or `WEBUI_HOST` / `WEBUI_PORT`). The API has **no
authentication**: keep the default `127.0.0.1` unless the network is trusted.

Don't run `serve.py` and the Flet app (`main.py`) at the same time — both would record the same
rooms from the same `config/recordings.json`.

## Develop

```bash
python serve.py                 # API on :6008
cd webui && npm run dev         # Vite on :5178, proxies /api to :6008
```

## What the API adds over the Flet UI

- Real download speed, file size and resolution per recording (the core only stores a
  placeholder `speed`) — sampled from the output file in `app/api/control/media.py`.
- Cover thumbnails grabbed from the local file being written. It never re-opens the stream URL
  while recording: some CDNs (Douyu) issue single-use URLs, and a second pull breaks the recording.
- A guard around `check_if_live`, which is not re-entrant: two concurrent checks start two
  recorders for one room.
