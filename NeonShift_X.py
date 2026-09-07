import os
import sys
import json
import time
import random
import threading
import traceback
import tkinter as tk
from tkinter import messagebox

try:
    import customtkinter as ctk
    import pyautogui
    from PIL import Image
    from pynput import mouse, keyboard
except ImportError as exc:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing dependency",
        "Install required packages:\n\n"
        "pip install customtkinter pyautogui pynput pillow\n\n"
        f"Details: {exc}",
    )
    root.destroy()
    raise SystemExit(1)

# ============================================================
# NEONSHIFT X — Macro & Activity Engine
# Windows-focused desktop macro recorder + activity helper.
# ============================================================

APP_NAME = "NEONSHIFT X"
APP_VERSION = "2.0 NEON"

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "neonshift_config.json")
MACRO_FILE = os.path.join(BASE_DIR, "neonshift_macro.json")

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "neonshift_logo.png")
HERO_FILE = os.path.join(ASSETS_DIR, "neonshift_hero.png")
ICON_FILE = os.path.join(ASSETS_DIR, "neonshift_icon.ico")

DEFAULT_CONFIG = {
    "afk_min_interval": 20.0,
    "afk_max_interval": 60.0,
    "afk_min_move": 30,
    "afk_max_move": 120,
    "afk_mode": "Move & Return",
    "playback_speed": 1.0,
    "playback_loops": 1,
    "record_mouse": True,
    "record_keyboard": True,
    "record_scroll": True,
    "move_threshold": 4,
    "return_delay": 0.20,
}

config = DEFAULT_CONFIG.copy()
stats = {
    "moves": 0,
    "clicks": 0,
    "keys": 0,
    "macro_runs": 0,
    "afk_pulses": 0,
}

state_lock = threading.RLock()
afK_stop = threading.Event()
record_stop = threading.Event()
play_stop = threading.Event()

recording = False
playing = False
afK_running = False
macro_events = []
record_start = 0.0
last_rec_x = 0
last_rec_y = 0
mouse_listener = None
keyboard_listener = None
hotkey_listener = None
app_instance = None
play_keyboard = keyboard.Controller()


def safe_log(text):
    if app_instance:
        app_instance.log_event(text)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            config.update(data)
    except Exception as exc:
        safe_log(f"Could not load configuration: {exc}")


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    safe_log("Configuration saved.")


def clamp(value, low, high):
    return max(low, min(high, value))


def random_signed_distance(min_distance, max_distance):
    minimum = max(1, abs(int(min_distance)))
    maximum = max(minimum, abs(int(max_distance)))
    value = random.randint(minimum, maximum)
    return value if random.choice((True, False)) else -value


# ------------------------- ACTIVITY / ANTI-AFK -------------------------

def activity_loop():
    global afK_running
    afK_running = True
    safe_log(
        f"Activity Engine START | mode={config['afk_mode']} | "
        f"interval={config['afk_min_interval']:.1f}-{config['afk_max_interval']:.1f}s"
    )

    try:
        while not afK_stop.is_set():
            delay = random.uniform(
                float(config["afk_min_interval"]),
                float(config["afk_max_interval"]),
            )
            if afK_stop.wait(delay):
                break

            try:
                width, height = pyautogui.size()
                start_x, start_y = pyautogui.position()

                dx = random_signed_distance(
                    config["afk_min_move"], config["afk_max_move"]
                )
                dy = random_signed_distance(
                    config["afk_min_move"], config["afk_max_move"]
                )

                # Keep cursor away from fail-safe corners.
                margin = 8
                target_x = clamp(start_x + dx, margin, max(margin, width - margin - 1))
                target_y = clamp(start_y + dy, margin, max(margin, height - margin - 1))
                mode = config.get("afk_mode", "Move & Return")

                if mode == "Micro Jitter":
                    micro_x = clamp(start_x + random.randint(-8, 8), margin, width - margin - 1)
                    micro_y = clamp(start_y + random.randint(-8, 8), margin, height - margin - 1)
                    pyautogui.moveTo(micro_x, micro_y, duration=random.uniform(0.08, 0.16))

                elif mode == "Drift":
                    pyautogui.moveTo(target_x, target_y, duration=random.uniform(0.18, 0.42))

                else:  # Move & Return
                    pyautogui.moveTo(target_x, target_y, duration=random.uniform(0.16, 0.36))
                    if afK_stop.wait(float(config.get("return_delay", 0.20))):
                        break
                    safe_x = clamp(start_x, margin, width - margin - 1)
                    safe_y = clamp(start_y, margin, height - margin - 1)
                    pyautogui.moveTo(safe_x, safe_y, duration=random.uniform(0.12, 0.28))

                with state_lock:
                    stats["moves"] += 1
                    stats["afk_pulses"] += 1
                if app_instance:
                    app_instance.update_stats()

            except pyautogui.FailSafeException:
                safe_log("FAIL-SAFE triggered. Activity Engine stopped.")
                break
            except Exception as exc:
                safe_log(f"Activity Engine error: {exc}")
                break

    finally:
        afK_running = False
        afK_stop.set()
        safe_log("Activity Engine STOP.")


