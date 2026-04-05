import asyncio
import threading
import json
import os
import re
import queue
import customtkinter as ctk
from datetime import datetime, timedelta
from geopy.distance import geodesic

# 從原本的檔案只匯入取得連線的方法與設定
from spoofy import get_device_provider, load_config

class GUISpoofer:
    """專為 GUI 設計的 Spoofer，移除所有 input() 與終端機監聽"""
    def __init__(self, provider, is_ios17, log_callback):
        self.provider = provider
        self.is_ios17 = is_ios17
        self.log = log_callback

    async def teleport(self, lat, lng):
        try:
            if self.is_ios17:
                from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
                from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
                async with DvtProvider(self.provider) as dvt, LocationSimulation(dvt) as loc:
                    await loc.set(lat, lng)
                    self.log(f"🚀 成功定位至座標: 緯度 {lat}, 經度 {lng}")
                    self.log("🔒 定位已鎖定 (iPhone 不會亂跳)。\n若要解除或更改，請直接點擊其他按鈕或停止。")
                    # 使用 sleep 取代 input，保持 async with 不結束
                    await asyncio.sleep(86400) 
            else:
                from pymobiledevice3.services.simulate_location import DtSimulateLocation
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
        start_lat, start_lng = start_coords
        end_lat, end_lng = end_coords
        speed_ms = speed_kmh / 3.6
        total_distance = geodesic(start_coords, end_coords).meters
        if total_distance == 0:
            self.log("A 點和 B 點相同！")
            return

        total_time_seconds = total_distance / speed_ms
        steps = int(total_time_seconds)
        finish_time = datetime.now() + timedelta(seconds=total_time_seconds)

        self.log(f"🚶 開始導航！總距離: {total_distance:.2f} 公尺, 預計耗時: {total_time_seconds:.2f} 秒")
        self.log(f"🏁 預計結束時間：{finish_time.strftime('%H:%M:%S')}")

        try:
            if self.is_ios17:
                from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
                from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
                async with DvtProvider(self.provider) as dvt, LocationSimulation(dvt) as loc:
                    await self._do_walk(loc, start_lat, start_lng, end_lat, end_lng, steps)
                    self.log("🏁 抵達目的地！定位鎖定中...")
                    await asyncio.sleep(86400)
            else:
                from pymobiledevice3.services.simulate_location import DtSimulateLocation
                service = DtSimulateLocation(self.provider)
                await self._do_walk(service, start_lat, start_lng, end_lat, end_lng, steps)
                self.log("🏁 抵達目的地！定位鎖定中...")
                await asyncio.sleep(86400)
        except asyncio.CancelledError:
            self.log("🛑 導航已中斷！")
        except Exception as e:
            self.log(f"❌ 行走過程中發生錯誤: {e}")

    async def _do_walk(self, loc_service, start_lat, start_lng, end_lat, end_lng, steps):
        for step in range(steps + 1):
            ratio = step / steps if steps > 0 else 1.0
            current_lat = start_lat + (end_lat - start_lat) * ratio
            current_lng = start_lng + (end_lng - start_lng) * ratio

            await loc_service.set(current_lat, current_lng)
            # 每 3 秒印一次日誌，避免畫面太亂
            if step % 3 == 0 or step == steps: 
                self.log(f"進度 {ratio * 100:.1f}% | 當前: {current_lat:.5f}, {current_lng:.5f}")
            await asyncio.sleep(1)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Spoofy GUI - iPhone 定位模擬器")
        self.geometry("700x550")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 狀態變數
        self.loop = None
        self.spoofer = None
        self.current_task = None
        self.home, self.company, self.default_speed = load_config()
        self.log_queue = queue.Queue()

        # UI 佈局
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # 1. 頂部狀態欄
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="🔌 尚未連線", font=("Microsoft JhengHei", 16, "bold"))
        self.status_label.pack(side="left", padx=20, pady=10)
        
        self.connect_btn = ctk.CTkButton(self.status_frame, text="開始連線", command=self.start_connection)
        self.connect_btn.pack(side="right", padx=20, pady=10)

        # 2. 控制面板
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.control_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.home_btn = ctk.CTkButton(self.control_frame, text="🏠 回家", command=self.go_home, state="disabled")
        self.home_btn.grid(row=0, column=0, padx=10, pady=10)

        self.comp_btn = ctk.CTkButton(self.control_frame, text="🏢 去公司", command=self.go_company, state="disabled")
        self.comp_btn.grid(row=0, column=1, padx=10, pady=10)
        
        self.stop_btn = ctk.CTkButton(self.control_frame, text="🛑 停止動作", fg_color="indianred", hover_color="darkred", command=self.stop_action, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=10, pady=10)

        self.coord_entry = ctk.CTkEntry(self.control_frame, placeholder_text="貼上座標 (例如: 25.0339, 121.5644)", width=400)
        self.coord_entry.grid(row=1, column=0, columnspan=2, padx=10, pady=10)
        
        self.teleport_btn = ctk.CTkButton(self.control_frame, text="🚀 瞬間移動", command=self.manual_teleport, state="disabled")
        self.teleport_btn.grid(row=1, column=2, padx=10, pady=10)

        self.speed_label = ctk.CTkLabel(self.control_frame, text=f"時速: {self.default_speed} km/h")
        self.speed_label.grid(row=2, column=0, padx=10, pady=0)
        
        self.speed_slider = ctk.CTkSlider(self.control_frame, from_=1, to=100, number_of_steps=99, command=self.update_speed_label)
        self.speed_slider.set(self.default_speed)
        self.speed_slider.grid(row=2, column=1, padx=10, pady=0)
        
        self.walk_btn = ctk.CTkButton(self.control_frame, text="🚶 開始行走 (到點)", command=self.start_walk, state="disabled")
        self.walk_btn.grid(row=2, column=2, padx=10, pady=10)

        # 3. 日誌區域
        self.log_text = ctk.CTkTextbox(self, width=600, height=200)
        self.log_text.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="nsew")
        self.log_text.insert("0.0", "歡迎使用 Spoofy GUI！\n請先確認 iPhone 已連接並點擊「開始連線」。\n")

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
                self.spoofer = GUISpoofer(provider, is_ios17, self.log)
                self.after(0, self.on_connected)
                self.log(f"✅ 連線成功 (iOS 17+: {is_ios17})")
            except Exception as e:
                self.log(f"❌ 連線失敗: {e}")
                self.after(0, lambda: self.connect_btn.configure(state="normal", text="開始連線"))

        asyncio.run_coroutine_threadsafe(connect(), self.loop)

    def on_connected(self):
        self.status_label.configure(text="🟢 已連線", text_color="green")
        self.connect_btn.configure(text="重新連線", state="normal")
        self.home_btn.configure(state="normal")
        self.comp_btn.configure(state="normal")
        self.teleport_btn.configure(state="normal")
        self.walk_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")

    def update_speed_label(self, value):
        self.speed_label.configure(text=f"時速: {int(value)} km/h")

    def stop_action(self):
        self.log("🛑 收到停止指令...")
        if self.current_task:
            self.loop.call_soon_threadsafe(self.current_task.cancel)
            self.current_task = None

    def go_home(self):
        if self.spoofer:
            self.log(f"🏠 準備前往住家...")
            self.run_action(self.spoofer.teleport(*self.home))

    def go_company(self):
        if self.spoofer:
            self.log(f"🏢 準備前往公司...")
            self.run_action(self.spoofer.teleport(*self.company))

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
            end_coords = (float(coords[0]), float(coords[1]))
            speed = self.speed_slider.get()
            # 簡化：從家裡走到目的地 (您可以根據需求改成從公司走，或當前位置)
            self.run_action(self.spoofer.walk(self.home, end_coords, speed_kmh=speed))
        else:
            self.log("❌ 請先在輸入框貼上「終點」座標。")

if __name__ == "__main__":
    app = App()
    app.mainloop()
