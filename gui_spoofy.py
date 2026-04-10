import asyncio
import threading
import json
import os
import re
import queue
import urllib.request
import urllib.parse
import customtkinter as ctk
from datetime import datetime, timedelta
from geopy.distance import geodesic

# 從原本的檔案只匯入取得連線的方法與設定
from spoofy import get_device_provider, load_config


class GUISpoofy:
    """專為 GUI 設計的 Spoofer，移除所有 input() 與終端機監聽"""

    def __init__(self, provider, is_ios17, log_callback):
        self.provider = provider
        self.is_ios17 = is_ios17
        self.log = log_callback

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
                    self.log(f"🚀 成功定位至座標: 緯度 {lat}, 經度 {lng}")
                    self.log(
                        "🔒 定位已鎖定 (iPhone 不會亂跳)。\n若要解除或更改，請直接點擊其他按鈕或停止。"
                    )
                    # 使用 sleep 取代 input，保持 async with 不結束
                    await asyncio.sleep(86400)
            else:
                from pymobiledevice3.services.simulate_location import (
                    DtSimulateLocation,
                )

                service = DtSimulateLocation(self.provider)
                await service.set(lat, lng)
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

                    # 每 3 秒印一次日誌
                    if int(elapsed) % 3 == 0:
                        self.log(
                            f"進度 {current_dist / total_dist * 100:.1f}% | 當前: {cur_lat:.5f}, {cur_lng:.5f}"
                        )
                    break
                acc_dist += seg_dist

            await asyncio.sleep(1)

        await loc_service.set(path[-1][0], path[-1][1])
        self.log(f"進度 100.0% | 當前: {path[-1][0]:.5f}, {path[-1][1]:.5f}")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Spoofy GUI - iPhone 定位模擬器")
        self.geometry("700x600")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 狀態變數
        self.loop = None
        self.spoofer = None
        self.current_task = None
        self.start_coords, self.end_coords, self.default_speed, self.frequent_locations = load_config()
        self.log_queue = queue.Queue()

        # UI 佈局
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

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
        self.control_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.home_btn = ctk.CTkButton(
            self.control_frame,
            text="🏠 前往起點",
            command=self.go_home,
            state="disabled",
        )
        self.home_btn.grid(row=0, column=0, padx=10, pady=10)

        self.comp_btn = ctk.CTkButton(
            self.control_frame,
            text="🏢 前往終點",
            command=self.go_company,
            state="disabled",
        )
        self.comp_btn.grid(row=0, column=1, padx=10, pady=10)

        self.stop_btn = ctk.CTkButton(
            self.control_frame,
            text="🛑 停止動作",
            fg_color="indianred",
            hover_color="darkred",
            command=self.stop_action,
            state="disabled",
        )
        self.stop_btn.grid(row=0, column=2, padx=10, pady=10)

        self.coord_entry = ctk.CTkEntry(
            self.control_frame,
            placeholder_text="貼上座標 (例如: 25.0339, 121.5644)",
            width=400,
        )
        self.coord_entry.grid(row=1, column=0, columnspan=2, padx=10, pady=10)

        self.teleport_btn = ctk.CTkButton(
            self.control_frame,
            text="🚀 瞬間移動",
            command=self.manual_teleport,
            state="disabled",
        )
        self.teleport_btn.grid(row=1, column=2, padx=10, pady=10)

        self.speed_label = ctk.CTkLabel(
            self.control_frame, text=f"時速: {self.default_speed} km/h"
        )
        self.speed_label.grid(row=2, column=0, padx=10, pady=0)

        self.speed_slider = ctk.CTkSlider(
            self.control_frame,
            from_=1,
            to=100,
            number_of_steps=99,
            command=self.update_speed_label,
        )
        self.speed_slider.set(self.default_speed)
        self.speed_slider.grid(row=2, column=1, padx=10, pady=0)

        self.walk_btn = ctk.CTkButton(
            self.control_frame,
            text="🚶 開始行走 (到點)",
            command=self.start_walk,
            state="disabled",
        )
        self.walk_btn.grid(row=2, column=2, padx=10, pady=10)

        # 3. 常用地點選單
        self.freq_label = ctk.CTkLabel(self.control_frame, text="📍 常用地點:")
        self.freq_label.grid(row=3, column=0, padx=10, pady=10)

        self.freq_options = (
            [loc["name"] for loc in self.frequent_locations]
            if self.frequent_locations
            else ["尚無常用地點"]
        )
        self.freq_menu = ctk.CTkOptionMenu(
            self.control_frame,
            values=self.freq_options,
            width=250,
        )
        self.freq_menu.grid(row=3, column=1, padx=10, pady=10)

        self.freq_go_btn = ctk.CTkButton(
            self.control_frame,
            text="📍 傳送到此處",
            command=self.go_frequent,
            state="disabled",
        )
        self.freq_go_btn.grid(row=3, column=2, padx=10, pady=10)

        # 4. 日誌區域
        self.log_text = ctk.CTkTextbox(self, width=600, height=200)
        self.log_text.grid(row=4, column=0, padx=20, pady=(10, 20), sticky="nsew")
        self.log_text.insert(
            "0.0", "歡迎使用 Spoofy GUI！\n請先確認 iPhone 已連接並點擊「開始連線」。\n"
        )

        # 啟動背景事件迴圈
        self.start_async_loop()
        self.check_logs()

    # --- 非同步處理相關 ---
    def start_async_loop(self):
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

    def run_action(self, coro):
        """執行一個新的動作前，先取消掉前一個正在進行的任務 (例如取消鎖定狀態)"""
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
        self.after(100, self.check_logs)

    # --- 功能邏輯 ---
    def start_connection(self):
        self.log("正在嘗試連線至裝置...")
        self.connect_btn.configure(state="disabled", text="連線中...")

        async def connect():
            try:
                provider, is_ios17 = await get_device_provider()
                self.spoofer = GUISpoofy(provider, is_ios17, self.log)
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
        self.home_btn.configure(state="normal")
        self.comp_btn.configure(state="normal")
        self.teleport_btn.configure(state="normal")
        self.walk_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        if self.frequent_locations:
            self.freq_go_btn.configure(state="normal")

    def update_speed_label(self, value):
        self.speed_label.configure(text=f"時速: {int(value)} km/h")

    def stop_action(self):
        self.log("🛑 收到停止指令...")
        if self.current_task:
            self.loop.call_soon_threadsafe(self.current_task.cancel)
            self.current_task = None

    def go_home(self):
        if self.spoofer:
            self.log(f"🏠 準備前往常用起點...")
            self.run_action(self.spoofer.teleport(*self.start_coords))

    def go_company(self):
        if self.spoofer:
            self.log(f"🏢 準備前往常用終點...")
            self.run_action(self.spoofer.teleport(*self.end_coords))

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

    def manual_teleport(self):
        raw = self.coord_entry.get()
        coords = re.findall(r"[-+]?\d*\.\d+|\d+", raw)
        if len(coords) >= 2:
            lat, lng = float(coords[0]), float(coords[1])
            self.run_action(self.spoofer.teleport(lat, lng))
        else:
            self.log("❌ 座標格式錯誤。")

    def start_walk(self):
        raw = self.coord_entry.get()
        coords = re.findall(r"[-+]?\d*\.\d+|\d+", raw)
        if len(coords) >= 2:
            dest_coords = (float(coords[0]), float(coords[1]))
            speed = self.speed_slider.get()
            # 簡化：從常用起點走到目的地
            self.run_action(
                self.spoofer.walk(self.start_coords, dest_coords, speed_kmh=speed)
            )
        else:
            self.log("❌ 請先在輸入框貼上「終點」座標。")


if __name__ == "__main__":
    app = App()
    app.mainloop()