# ------------------------------ RECORDING ------------------------------

def record_add(event):
    with state_lock:
        macro_events.append(event)


def on_move(x, y):
    global last_rec_x, last_rec_y
    if not recording or not config.get("record_mouse", True):
        return

    threshold = max(0, int(config.get("move_threshold", 4)))
    if abs(x - last_rec_x) >= threshold or abs(y - last_rec_y) >= threshold:
        record_add({
            "type": "move",
            "x": int(x),
            "y": int(y),
            "time": time.perf_counter() - record_start,
        })
        last_rec_x, last_rec_y = x, y


def on_click(x, y, button, pressed):
    if not recording or not config.get("record_mouse", True):
        return

    btn = str(button).replace("Button.", "")
    record_add({
        "type": "mouse_button",
        "x": int(x),
        "y": int(y),
        "button": btn,
        "action": "down" if pressed else "up",
        "time": time.perf_counter() - record_start,
    })

    if pressed:
        with state_lock:
            stats["clicks"] += 1
        if app_instance:
            app_instance.update_stats()


def on_scroll(x, y, dx, dy):
    if not recording or not config.get("record_scroll", True):
        return

    record_add({
        "type": "scroll",
        "x": int(x),
        "y": int(y),
        "dx": int(dx),
        "dy": int(dy),
        "time": time.perf_counter() - record_start,
    })


def serialize_key(key):
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return {"kind": "char", "value": key.char}
        return {"kind": "vk", "value": key.vk}

    name = str(key)
    if name.startswith("Key."):
        name = name[4:]
    return {"kind": "special", "value": name}


def deserialize_key(data):
    kind = data.get("kind")
    value = data.get("value")

    if kind == "char":
        return value
    if kind == "vk":
        try:
            return keyboard.KeyCode.from_vk(int(value))
        except Exception:
            return None
    if kind == "special":
        return getattr(keyboard.Key, str(value), None)
    return None


def on_press(key):
    # F8 is reserved as a global emergency stop and is never recorded.
    if key == keyboard.Key.f8:
        emergency_stop()
        return

    if recording and key == keyboard.Key.esc:
        record_stop.set()
        return False

    if recording and config.get("record_keyboard", True):
        record_add({
            "type": "key_down",
            "key": serialize_key(key),
            "time": time.perf_counter() - record_start,
        })
        with state_lock:
            stats["keys"] += 1
        if app_instance:
            app_instance.update_stats()


def on_release(key):
    if recording and key != keyboard.Key.esc and key != keyboard.Key.f8 and config.get("record_keyboard", True):
        record_add({
            "type": "key_up",
            "key": serialize_key(key),
            "time": time.perf_counter() - record_start,
        })


