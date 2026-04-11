import asyncio
import threading
import json
import os
import re
import queue
import urllib.request
import urllib.parse
import webbrowser
import customtkinter as ctk
from datetime import datetime, timedelta
from geopy.distance import geodesic

# 從原本的檔案只匯入取得連線的方法與設定
from spoofy import get_device_provider, load_config


class GUISpoofy:
    """專為 GUI 設計的 Spoofer，移除所有 input() 與終端機監聽"""

    def __init__(self, provider, is_ios17, log_callback, initial_coords):
        self.provider = provider
        self.is_ios17 = is_ios17
        self.log = log_callback
        self.current_coords = initial_coords

    async def get_route(self, start_coords, end_coords):
        """取得兩點間的真實路徑座標點 (使用 OSRM 公開 API)"""
        start_lat, start_lng = start_coords
        end_lat, end_lng = end_coords
        url = f"http://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}?overview=full&geometries=geojson"

        try:

            def _fetch_route():
                with urllib.request.urlopen(url, timeout=10) as response:
                    return json.loads(response.read().decode())

            data = await asyncio.to_thread(_fetch_route)

            if data.get("code") == "Ok" and data.get("routes"):
                coords = data["routes"][0]["geometry"]["coordinates"]
                return [(lat, lng) for lng, lat in coords]
            else:
                self.log(f"❌ 無法取得導航路徑：{data.get('message', '未知錯誤')}")
                return None
        except Exception as e:
            self.log(f"❌ 網路連線錯誤 (取得路徑失敗): {e}")
            return None

    async def teleport(self, lat, lng):
        try:
            if self.is_ios17:
                from pymobiledevice3.services.dvt.instruments.location_simulation import (
                    LocationSimulation,
                )
                from pymobiledevice3.services.dvt.instruments.dvt_provider import (
                    DvtProvider,
                )

                async with (
                    DvtProvider(self.provider) as dvt,
                    LocationSimulation(dvt) as loc,
                ):
                    await loc.set(lat, lng)
                    self.current_coords = (lat, lng)
                    self.log(f"🚀 成功定位至座標: 緯度 {lat}, 經度 {lng}")
                    self.log(
                        "🔒 定位已鎖定 (iPhone 不會亂跳)。\n若要解除或更改，請直接點擊其他按鈕或停止。"
                    )
                    await asyncio.sleep(86400)
            else:
                from pymobiledevice3.services.simulate_location import (
                    DtSimulateLocation,
                )

                service = DtSimulateLocation(self.provider)
                await service.set(lat, lng)
                self.current_coords = (lat, lng)
                self.log(f"🚀 成功定位至座標: 緯度 {lat}, 經度 {lng}")
                self.log("🔒 定位已鎖定。")
                await asyncio.sleep(86400)
        except asyncio.CancelledError:
            self.log("🛑 定位鎖定已解除。")
        except Exception as e:
            self.log(f"❌ 定位失敗: {e}")

    async def walk(self, start_coords, end_coords, speed_kmh=5.0):
        self.log("🔍 正在規劃真實道路路徑...")
        path = await self.get_route(start_coords, end_coords)

        if not path:
            self.log("⚠️ 無法取得導航路徑，將改為直線移動。")
            path = [start_coords, end_coords]

        try:
            if self.is_ios17:
                from pymobiledevice3.services.dvt.instruments.location_simulation import (
                    LocationSimulation,
                )
                from pymobiledevice3.services.dvt.instruments.dvt_provider import (
                    DvtProvider,
                )

                async with (
                    DvtProvider(self.provider) as dvt,
                    LocationSimulation(dvt) as loc,
                ):
                    await self._do_walk(loc, path, speed_kmh)
                    self.log("🏁 抵達目的地！定位鎖定中...")
                    await asyncio.sleep(86400)
            else:
                from pymobiledevice3.services.simulate_location import (
                    DtSimulateLocation,
                )

                service = DtSimulateLocation(self.provider)
                await self._do_walk(service, path, speed_kmh)
                self.log("🏁 抵達目的地！定位鎖定中...")
                await asyncio.sleep(86400)
        except asyncio.CancelledError:
            self.log("🛑 導航已中斷！")
        except Exception as e:
            self.log(f"❌ 行走過程中發生錯誤: {e}")

    async def _do_walk(self, loc_service, path, speed_kmh):
        speed_ms = speed_kmh / 3.6
        segments = []
        total_dist = 0
        for i in range(len(path) - 1):
            d = geodesic(path[i], path[i + 1]).meters
            segments.append(d)
            total_dist += d

        if total_dist == 0:
            return

        total_time = total_dist / speed_ms
        finish_time = datetime.now() + timedelta(seconds=total_time)
        self.log(f"🚶 開始導航！路徑距離: {total_dist:.2f} 公尺")
        self.log(f"🏁 預計結束時間：{finish_time.strftime('%H:%M:%S')}")

        current_dist = 0
        start_time = asyncio.get_event_loop().time()

        while current_dist < total_dist:
            elapsed = asyncio.get_event_loop().time() - start_time
            current_dist = elapsed * speed_ms

            if current_dist >= total_dist:
                break

            acc_dist = 0
            for i, seg_dist in enumerate(segments):
                if acc_dist + seg_dist >= current_dist:
                    ratio = (
                        (current_dist - acc_dist) / seg_dist if seg_dist > 0 else 1.0
                    )
                    p1, p2 = path[i], path[i + 1]
                    cur_lat = p1[0] + (p2[0] - p1[0]) * ratio
                    cur_lng = p1[1] + (p2[1] - p1[1]) * ratio
                    await loc_service.set(cur_lat, cur_lng)
                    self.current_coords = (cur_lat, cur_lng)

                    if int(elapsed) % 3 == 0:
                        self.log(
                            f"進度 {current_dist / total_dist * 100:.1f}% | 當前: {cur_lat:.5f}, {cur_lng:.5f}"
                        )
                    break
                acc_dist += seg_dist

            await asyncio.sleep(1)

        await loc_service.set(path[-1][0], path[-1][1])
        self.current_coords = (path[-1][0], path[-1][1])
        self.log(f"進度 100.0% | 當前: {path[-1][0]:.5f}, {path[-1][1]:.5f}")

    def preview_route(self, start_coords, end_coords):
        """在瀏覽器中開啟 Google Maps 預覽路徑"""
        start_lat, start_lng = start_coords
        end_lat, end_lng = end_coords
        url = f"https://www.google.com/maps/dir/?api=1&origin={start_lat},{start_lng}&destination={end_lat},{end_lng}&travelmode=bicycling"
        self.log(f"🔗 正在開啟瀏覽器預覽路徑...")
        webbrowser.open(url)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Spoofy GUI - iPhone 定位模擬器")
        self.geometry("750x750")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 狀態變數
        self.loop = None
        self.spoofer = None
        self.current_task = None
        (
            self.start_coords,
            self.end_coords,
            self.default_speed,
            self.frequent_locations,
            self.start_data,
            self.end_data,
        ) = load_config()
        self.log_queue = queue.Queue()

        # UI 佈局
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # 1. 頂部狀態欄
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="🔌 尚未連線",
            font=("Microsoft JhengHei", 16, "bold"),
        )
        self.status_label.pack(side="left", padx=20, pady=10)

        self.connect_btn = ctk.CTkButton(
            self.status_frame, text="開始連線", command=self.start_connection
        )
        self.connect_btn.pack(side="right", padx=20, pady=10)

        # 2. 控制面板
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.control_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        start_name = (
            self.start_data["name"] if isinstance(self.start_data, dict) else "起點"
        )
        end_name = self.end_data["name"] if isinstance(self.end_data, dict) else "終點"

        self.walk_home_comp_btn = ctk.CTkButton(
            self.control_frame,
            text=f"🚶 {start_name}➔{end_name}行走",
            command=self.go_walk_home_comp,
            state="disabled",
            fg_color="seagreen",
            hover_color="darkgreen",
            width=150,
        )
        self.walk_home_comp_btn.grid(row=0, column=0, columnspan=2, padx=5, pady=10)

        self.preview_home_comp_btn = ctk.CTkButton(
            self.control_frame,
            text="🗺️ 預覽路徑",
            command=self.preview_home_comp,
            state="disabled",
            width=120,
        )
        self.preview_home_comp_btn.grid(row=0, column=2, padx=5, pady=10)

        self.stop_btn = ctk.CTkButton(
            self.control_frame,
            text="🛑 停止動作",
            fg_color="indianred",
            hover_color="darkred",
            command=self.stop_action,
            state="disabled",
            width=120,
        )
        self.stop_btn.grid(row=0, column=3, columnspan=2, padx=5, pady=10)

        self.coord_entry = ctk.CTkEntry(
            self.control_frame,
            placeholder_text="貼上座標 (例如: 25.0339, 121.5644)",
            width=300,
        )
        self.coord_entry.grid(row=1, column=0, columnspan=2, padx=5, pady=10)

        self.teleport_btn = ctk.CTkButton(
            self.control_frame,
            text="🚀 瞬間移動",
            command=self.manual_teleport,
            state="disabled",
            width=100,
        )
        self.teleport_btn.grid(row=1, column=2, padx=5, pady=10)

        self.set_start_btn = ctk.CTkButton(
            self.control_frame,
            text="📍 設為起點",
            command=self.set_as_start,
            state="disabled",
            width=100,
            fg_color="gray30",
            hover_color="gray20",
        )
        self.set_start_btn.grid(row=1, column=3, padx=5, pady=10)

        self.walk_btn = ctk.CTkButton(
            self.control_frame,
            text="🚶 導航到此處",
            command=self.start_walk,
            state="disabled",
            width=100,
        )
        self.walk_btn.grid(row=2, column=3, padx=5, pady=10)

        self.preview_custom_walk_btn = ctk.CTkButton(
            self.control_frame,
            text="🗺️ 預覽",
            command=self.preview_custom_walk,
            state="disabled",
            width=80,
        )
        self.preview_custom_walk_btn.grid(row=2, column=4, padx=5, pady=10)

        self.speed_label = ctk.CTkLabel(
            self.control_frame, text=f"時速: {self.default_speed} km/h"
        )
        self.speed_label.grid(row=3, column=0, padx=5, pady=0)

        self.speed_slider = ctk.CTkSlider(
            self.control_frame,
            from_=1,
            to=100,
            number_of_steps=99,
            command=self.update_speed_label,
        )
        self.speed_slider.set(self.default_speed)
        self.speed_slider.grid(
            row=3, column=1, columnspan=3, padx=5, pady=0, sticky="ew"
        )

        # 3. 常用地點
        ctk.CTkLabel(self.control_frame, text="📍 常用地點:").grid(
            row=4, column=0, padx=5, pady=10
        )
        self.freq_options = (
            [loc["name"] for loc in self.frequent_locations]
            if self.frequent_locations
            else ["尚無常用地點"]
        )
        self.freq_menu = ctk.CTkOptionMenu(
            self.control_frame, values=self.freq_options, width=200
        )
        self.freq_menu.grid(row=4, column=1, columnspan=2, padx=5, pady=10)
        self.freq_go_btn = ctk.CTkButton(
            self.control_frame,
            text="📍 前往常用",
            command=self.go_frequent,
            state="disabled",
        )
        self.freq_go_btn.grid(row=4, column=3, padx=5, pady=10)

        # 5. 當前座標顯示
        self.current_coord_label = ctk.CTkLabel(
            self.control_frame,
            text="📍 當前模擬位置: 尚未連線",
            font=("Microsoft JhengHei", 12, "bold"),
        )
        self.current_coord_label.grid(
            row=5, column=0, columnspan=5, padx=20, pady=5, sticky="w"
        )

        # 6. 日誌區域
        self.log_text = ctk.CTkTextbox(self, width=600, height=200)
        self.log_text.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="nsew")
        self.log_text.insert("0.0", "歡迎使用 Spoofy GUI！\n請點擊「開始連線」。\n")

        self.start_async_loop()
        self.check_logs()
        self.bind_macos_shortcuts()

    def bind_macos_shortcuts(self):
        import tkinter as tk

        # macOS 原生選單仍保留，但僅作顯示用，不掛載自定義指令，避免與元件層級的綁定衝突
        try:
            menubar = tk.Menu(self)
            edit_menu = tk.Menu(menubar, tearoff=0)
            edit_menu.add_command(label="Cut", accelerator="Cmd+X")
            edit_menu.add_command(label="Copy", accelerator="Cmd+C")
            edit_menu.add_command(label="Paste", accelerator="Cmd+V")
            edit_menu.add_command(label="Select All", accelerator="Cmd+A")
            menubar.add_cascade(label="Edit", menu=edit_menu)
            self.config(menu=menubar)
        except Exception as e:
            self.log(f"系統選單建立失敗: {e}")

        # 核心剪貼簿與選取處理函式
        def handle_cut(event):
            event.widget.event_generate("<<Cut>>")
            return "break"

        def handle_copy(event):
            event.widget.event_generate("<<Copy>>")
            return "break"

        def handle_paste(event):
            event.widget.event_generate("<<Paste>>")
            return "break"

        def handle_select_all(event):
            event.widget.event_generate("<<SelectAll>>")
            return "break"

        def handle_cmd_backspace(event):
            try:
                if hasattr(event.widget, "delete"):
                    event.widget.delete(0, "end")
                return "break"
            except:
                pass

        # === 精準綁定：只綁定到特定的輸入框，避免全域 (bind_all) 帶來的重複或遺失問題 ===
        entries = [self.coord_entry]
        for entry in entries:
            # 為了保險，同時綁定 Command 和 Meta，因為 Tkinter 在不同 macOS 版本下識別可能不同
            entry.bind("<Command-x>", handle_cut)
            entry.bind("<Command-c>", handle_copy)
            entry.bind("<Command-v>", handle_paste)
            entry.bind("<Command-a>", handle_select_all)
            entry.bind("<Command-BackSpace>", handle_cmd_backspace)

            entry.bind("<Meta-x>", handle_cut)
            entry.bind("<Meta-c>", handle_copy)
            entry.bind("<Meta-v>", handle_paste)
            entry.bind("<Meta-a>", handle_select_all)
            entry.bind("<Meta-BackSpace>", handle_cmd_backspace)

        # 針對輸入框增加右鍵選單
        def show_menu(event):
            m = tk.Menu(self, tearoff=0)
            m.add_command(
                label="貼上", command=lambda: event.widget.event_generate("<<Paste>>")
            )
            m.tk_popup(event.x_root, event.y_root)

        self.coord_entry.bind(
            "<Button-2>" if os.name == "posix" else "<Button-3>", show_menu
        )

    def start_async_loop(self):
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        threading.Thread(target=run_loop, daemon=True).start()

    def run_action(self, coro):
        if self.current_task:
            self.loop.call_soon_threadsafe(self.current_task.cancel)

        async def wrapped():
            try:
                await coro
            except asyncio.CancelledError:
                pass

        self.current_task = asyncio.run_coroutine_threadsafe(wrapped(), self.loop)

    def log(self, message):
        self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")

    def check_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_text.insert("end", msg)
            self.log_text.see("end")

        if self.spoofer and hasattr(self.spoofer, "current_coords"):
            lat, lng = self.spoofer.current_coords
            self.current_coord_label.configure(
                text=f"📍 當前模擬位置: {lat:.6f}, {lng:.6f}"
            )
        self.after(100, self.check_logs)

    def start_connection(self):
        self.log("正在嘗試連線至裝置...")
        self.connect_btn.configure(state="disabled", text="連線中...")

        async def connect():
            try:
                provider, is_ios17 = await get_device_provider()
                self.spoofer = GUISpoofy(
                    provider, is_ios17, self.log, self.start_coords
                )
                self.after(0, self.on_connected)
                self.log(f"✅ 連線成功 (iOS 17+: {is_ios17})")
            except Exception as e:
                self.log(f"❌ 連線失敗: {e}")
                self.after(
                    0,
                    lambda: self.connect_btn.configure(state="normal", text="開始連線"),
                )

        asyncio.run_coroutine_threadsafe(connect(), self.loop)

    def on_connected(self):
        self.status_label.configure(text="🟢 已連線", text_color="green")
        self.connect_btn.configure(text="重新連線", state="normal")
        for btn in [
            self.walk_home_comp_btn,
            self.preview_home_comp_btn,
            self.teleport_btn,
            self.set_start_btn,
            self.walk_btn,
            self.preview_custom_walk_btn,
            self.stop_btn,
        ]:
            btn.configure(state="normal")
        if self.frequent_locations:
            self.freq_go_btn.configure(state="normal")

    def update_speed_label(self, value):
        self.speed_label.configure(text=f"時速: {int(value)} km/h")

    def stop_action(self):
        self.log("🛑 收到停止指令...")
        if self.current_task:
            self.loop.call_soon_threadsafe(self.current_task.cancel)
            self.current_task = None

    def go_walk_home_comp(self):
        if self.spoofer:
            speed = self.speed_slider.get()
            start_name = (
                self.start_data["name"] if isinstance(self.start_data, dict) else "起點"
            )
            end_name = (
                self.end_data["name"] if isinstance(self.end_data, dict) else "終點"
            )
            self.log(
                f"🚶 準備從 {start_name} 行走至 {end_name} (時速 {int(speed)} km/h)..."
            )
            self.run_action(
                self.spoofer.walk(self.start_coords, self.end_coords, speed_kmh=speed)
            )

    def preview_home_comp(self):
        if self.spoofer:
            self.spoofer.preview_route(self.start_coords, self.end_coords)

    def go_frequent(self):
        if not self.spoofer or not self.frequent_locations:
            return
        selected_name = self.freq_menu.get()
        target = next(
            (loc for loc in self.frequent_locations if loc["name"] == selected_name),
            None,
        )
        if target:
            self.log(f"📍 準備前往常用地點: {target['name']}...")
            self.run_action(self.spoofer.teleport(*target["coords"]))

    def set_as_start(self):
        if not self.spoofer:
            return
        raw = self.coord_entry.get()
        coords = re.findall(r"[-+]?\d*\.\d+|\d+", raw)
        if len(coords) >= 2:
            lat, lng = float(coords[0]), float(coords[1])
            self.spoofer.current_coords = (lat, lng)
            self.log(f"📍 起點已更新為: {lat}, {lng} (尚未執行瞬間移動)")
        else:
            self.log("❌ 請先在輸入框貼上「起點」座標。")

    def manual_teleport(self):
        raw = self.coord_entry.get()
        coords = re.findall(r"[-+]?\d*\.\d+|\d+", raw)
        if len(coords) >= 2:
            self.run_action(self.spoofer.teleport(float(coords[0]), float(coords[1])))
        else:
            self.log("❌ 座標格式錯誤。")

    def start_walk(self):
        raw = self.coord_entry.get()
        coords = re.findall(r"[-+]?\d*\.\d+|\d+", raw)
        if len(coords) >= 4:
            # 支援同時貼上起點與終點
            start = (float(coords[0]), float(coords[1]))
            dest = (float(coords[2]), float(coords[3]))
            self.log(f"🚶 偵測到起點與終點，將從 {start} 開始導航...")
            self.run_action(
                self.spoofer.walk(start, dest, speed_kmh=self.speed_slider.get())
            )
        elif len(coords) >= 2:
            dest = (float(coords[0]), float(coords[1]))
            self.run_action(
                self.spoofer.walk(
                    self.spoofer.current_coords, dest, speed_kmh=self.speed_slider.get()
                )
            )
        else:
            self.log("❌ 請先在輸入框貼上「終點」座標。")

    def preview_custom_walk(self):
        if not self.spoofer:
            return
        raw = self.coord_entry.get()
        coords = re.findall(r"[-+]?\d*\.\d+|\d+", raw)
        if len(coords) >= 2:
            dest = (float(coords[0]), float(coords[1]))
            self.spoofer.preview_route(self.spoofer.current_coords, dest)
        else:
            self.log("❌ 請先在輸入框貼上「終點」座標以進行預覽。")


if __name__ == "__main__":
    App().mainloop()
