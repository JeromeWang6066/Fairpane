# 窗景心晴

英文名 Fairpane。每天打一次分，本地 Qwen 写成画面提示，云端 z-image-turbo 出清晨、正午、黄昏、夜晚四张横图。页面用来看这一天的效果。Mac 上打开应用时，这页就是控制台；当前时辰的那张图铺在系统桌面上，窗口和图标仍在它前面。

这不是疗愈对话。

## 环境

| 项目 | 说明 |
|------|------|
| Python | 3.11 |
| 系统 | macOS。桌面壁纸和菜单栏只在 Mac 上可用 |
| 本地 Qwen | `http://127.0.0.1:8080/v1`，模型名 `qwen3.5-2b` |
| 出图 | 阿里云百炼的 `DASHSCOPE_API_KEY`（z-image-turbo，华北 2 北京） |

Qwen 权重不在这个仓库里。把移动硬盘挂上，在 `qwen35-2b` 目录运行 `start_qwen.sh`。默认脚本路径是 `/Volumes/My Passport/qwen35-2b/start_qwen.sh`，也可以用环境变量 `QWEN_START` 指到别处。

## 安装与启动

```bash
git clone git@github.com:JeromeWang6066/Fairpane.git
cd Fairpane

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 把 DASHSCOPE_API_KEY 写入 .env
```

密钥留空时，程序还会读上一级目录里的 `.env`，只取同名的 `DASHSCOPE_API_KEY`。

```bash
.venv/bin/python server.py
```

浏览器打开 http://127.0.0.1:8770 。

每次打开，画面都固定在一扇窗前。先选窗外的景观（街道、海岸或庭院），再选风格（写实、水彩或动漫），然后打 1–10 分。可以写一句，也可以跳过。确认之后从当时的时辰开始画，更早的时辰不再画，后面的时辰会接着画完。页面仍铺满来预览。右下角「时刻」只换页面上预览的那一张，不改桌面。左下角的圆点可以改今天的分数，新旧画面用大约一分钟淡过去。拨到「夜」，或本地时间过了晚上八点，会问今天这张是否合适。

Qwen 没有连上时，仍用代码里的保底句子出图，页面会说明。百炼没有连上时，页面留下失败原因，可以再试。

在 Mac 上，服务起来之后会把当前时辰的 PNG 设成每块屏幕的桌面图片。清晨图先画好时，如果现在不是清晨，桌面会等这一时辰的文件落盘再换。某一张没画成，原来的桌面留着。设 `DAYPLACE_WALLPAPER=0` 则只开页面，不改桌面。

直接跑 `server.py` 时，图片和当天记录在 `data/`，不进版本库。`build/` 和 `dist/` 是打包产物，同样不入库。

## Mac 应用

控制台是一个普通窗口，不全屏。关掉窗口后程序留在菜单栏，到点把桌面换成下一个时辰。菜单栏只显示当天出图天气的符号，点开可以再打开控制台、按当前时辰再铺一次，或退出。退出之后，最后一张壁纸还在，下一时辰不再自动换，直到再次打开。

应用窗口不放生成的画面，只调地点、风格、时间、心情和天气，再按「重新生成」。时间决定从哪个时辰开始画。窗口和菜单栏都可以「换回原来的壁纸」，回到这次打开之前桌面上的那张。换回之后，到点不再自动铺上新画面；重新生成，或菜单里「按当前时辰再铺一次」，会再换回来。打开应用时会看本机 8080 端口。已经在听，或 `llama-server` 还在加载，就不再启动一次。都没有，且 My Passport 上有 `qwen35-2b/start_qwen.sh`，就把它拉起来。硬盘没挂上时应用仍会打开，出图改用保底句子。启动记录写在 `~/Library/Application Support/Dayplace/qwen.log`。

```bash
.venv/bin/python mac_app.py
```

打成可以双击的应用：

```bash
.venv/bin/python setup.py py2app
```

产物是 `dist/窗景心晴.app`。包名是 Fairpane，Dock 上仍显示窗景心晴。打包后的图片、记录和 `.env` 放在 `~/Library/Application Support/Dayplace/`。Qwen 的权重仍在移动硬盘上，不打进应用里。

## 环境变量

复制 `.env.example` 为 `.env` 后再改。

| 变量 | 默认 | 说明 |
|------|------|------|
| `QWEN_API_BASE` | `http://127.0.0.1:8080/v1` | 本地 Qwen |
| `QWEN_MODEL` | `qwen3.5-2b` | 模型名 |
| `QWEN_API_KEY` | `local` | 本地服务不校验这把钥匙 |
| `QWEN_START` | My Passport 上的 `start_qwen.sh` | 8080 没在听时要拉起的脚本 |
| `DASHSCOPE_API_KEY` | 空 | 百炼密钥，必填才能出图 |
| `DASHSCOPE_API_BASE` | `https://dashscope.aliyuncs.com/api/v1` | 可换成业务空间域名 |
| `DAYPLACE_LAT` / `DAYPLACE_LON` | 上海 | 不授权定位时的天气坐标 |
| `DAYPLACE_CITY` | 上海 | 城市名 |
| `DAYPLACE_HOST` | `127.0.0.1` | 页面地址 |
| `DAYPLACE_PORT` | `8770` | 页面端口 |
| `DAYPLACE_WALLPAPER` | 开启 | 设为 `0` 时不改系统桌面 |

## 许可

MIT。见 [LICENSE](LICENSE)。
