# Fairpane

[中文](README.md)

Fairpane (窗景心晴) asks for one score a day. A local Qwen model turns that into a picture prompt, and z-image-turbo draws four wide images: morning, noon, dusk, and night. The page is for looking at that day. On a Mac, the same page is the console, and the image for the current part of the day is set as the desktop wallpaper. The window and icons stay in front of it.

## Requirements

| Item | Notes |
|------|------|
| Python | 3.11 |
| System | macOS. Wallpaper and the menu bar only work on a Mac |
| Local Qwen | An OpenAI-compatible server on your machine. Default `http://127.0.0.1:8080/v1`, model name `qwen3.5-2b` |
| Images | An Alibaba Cloud Model Studio `DASHSCOPE_API_KEY` (z-image-turbo, China North 2, Beijing) |

The model weights are not in this repository. Start the Qwen server your own way before generating images. If the address or model name differs, change `QWEN_API_BASE` and `QWEN_MODEL` in `.env`. If you have a launch script, put its path in `QWEN_START`.

## Install and run

```bash
git clone https://github.com/JeromeWang6066/Fairpane.git
cd Fairpane

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Open `.env` and set `DASHSCOPE_API_KEY`. If that key is left empty, the program also reads `.env` in the parent directory and takes only the same variable.

Once the local Qwen server is listening:

```bash
.venv/bin/python server.py
```

Open http://127.0.0.1:8770 .

Every picture stays in front of one window. Choose what is outside (a street, a shore, or a courtyard), then a style (realistic, watercolor, or anime), then a score from 1 to 10. A short note is optional. After you confirm, drawing starts at the current part of the day. Earlier parts are skipped. Later ones continue until the day is done. The page stays filled to the edges so you can preview. The “时刻” control at the lower right only changes which image the page shows. It does not change the desktop. The dot at the lower left can change today's score. The old and new pictures crossfade for about a minute. At "night", or after 8 p.m. local time, it asks whether today's picture fits.

If Qwen is not connected, pictures still use the fallback sentences in the code, and the page says so. If Model Studio is not connected, the page keeps the error so you can try again.

On a Mac, once the server is up it sets the PNG for the current part of the day as the wallpaper on each screen. If the morning image finishes while it is no longer morning, the desktop waits until the file for the current part of the day is on disk. If one image fails, the previous wallpaper stays. Set `DAYPLACE_WALLPAPER=0` to keep the page and leave the desktop alone.

When you run `server.py` directly, images and the day's record go in `data/`, which is not in the repository. `build/` and `dist/` are packaging output and are left out as well.

## Mac app

The console is a normal window, not fullscreen. After you close it, the program stays in the menu bar and changes the desktop when the next part of the day begins. The menu bar only shows the weather symbol used for today's pictures. From there you can open the console again, set the wallpaper for the current part of the day, or quit. After you quit, the last wallpaper remains. The next part of the day does not change it until you open the app again.

The app window does not show the generated picture. It only sets place, style, time, mood, and weather, then "Regenerate". The time chooses which part of the day drawing starts from. Both the window and the menu bar can restore the wallpaper from before this launch. After that restore, later parts of the day do not replace the desktop again until you regenerate, or choose to set the current image again from the menu. On launch the app checks port 8080. If something is already listening, or `llama-server` is still loading, it does not start another copy. If neither is true and `QWEN_START` points to a launch script, it runs that script. If Qwen never comes up, the app still opens and uses the fallback sentences. The launch log is `~/Library/Application Support/Dayplace/qwen.log`.

```bash
.venv/bin/python mac_app.py
```

To build an app you can double-click:

```bash
.venv/bin/python setup.py py2app
```

The result is `dist/窗景心晴.app`. The bundle name is Fairpane. The Dock still shows 窗景心晴. After packaging, images, records, and `.env` live in `~/Library/Application Support/Dayplace/`. The Qwen weights are not bundled into the app.

## Environment variables

Copy `.env.example` to `.env`, then edit it.

| Variable | Default | Notes |
|------|------|------|
| `QWEN_API_BASE` | `http://127.0.0.1:8080/v1` | Address of the local Qwen server |
| `QWEN_MODEL` | `qwen3.5-2b` | Model name |
| `QWEN_API_KEY` | `local` | The local server does not check this key |
| `QWEN_START` | empty | Optional. Script to run when port 8080 is not listening |
| `DASHSCOPE_API_KEY` | empty | Model Studio key. Required to generate images |
| `DASHSCOPE_API_BASE` | `https://dashscope.aliyuncs.com/api/v1` | Can be a workspace endpoint instead |
| `DAYPLACE_LAT` / `DAYPLACE_LON` | Shanghai | Weather coordinates when location access is not granted |
| `DAYPLACE_CITY` | 上海 | City name |
| `DAYPLACE_HOST` | `127.0.0.1` | Page address |
| `DAYPLACE_PORT` | `8770` | Page port |
| `DAYPLACE_WALLPAPER` | on | Set to `0` to leave the desktop unchanged |

## License

MIT. See [LICENSE](LICENSE).
