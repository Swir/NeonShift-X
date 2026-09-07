<div align="center">

# ⚡ NEONSHIFT X

### Neon Gaming Macro & Activity Engine for Windows

**Macro Recorder • Playback Engine • Activity Modes • Emergency Stop • Gaming UI**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![GUI](https://img.shields.io/badge/GUI-CustomTkinter-00E5FF)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active-39FF88)

</div>

---

## 🚀 About

**NEONSHIFT X** is a desktop macro recorder, playback engine and configurable activity utility written in Python. It combines mouse and keyboard recording with a futuristic neon control center designed for Windows.

The project focuses on transparent local automation: record your own input, inspect the captured macro, replay it with configurable speed and loops, or use lightweight activity modes when appropriate.

---

## ✨ Features

| Module | Features |
|---|---|
| 🖱️ Mouse | movement, clicks and scroll recording |
| ⌨️ Keyboard | key-down and key-up recording |
| ▶️ Playback | configurable speed and repeat count |
| 🎮 Activity Engine | Move & Return, Drift and Micro Jitter modes |
| 🛑 Safety | F8 global Emergency Stop and PyAutoGUI Fail-Safe |
| 📊 Telemetry | moves, clicks, keys, macro runs and activity pulses |
| 🔎 Macro Inspector | quick statistics for recorded macros |
| 💾 Configuration | persistent local JSON settings |
| 🌌 Interface | dark neon cyan / purple / magenta gaming dashboard |

---

## 🛑 Controls

- **F8** — Global Emergency Stop for recording, playback and Activity Engine.
- **ESC** — Stop macro recording.
- Moving the pointer to a PyAutoGUI fail-safe corner can stop automated pointer actions.

---

## 📦 Installation

```bash
git clone https://github.com/Swir/NeonShift-X.git
cd NeonShift-X
pip install -r requirements.txt
python NeonShift_X.py
```

Requires Python 3.10+ and is primarily designed for Windows.

---

## 🎛️ Activity Modes

**Move & Return** performs a small movement and returns the cursor to its previous position. **Drift** performs bounded movement while keeping the cursor inside a safe screen area. **Micro Jitter** uses very small movements for a lighter activity pattern.

Intervals and movement ranges are configurable from the application interface.

---

## 🎙️ Macro Engine

NEONSHIFT X records timestamped mouse and keyboard events. Keyboard input stores separate press and release events so modifier combinations such as Ctrl, Shift and Alt can be reproduced more accurately. Legacy `keypress` macro events are also supported for compatibility with older recordings.

Macro data is stored locally in `neonshift_macro.json`. Application settings are stored in `neonshift_config.json`. Both files are ignored by Git by default.

---

## 🔍 Discoverability

`python macro recorder` • `windows macro recorder` • `gaming macro python` • `customtkinter gaming ui` • `python mouse recorder` • `python keyboard recorder` • `pynput macro recorder` • `pyautogui macro` • `macro playback engine` • `desktop automation python` • `neon python gui` • `activity engine windows` • `mouse movement utility` • `keyboard automation` • `macro inspector` • `gaming automation dashboard` • `customtkinter neon dashboard`

---

## 🛠️ Built With

- Python
- CustomTkinter
- PyAutoGUI
- Pynput
- Tkinter
- Threading
- JSON

---

## ⚠️ Responsible Use

NEONSHIFT X automates local keyboard and mouse input. Use it only where automation is permitted. Do not use it to spam, bypass security controls, evade platform restrictions, or automate actions you are not authorized to perform.

---

## 👨‍💻 Author

Developed by **Swir** — [@Swir](https://github.com/Swir)

---

<div align="center">

### ⚡ RECORD • REPLAY • CONTROL

⭐ Star the repository if you find the project useful.

</div>