def record_macro_worker():
    global recording, record_start, macro_events
    global mouse_listener, keyboard_listener, last_rec_x, last_rec_y

    with state_lock:
        macro_events = []

    record_stop.clear()
    recording = True
    record_start = time.perf_counter()
    x, y = pyautogui.position()
    last_rec_x, last_rec_y = x, y

    safe_log("RECORDING ACTIVE | ESC or F8 = stop")

    mouse_listener = mouse.Listener(
        on_move=on_move,
        on_click=on_click,
        on_scroll=on_scroll,
    )
    keyboard_listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release,
    )

    mouse_listener.start()
    keyboard_listener.start()
    record_stop.wait()
    recording = False

    try:
        mouse_listener.stop()
    except Exception:
        pass
    try:
        keyboard_listener.stop()
    except Exception:
        pass

    with state_lock:
        events = list(macro_events)

    try:
        with open(MACRO_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        safe_log(f"Macro saved | {len(events)} events")
    except Exception as exc:
        safe_log(f"Macro save error: {exc}")

    if app_instance:
        app_instance.after(0, app_instance.reset_record_ui)


# ------------------------------ PLAYBACK ------------------------------

def play_macro_worker():
    global playing

    if not os.path.exists(MACRO_FILE):
        safe_log("No macro file found. Record a macro first.")
        if app_instance:
            app_instance.after(0, app_instance.reset_play_ui)
        return

    try:
        with open(MACRO_FILE, "r", encoding="utf-8") as f:
            events = json.load(f)
    except Exception as exc:
        safe_log(f"Macro read error: {exc}")
        if app_instance:
            app_instance.after(0, app_instance.reset_play_ui)
        return

    if not events:
        safe_log("Macro is empty.")
        if app_instance:
            app_instance.after(0, app_instance.reset_play_ui)
        return

    try:
        speed = max(0.05, float(config["playback_speed"]))
        loops = max(1, int(config["playback_loops"]))
    except Exception:
        speed, loops = 1.0, 1

    playing = True
    play_stop.clear()
    safe_log(f"PLAYBACK START | speed={speed:g}x | loops={loops}")

    pressed_keys = []
    try:
        for loop_no in range(loops):
            if play_stop.is_set():
                break

            previous_time = 0.0
            for event in events:
                if play_stop.is_set():
                    break

                event_time = max(0.0, float(event.get("time", 0.0)))
                delay = max(0.0, (event_time - previous_time) / speed)
                if play_stop.wait(delay):
                    break

                event_type = event.get("type")
                try:
                    if event_type == "move":
                        pyautogui.moveTo(int(event["x"]), int(event["y"]), duration=0)
                        with state_lock:
                            stats["moves"] += 1

                    elif event_type == "mouse_button":
                        button = event.get("button", "left")
                        x = int(event.get("x", pyautogui.position().x))
                        y = int(event.get("y", pyautogui.position().y))
                        if event.get("action") == "down":
                            pyautogui.mouseDown(x=x, y=y, button=button)
                            with state_lock:
                                stats["clicks"] += 1
                        else:
                            pyautogui.mouseUp(x=x, y=y, button=button)

                    elif event_type == "scroll":
                        pyautogui.moveTo(int(event["x"]), int(event["y"]), duration=0)
                        dx = int(event.get("dx", 0))
                        dy = int(event.get("dy", 0))
                        if dx:
                            pyautogui.hscroll(dx)
                        if dy:
                            pyautogui.scroll(dy)

                    elif event_type in ("key_down", "key_up"):
                        key_obj = deserialize_key(event.get("key", {}))
                        if key_obj is not None:
                            if event_type == "key_down":
                                play_keyboard.press(key_obj)
                                pressed_keys.append(key_obj)
                            else:
                                play_keyboard.release(key_obj)
                                if key_obj in pressed_keys:
                                    pressed_keys.remove(key_obj)

                    # Backward compatibility with old macro files.
                    elif event_type == "keypress":
                        raw = event.get("key", "")
                        if raw.startswith("Key."):
                            key_obj = getattr(keyboard.Key, raw[4:], None)
                        elif len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
                            key_obj = raw[1:-1]
                        else:
                            key_obj = raw
                        if key_obj:
                            play_keyboard.press(key_obj)
                            play_keyboard.release(key_obj)

                except pyautogui.FailSafeException:
                    safe_log("FAIL-SAFE triggered. Playback stopped.")
                    play_stop.set()
                    break
                except Exception as exc:
                    safe_log(f"Playback event error [{event_type}]: {exc}")

                previous_time = event_time

            if not play_stop.is_set():
                with state_lock:
                    stats["macro_runs"] += 1
                if app_instance:
                    app_instance.update_stats()
                    app_instance.log_event(f"Loop completed {loop_no + 1}/{loops}")

    finally:
        for key_obj in reversed(pressed_keys):
            try:
                play_keyboard.release(key_obj)
            except Exception:
                pass

        playing = False
        if app_instance:
            app_instance.after(0, app_instance.reset_play_ui)
        safe_log("PLAYBACK STOP.")


# ------------------------------ EMERGENCY STOP ------------------------------

def emergency_stop():
    afK_stop.set()
    record_stop.set()
    play_stop.set()
    safe_log("EMERGENCY STOP | F8")
    if app_instance:
        app_instance.after(0, app_instance.emergency_ui_reset)


def start_hotkey_listener():
    global hotkey_listener

    def hotkey_press(key):
        if key == keyboard.Key.f8:
            emergency_stop()

    hotkey_listener = keyboard.Listener(on_press=hotkey_press)
    hotkey_listener.daemon = True
    hotkey_listener.start()


# ------------------------------ UI ------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG = "#05070D"
SIDEBAR = "#070A12"
PANEL = "#0B1020"
PANEL_ALT = "#0A0F1A"
CARD = "#0D1426"
INPUT = "#080D18"
BORDER = "#1A2944"
CYAN = "#00F0FF"
PURPLE = "#9D4EDD"
MAGENTA = "#FF3CAC"
GREEN = "#39FF88"
RED = "#FF4D6D"
YELLOW = "#FFD166"
TEXT = "#F4F7FF"
MUTED = "#7F8BA5"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        global app_instance
        app_instance = self
        self.title('NEONSHIFT X — Macro & Activity Engine')
        self.geometry('1180x740')
        self.minsize(1040, 680)
        self.configure(fg_color=BG)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.build_header()
        self.build_sidebar()
        self.pages = {}
        self.build_dashboard()
        self.build_controls()
        self.build_manager()
        self.build_about()
        self.build_statistics()
        footer = ctk.CTkFrame(self, fg_color='#060C18', height=26, corner_radius=0)
        footer.grid(row=2, column=0, columnspan=2, sticky='ew')
        ctk.CTkLabel(footer, text='PLAY SMART. STAY ACTIVE.', text_color=CYAN, font=('Consolas', 11)).pack(side='left', padx=16)
        ctk.CTkLabel(footer, text='v2.0  |  By Swir  |  Keep Gaming!  ♡', text_color=MUTED, font=('Segoe UI', 11)).pack(side='right', padx=16)
        self.show_page('Dashboard')
        self.log_event('NeonShift X started. Welcome!')
        self.log_event('Ready. Choose a module to begin. F8 stops all actions.')
        self.update_stats()
        self.refresh_status()
        start_hotkey_listener()

    def build_header(self):
        from PIL import ImageTk, ImageOps
        self.hero_source = Image.open(HERO_FILE).convert('RGB') if os.path.exists(HERO_FILE) else None
        canvas = tk.Canvas(self, height=170, bg=BG, highlightthickness=0)
        canvas.grid(row=0, column=0, columnspan=2, sticky='ew')
        def draw(event):
            w = event.width
            canvas.delete('all')
            if self.hero_source:
                self.hero_photo = ImageTk.PhotoImage(ImageOps.fit(self.hero_source, (w, 170)))
                canvas.create_image(0, 0, anchor='nw', image=self.hero_photo)
            canvas.create_text(25, 58, anchor='w', text='NEON', fill=CYAN, font=('Arial', 31, 'bold italic'))
            canvas.create_text(150, 58, anchor='w', text='SHIFT', fill='#E746F5', font=('Arial', 31, 'bold italic'))
            canvas.create_text(290, 58, anchor='w', text='X', fill='#13BFFF', font=('Arial', 43, 'bold italic'))
            canvas.create_text(30, 96, anchor='w', text='M A C R O  &  A C T I V I T Y  E N G I N E', fill='#BD9CFF', font=('Segoe UI', 9))
            canvas.create_text(30, 118, anchor='w', text='PLAY SMART. STAY ACTIVE.', fill=CYAN, font=('Consolas', 11, 'bold'))
            canvas.create_line(0, 169, w, 169, fill='#17698C')
        canvas.bind('<Configure>', draw)

    def build_sidebar(self):
        side = ctk.CTkFrame(self, width=198, corner_radius=0, fg_color='#040914', border_width=1, border_color=BORDER)
        side.grid(row=1, column=0, sticky='nsew')
        side.grid_propagate(False)
        self.nav = {}
        for name, icon in [('Dashboard','⌂'), ('Activity Engine','ϟ'), ('Macro Recorder','◉'), ('Playback','▷'), ('Macro Manager','▤'), ('Settings','⚙'), ('Statistics','▥'), ('About','ⓘ')]:
            b = ctk.CTkButton(side, text=f'{icon}    {name}', anchor='w', height=44, corner_radius=7, fg_color='transparent', hover_color='#10243A', text_color='#C6CCED', font=('Segoe UI',14), command=lambda n=name:self.show_page(n))
            b.pack(fill='x', padx=12, pady=(12 if name=='Dashboard' else 3, 3))
            self.nav[name] = b

    def page(self, name):
        p = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        p.grid(row=1, column=1, sticky='nsew', padx=14, pady=12)
        self.pages[name] = p
        return p

    def show_page(self, name):
        for p in self.pages.values():
            p.grid_remove()
        self.pages[name].grid()
        for n,b in self.nav.items():
            b.configure(fg_color='#0C1B30' if n==name else 'transparent', text_color=CYAN if n==name else '#C6CCED')
        if name=='Macro Manager':
            self.refresh_macros()

    def panel(self, parent, accent=BORDER):
        return ctk.CTkFrame(parent, fg_color='#060E19', corner_radius=9, border_width=1, border_color=accent)

    def build_dashboard(self):
        p = self.page('Dashboard')
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(2, weight=1)
        cards = ctk.CTkFrame(p, fg_color='transparent')
        cards.grid(row=0, column=0, sticky='ew')
        self.switches = []
        for i,(title,desc,icon,color,command) in enumerate([
            ('ACTIVITY ENGINE','Keep you active\nCustom movement patterns','➤',CYAN,lambda:self.stop_afk() if afK_running else self.start_afk()),
            ('RECORD MACRO','Capture mouse & keyboard\nSave your actions','●',RED,lambda:self.stop_record() if recording else self.start_record()),
            ('PLAYBACK MACRO','Run your macro\nLoops & speed control','▶',CYAN,lambda:self.stop_play() if playing else self.start_play()),
            ('EMERGENCY STOP','Stop everything instantly\n(Hotkey: F8)','⚠',RED,emergency_stop)]):
            cards.grid_columnconfigure(i, weight=1, uniform='cards')
            card = self.panel(cards, '#166884' if i!=3 else '#813655')
            card.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 5,0),pady=(0,8))
            ctk.CTkLabel(card,text=icon,text_color=color,font=('Segoe UI Symbol',40),height=66).pack(pady=(8,0))
            ctk.CTkLabel(card,text=title,text_color=color,font=('Segoe UI',14,'bold')).pack()
            ctk.CTkLabel(card,text=desc,text_color='#BDCAE7',font=('Segoe UI',11),height=40).pack(padx=7)
            if i<3:
                sw=ctk.CTkSwitch(card,text='OFF',width=78,progress_color=color,button_color='#A8B9ED',fg_color='#172439',command=command,font=('Segoe UI',10))
                sw.pack(pady=(7,14))
                self.switches.append(sw)
            else:
                ctk.CTkButton(card,text='STOP ALL',command=command,fg_color='#D71152',hover_color='#F52969',height=30,width=150,font=('Segoe UI',12,'bold')).pack(pady=(7,14))
        middle=ctk.CTkFrame(p,fg_color='transparent')
        middle.grid(row=1,column=0,sticky='ew',pady=(0,8))
        middle.grid_columnconfigure(0,weight=2)
        middle.grid_columnconfigure(1,weight=1)
        telemetry=self.panel(middle)
        telemetry.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        ctk.CTkLabel(telemetry,text='Live Statistics',text_color=CYAN).pack(anchor='w',padx=12,pady=5)
        row=ctk.CTkFrame(telemetry,fg_color='transparent')
        row.pack(fill='x',padx=8,pady=(4,16))
        for i,(attr,label,icon,color) in enumerate([('card_moves','Moves','➤',CYAN),('card_clicks','Clicks','♧','#55BAFF'),('card_keys','Keys','⌨',CYAN),('card_runs','Macro Runs','⟳','#E34EFA'),('card_pulses','AFK Pulses','ϟ','#E34EFA')]):
            row.grid_columnconfigure(i,weight=1,uniform='stat')
            f=ctk.CTkFrame(row,fg_color='transparent')
            f.grid(row=0,column=i,sticky='ew')
            ctk.CTkLabel(f,text=icon,text_color=color,font=('Segoe UI Symbol',26)).pack()
            value=ctk.CTkLabel(f,text='0',text_color='#B7EDFF',font=('Segoe UI',20))
            value.pack()
            setattr(self,attr,value)
            ctk.CTkLabel(f,text=label,text_color='#BDCAE7',font=('Segoe UI',10)).pack()
        status=self.panel(middle)
        status.grid(row=0,column=1,sticky='nsew')
        ctk.CTkLabel(status,text='Status',text_color=CYAN).pack(anchor='w',padx=12,pady=(5,2))
        self.status_labels=[]
        for title in ['Activity Engine','Recording','Playback']:
            l=ctk.CTkLabel(status,text=f'●  {title}     Stopped',font=('Segoe UI',11),text_color=MUTED)
            l.pack(anchor='w',padx=12)
            self.status_labels.append(l)
        ctk.CTkLabel(status,text='F8 · Emergency Stop   |   ESC · Stop Recording',font=('Segoe UI',9),text_color='#B4C4E8').pack(padx=10,pady=5)
        log=self.panel(p)
        log.grid(row=2,column=0,sticky='nsew')
        log.grid_columnconfigure(0,weight=1)
        log.grid_rowconfigure(1,weight=1)
        ctk.CTkLabel(log,text='Event Log',text_color='#B4C4E8').grid(row=0,column=0,sticky='w',padx=12)
        ctk.CTkButton(log,text='Clear',width=65,height=25,fg_color='#222B50',command=self.clear_console).grid(row=0,column=1,padx=8,pady=6)
        self.console=ctk.CTkTextbox(log,fg_color='#060E19',text_color='#BDCAE7',font=('Consolas',11),height=80)
        self.console.grid(row=1,column=0,columnspan=2,sticky='nsew',padx=7,pady=(0,7))

    def heading(self,p,title,subtitle,color=CYAN):
        ctk.CTkLabel(p,text=title,text_color=color,font=('Segoe UI',25,'bold')).pack(anchor='w',padx=20,pady=(15,3))
        ctk.CTkLabel(p,text=subtitle,text_color=MUTED,font=('Segoe UI',12)).pack(anchor='w',padx=20,pady=(0,15))

    def setting(self,p,label,value):
        row=ctk.CTkFrame(p,fg_color='transparent')
        row.pack(fill='x',padx=20,pady=6)
        ctk.CTkLabel(row,text=label,text_color='#BDCAE7').pack(side='left')
        e=ctk.CTkEntry(row,width=150,height=32,fg_color=INPUT,border_color='#254566')
        e.insert(0,str(value))
        e.pack(side='right')
        return e

    def check(self,p,text,value):
        var=tk.BooleanVar(value=value)
        c=ctk.CTkCheckBox(p,text=text,variable=var,fg_color=CYAN,text_color=TEXT)
        c.pack(anchor='w',padx=20,pady=9)
        c._bool_var=var
        return c

    def action_button(self,p,text,command,color=CYAN):
        b=ctk.CTkButton(p,text=text,command=command,height=38,fg_color=color,hover_color='#245575',text_color=BG if color==CYAN else TEXT)
        b.pack(fill='x',padx=20,pady=6)
        return b

    def build_controls(self):
        p=self.page('Activity Engine')
        self.heading(p,'ϟ  Activity Engine','Smart movement patterns. Your timing, your range.')
        self.afk_mode=ctk.CTkOptionMenu(p,values=['Move & Return','Drift','Micro Jitter'],fg_color='#142944',button_color='#245575')
        self.afk_mode.set(config['afk_mode'])
        self.afk_mode.pack(anchor='w',padx=20,pady=8)
        for attr,label,key in [('entry_afk_min','Min interval (seconds)','afk_min_interval'),('entry_afk_max','Max interval (seconds)','afk_max_interval'),('entry_move_min','Min movement (pixels)','afk_min_move'),('entry_move_max','Max movement (pixels)','afk_max_move')]:
            setattr(self,attr,self.setting(p,label,config[key]))
        self.btn_afk_start=self.action_button(p,'Start Activity',self.start_afk)
        self.btn_afk_stop=self.action_button(p,'Stop',self.stop_afk,'#283154')
        p=self.page('Macro Recorder')
        self.heading(p,'◉  Macro Recorder','Capture your actions. Press ESC to finish recording.',RED)
        self.chk_mouse=self.check(p,'Record mouse movement & clicks',config['record_mouse'])
        self.chk_keyboard=self.check(p,'Record keyboard (key down / up)',config['record_keyboard'])
        self.chk_scroll=self.check(p,'Record scroll events',config['record_scroll'])
        self.entry_threshold=self.setting(p,'Move threshold (pixels)',config['move_threshold'])
        self.rec_count=ctk.CTkLabel(p,text='Events captured: 0',text_color=MUTED)
        self.rec_count.pack(anchor='w',padx=20,pady=8)
        self.btn_rec=self.action_button(p,'●  RECORD MACRO',self.start_record,'#D71152')
        self.btn_rec_stop=self.action_button(p,'Stop & Save (ESC)',self.stop_record,'#283154')
        self.btn_rec_stop.configure(state='disabled')
        p=self.page('Playback')
        self.heading(p,'▷  Playback','Play the current macro with adjustable speed and repetitions.')
        ctk.CTkLabel(p,text='neonshift_macro.json',text_color=CYAN,font=('Consolas',14)).pack(anchor='w',padx=20,pady=12)
        self.entry_speed=self.setting(p,'Playback speed (×)',config['playback_speed'])
        self.entry_loops=self.setting(p,'Loop count',config['playback_loops'])
        self.btn_play=self.action_button(p,'▶  PLAY MACRO',self.start_play)
        self.btn_play_stop=self.action_button(p,'Stop Playback',self.stop_play,'#283154')
        self.btn_play_stop.configure(state='disabled')
        self.action_button(p,'Inspect Current Macro',self.analyze_macro,'#283154')
        p=self.page('Settings')
        self.heading(p,'⚙  Settings','Changes on the module pages apply when you start an engine.')
        self.action_button(p,'Save All Settings',self.save_gui_config)
        self.action_button(p,'Reset Statistics',self.reset_stats,'#283154')
        ctk.CTkLabel(p,text='F8  —  Stop all engines\nESC  —  Stop and save recording\n\nConfiguration is saved beside the program.',justify='left',text_color='#BDCAE7',font=('Segoe UI',14)).pack(anchor='w',padx=20,pady=25)

    def build_manager(self):
        p=self.page('Macro Manager')
        self.heading(p,'▤  Macro Manager','Import, export and inspect your current macro.')
        self.macro_info=ctk.CTkLabel(p,text='',text_color='#BDCAE7',font=('Consolas',14),justify='left')
        self.macro_info.pack(anchor='w',padx=20,pady=20)
        self.action_button(p,'Load Macro…',self.import_macro)
        self.action_button(p,'Save Macro As…',self.export_macro,'#283154')
        self.action_button(p,'Inspect Current Macro',self.analyze_macro,'#283154')
        self.action_button(p,'Open Folder',lambda:os.startfile(BASE_DIR),'#283154')

    def refresh_macros(self):
        try:
            with open(MACRO_FILE,encoding='utf-8') as f: events=json.load(f)
            self.macro_info.configure(text=f'neonshift_macro.json\n{len(events):,} events · {max((e.get("time",0) for e in events),default=0):.1f} seconds')
        except Exception:
            self.macro_info.configure(text='No current macro. Record one or load a JSON file.')

    def import_macro(self):
        from tkinter import filedialog
        if recording or playing:
            messagebox.showinfo(APP_NAME,'Stop recording and playback before loading a macro.')
            return
        path=filedialog.askopenfilename(parent=self,filetypes=[('Macro JSON','*.json')])
        if not path:return
        try:
            with open(path,encoding='utf-8') as f: events=json.load(f)
            if not isinstance(events,list) or not all(isinstance(e,dict) and 'type' in e for e in events):
                raise ValueError('This file is not a macro event list.')
            with open(MACRO_FILE,'w',encoding='utf-8') as f:json.dump(events,f,indent=2)
            self.refresh_macros()
            self.log_event('Macro loaded: '+os.path.basename(path))
        except Exception as exc:messagebox.showerror(APP_NAME,str(exc))

    def export_macro(self):
        from tkinter import filedialog
        import shutil
        if not os.path.exists(MACRO_FILE):
            messagebox.showinfo(APP_NAME,'Record or load a macro first.')
            return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',initialfile='my_macro.json',filetypes=[('Macro JSON','*.json')])
        if path and os.path.abspath(path)!=os.path.abspath(MACRO_FILE):
            try:shutil.copy2(MACRO_FILE,path)
            except OSError as exc:messagebox.showerror(APP_NAME,str(exc))

    def build_about(self):
        p=self.page('About')
        self.heading(p,'NEONSHIFT X','Macro & Activity Engine · By Swir')
        ctk.CTkLabel(p,text='AUTOMATE.\nDOMINATE.\nSTAY ONLINE.',font=('Segoe UI',32,'bold'),text_color=CYAN,justify='left').pack(anchor='w',padx=20,pady=20)

    def build_statistics(self):
        p=self.page('Statistics')
        self.heading(p,'▥  Statistics','Live counters for this session.')
        self.statistics_values={}
        for key,title in [('moves','Mouse moves'),('clicks','Mouse clicks'),('keys','Recorded key presses'),('macro_runs','Completed macro loops'),('afk_pulses','Activity pulses')]:
            row=self.panel(p)
            row.pack(fill='x',padx=20,pady=5)
            ctk.CTkLabel(row,text=title,text_color='#BDCAE7').pack(side='left',padx=14,pady=5)
            value=ctk.CTkLabel(row,text='0',text_color=CYAN,font=('Segoe UI',20))
            value.pack(side='right',padx=14,pady=5)
            self.statistics_values[key]=value
        self.action_button(p,'Reset Statistics',self.reset_stats,'#283154')

    def refresh_status(self):
        with state_lock:
            values=dict(stats)
        for key,label in self.statistics_values.items():
            label.configure(text=f'{values[key]:,}')
        self._update_stats_safe()
        for sw,label,active,title,color in zip(self.switches,self.status_labels,[afK_running,recording,playing],['Activity Engine','Recording','Playback'],[CYAN,RED,CYAN]):
            sw.select() if active else sw.deselect()
            sw.configure(text='ON' if active else 'OFF')
            label.configure(text=f'●  {title}     {"Running" if active else "Stopped"}',text_color=color if active else MUTED)
        self.rec_count.configure(text=f'Events captured: {len(macro_events):,}')
        self.after(250,self.refresh_status)


    def log_event(self, msg):
        self.after(0, self._log_safe, msg)

    def _log_safe(self, msg):
        try:
            stamp = time.strftime("%H:%M:%S")
            self.console.insert("end", f"[{stamp}] {msg}\n")
            self.console.see("end")
        except tk.TclError:
            pass

    def update_stats(self):
        self.after(0, self._update_stats_safe)

    def _update_stats_safe(self):
        with state_lock:
            values = dict(stats)
        self.card_moves.configure(text=f"{values['moves']:,}")
        self.card_clicks.configure(text=f"{values['clicks']:,}")
        self.card_keys.configure(text=f"{values['keys']:,}")
        self.card_runs.configure(text=str(values["macro_runs"]))
        self.card_pulses.configure(text=str(values["afk_pulses"]))

    def read_config(self):
        try:
            speed = float(self.entry_speed.get().replace(",", "."))
            loops = int(self.entry_loops.get())
            amin = float(self.entry_afk_min.get().replace(",", "."))
            amax = float(self.entry_afk_max.get().replace(",", "."))
            move_min = int(self.entry_move_min.get())
            move_max = int(self.entry_move_max.get())
            threshold = int(self.entry_threshold.get())

            if speed <= 0:
                raise ValueError("Playback speed must be greater than 0.")
            if loops < 1:
                raise ValueError("Playback loops must be at least 1.")
            if amin < 0.5 or amax < amin:
                raise ValueError("Activity interval range is invalid.")
            if move_min < 1 or move_max < move_min:
                raise ValueError("Movement range is invalid.")
            if threshold < 0:
                raise ValueError("Move threshold cannot be negative.")

            config.update({
                "playback_speed": speed,
                "playback_loops": loops,
                "afk_min_interval": amin,
                "afk_max_interval": amax,
                "afk_min_move": move_min,
                "afk_max_move": move_max,
                "afk_mode": self.afk_mode.get(),
                "record_mouse": bool(self.chk_mouse._bool_var.get()),
                "record_keyboard": bool(self.chk_keyboard._bool_var.get()),
                "record_scroll": bool(self.chk_scroll._bool_var.get()),
                "move_threshold": threshold,
            })
        except ValueError as exc:
            self.log_event(f"CONFIG ERROR: {exc}")
            messagebox.showerror('Check settings', str(exc), parent=self)
            raise

    def save_gui_config(self):
        try:
            self.read_config()
            save_config()
        except ValueError:
            pass
        except Exception as exc:
            self.log_event(f"Save error: {exc}")

    def start_afk(self):
        if afK_running:
            self.log_event("Activity Engine is already running.")
            return
        try:
            self.read_config()
        except ValueError:
            return
        afK_stop.clear()
        threading.Thread(target=activity_loop, daemon=True).start()
        self.log_event("Activity Engine launched.")

    def stop_afk(self):
        afK_stop.set()
        self.log_event("Stopping Activity Engine...")

    def start_record(self):
        if recording:
            return
        if playing:
            self.log_event("Stop playback before recording.")
            return
        try:
            self.read_config()
        except ValueError:
            return

        self.btn_rec.configure(state="disabled", text="●  RECORDING...")
        self.btn_rec_stop.configure(state="normal")
        threading.Thread(target=record_macro_worker, daemon=True).start()

    def stop_record(self):
        record_stop.set()
        self.log_event("Recording stop requested.")

    def reset_record_ui(self):
        self.btn_rec.configure(state="normal", text="●  RECORD MACRO")
        self.btn_rec_stop.configure(state="disabled")

    def start_play(self):
        if playing:
            return
        if recording:
            self.log_event("Stop recording before playback.")
            return
        try:
            self.read_config()
        except ValueError:
            return

        play_stop.clear()
        self.btn_play.configure(state="disabled", text="▶  PLAYING...")
        self.btn_play_stop.configure(state="normal")
        threading.Thread(target=play_macro_worker, daemon=True).start()

    def stop_play(self):
        play_stop.set()
        self.log_event("Playback stop requested.")

    def reset_play_ui(self):
        self.btn_play.configure(state="normal", text="▶  PLAY MACRO")
        self.btn_play_stop.configure(state="disabled")

    def emergency_ui_reset(self):
        self.reset_record_ui()
        self.reset_play_ui()

    def analyze_macro(self):
        if not os.path.exists(MACRO_FILE):
            self.log_event("No macro file found.")
            return

        try:
            with open(MACRO_FILE, "r", encoding="utf-8") as f:
                events = json.load(f)
            if not events:
                self.log_event("Macro is empty.")
                return

            moves = sum(e.get("type") == "move" for e in events)
            clicks = sum(
                e.get("type") == "mouse_button" and e.get("action") == "down"
                for e in events
            )
            key_down = sum(e.get("type") in ("key_down", "keypress") for e in events)
            key_up = sum(e.get("type") == "key_up" for e in events)
            scrolls = sum(e.get("type") == "scroll" for e in events)
            duration = max(float(e.get("time", 0.0)) for e in events)

            self.log_event(
                f"MACRO REPORT | events={len(events)} | duration={duration:.2f}s | "
                f"moves={moves} | clicks={clicks} | key-down={key_down} | "
                f"key-up={key_up} | scroll={scrolls}"
            )
        except Exception as exc:
            self.log_event(f"Macro analysis error: {exc}")

    def reset_stats(self):
        with state_lock:
            stats.update({
                "moves": 0, "clicks": 0, "keys": 0,
                "macro_runs": 0, "afk_pulses": 0,
            })
        self.update_stats()
        self.log_event("Telemetry reset.")

    def clear_console(self):
        self.console.delete("1.0", "end")
        self.log_event("Console cleared.")

    def on_close(self):
        afK_stop.set()
        record_stop.set()
        play_stop.set()

        for listener in (mouse_listener, keyboard_listener, hotkey_listener):
            try:
                if listener:
                    listener.stop()
            except Exception:
                pass
        self.destroy()


def main():
    load_config()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        error = traceback.format_exc()
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(f"{APP_NAME} error", error)
        root.destroy()
