import asyncio
import sys
import re
import platform
import json
import os
import webbrowser
from core import SpooferCore, get_device_provider

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    import msvcrt
else:
    import select

class CLISpoofer:
    def __init__(self, provider, is_ios17):
        # Setup progress reporting for CLI
        self.last_print_time = 0
        def progress_cb(pct, lat, lng):
            current_time = asyncio.get_event_loop().time()
            if current_time - self.last_print_time >= 3 or pct >= 100:
                print(f"進度 {pct:.1f}% | 當前位置: {lat:.5f}, {lng:.5f}    ", end="\r")
                self.last_print_time = current_time

        self.core = SpooferCore(provider, is_ios17, log_callback=print, progress_callback=progress_cb)
        self.is_ios17 = is_ios17

    def preview_route(self, start_coords, end_coords):
        """在瀏覽器中開啟 Google Maps 預覽路徑"""
        start_lat, start_lng = start_coords
        end_lat, end_lng = end_coords
        url = f"https://www.google.com/maps/dir/?api=1&origin={start_lat},{start_lng}&destination={end_lat},{end_lng}&travelmode=bicycling"
        print(f"\n🔗 正在開啟瀏覽器預覽路徑...")
        webbrowser.open(url)

    async def _wait_for_enter(self, prompt="\n↩️  若要結束鎖定並回到主選單，請按【Enter】鍵..."):
        """Wait for Enter key asynchronously to avoid blocking the event loop entirely."""
        print(prompt)
        while True:
            if IS_WINDOWS:
                if msvcrt.kbhit():
                    char = msvcrt.getch()
                    if char in (b"\r", b"\n"):
                        break
            else:
                if select.select([sys.stdin], [], [], 0)[0]:
                    char = sys.stdin.read(1)
                    if char in ("\n", "\r"):
                        break
            await asyncio.sleep(0.1)

    async def teleport(self, lat, lng):
        """CLI wrapper for teleport, adding user input block."""
        print(f"\n🚀 準備定位至座標: 緯度 {lat}, 經度 {lng}")
        print("🔒 目前正在『鎖定定位』中，防止 iPhone 自動跳回真實位置...")
        print("👉 [提示] 在此狀態下您可以安心使用手機。")
        
        teleport_task = asyncio.create_task(self.core.teleport(lat, lng))
        try:
            await self._wait_for_enter()
        finally:
            teleport_task.cancel()
            try:
                await teleport_task
            except asyncio.CancelledError:
                pass

    async def walk(self, start_coords, end_coords, speed_kmh=5.0):
        """CLI wrapper for walk, adding user input block for cancellation."""
        print("💡 【提示】在導航過程中，您可以隨時按下 `Enter` 鍵中斷導航。")
        walk_task = asyncio.create_task(self.core.walk(start_coords, end_coords, speed_kmh))
        try:
            await self._wait_for_enter("\n↩️  按下【Enter】鍵中斷導航或結束鎖定...")
        finally:
            walk_task.cancel()
            try:
                await walk_task
            except asyncio.CancelledError:
                pass

    async def manual_input_teleport(self):
        print("\n📍 請貼上座標 (格式如: 25.0339, 121.5644)")
        raw_input = input("座標：").strip()
        coords = re.findall(r"[-+]?\d*\.\d+|\d+", raw_input)
        if len(coords) >= 2:
            try:
                lat, lng = float(coords[0]), float(coords[1])
                print(f"解析成功：緯度 {lat}, 經度 {lng}")
                await self.teleport(lat, lng)
            except ValueError:
                print("❌ 無法解析座標數字。")
        else:
            print("❌ 格式不正確，請確保包含經度和緯度兩個數字。")

    async def custom_walk(self):
        print("\n📍 請輸入起點 A 的座標 (格式如: 25.0339, 121.5644)")
        raw_start = input("起點座標：").strip()
        coords_start = re.findall(r"[-+]?\d*\.\d+|\d+", raw_start)
        if len(coords_start) < 2: return print("❌ 格式不正確。")
        start_lat, start_lng = float(coords_start[0]), float(coords_start[1])

        print("\n📍 請輸入終點 B 的座標 (格式如: 25.0479, 121.5173)")
        raw_end = input("終點座標：").strip()
        coords_end = re.findall(r"[-+]?\d*\.\d+|\d+", raw_end)
        if len(coords_end) < 2: return print("❌ 格式不正確。")
        end_lat, end_lng = float(coords_end[0]), float(coords_end[1])

        print("\n🚗 請輸入導航時速 (km/h) [預設為 19]")
        raw_speed = input("時速：").strip()
        speed = float(raw_speed) if raw_speed else 19.0

        print("\n請選擇：\n1. 預覽路徑\n2. 開始導航")
        if input("請選擇 (預設為 2): ").strip() == "1":
            self.preview_route((start_lat, start_lng), (end_lat, end_lng))
        else:
            save_last_navigation([start_lat, start_lng], [end_lat, end_lng], speed)
            await self.walk((start_lat, start_lng), (end_lat, end_lng), speed_kmh=speed)

def save_last_navigation(start_coords, end_coords, speed):
    """儲存最後一次導航資訊到 config.json"""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except:
            pass
    config["last_navigation"] = {
        "start_coords": start_coords,
        "end_coords": end_coords,
        "speed": speed
    }
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ 儲存導航資訊失敗: {e}")

def load_config():
    """從 config.json 載入常用地點座標"""
    default_config = {
        "start": {"name": "預設起點", "coords": [25.027718192429898, 121.54652202461413]},
        "end": {"name": "預設終點", "coords": [25.127024499013306, 121.47395879902238]},
        "speed": 19.0,
        "frequent_locations": [],
        "last_navigation": None
    }
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    config = default_config.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception as e:
            print(f"⚠️ 讀取設定檔發生錯誤: {e}")
    
    start_data = config.get("start", default_config["start"])
    start_coords = start_data.get("coords") if isinstance(start_data, dict) else start_data
    end_data = config.get("end", default_config["end"])
    end_coords = end_data.get("coords") if isinstance(end_data, dict) else end_data
    
    return (tuple(start_coords), tuple(end_coords), float(config.get("speed", default_config["speed"])), 
            config.get("frequent_locations", default_config["frequent_locations"]), start_data, end_data,
            config.get("last_navigation"))

async def main():
    print("========================================================================")
    print("🚀 iPhone 定位模擬器 (Spoofy)")
    print("👉 詳細使用說明請參考專案中的 README.md")
    print("========================================================================")

    start_coords, end_coords, default_speed, frequent_locations, start_data, end_data, last_nav = load_config()

    try:
        provider, is_ios17 = await get_device_provider()
        spoofer = CLISpoofer(provider, is_ios17)
        print(f"成功連線至裝置 (iOS 17+: {is_ios17})")
    except Exception as e:
        print(f"連線錯誤: {e}")
        return

    while True:
        try:
            start_name = start_data["name"] if isinstance(start_data, dict) else "常用起點"
            end_name = end_data["name"] if isinstance(end_data, dict) else "常用終點"

            print("\n請選擇功能：")
            print(f"1. {start_name} -> {end_name} (行走模擬) - 預設時速 {default_speed} km/h")
            print("2. 手動輸入單一座標 (適合從 Google Maps 複製貼上)")
            print("3. 自訂導航移動 (輸入兩點座標及時速)")
            if frequent_locations: print("4. 傳送到常用地點")
            if last_nav: print("5. 使用上次的導航")
            print("q. 離開程式")

            choice = input("輸入功能編號: ").strip().lower()

            if choice == "1":
                print("\n請選擇：\n1. 預覽路徑\n2. 開始導航")
                if input("請選擇 (預設為 2): ").strip() == "1":
                    spoofer.preview_route(start_coords, end_coords)
                else:
                    await spoofer.walk(start_coords, end_coords, speed_kmh=default_speed)
            elif choice == "2":
                await spoofer.manual_input_teleport()
            elif choice == "3":
                await spoofer.custom_walk()
                # 更新上次導航資訊，以便在選單中顯示
                _, _, _, _, _, _, last_nav = load_config()
            elif choice == "4" and frequent_locations:
                print("\n📍 常用地點：")
                for i, loc in enumerate(frequent_locations):
                    print(f"[{i + 1}] {loc['name']} ({loc['coords'][0]}, {loc['coords'][1]})")
                sel = input(f"請選擇地點 (1-{len(frequent_locations)}) 或 0 取消: ").strip()
                if sel.isdigit() and 0 <= int(sel) - 1 < len(frequent_locations):
                    target = frequent_locations[int(sel) - 1]
                    await spoofer.teleport(target["coords"][0], target["coords"][1])
            elif choice == "5" and last_nav:
                s = last_nav["start_coords"]
                e = last_nav["end_coords"]
                sp = last_nav["speed"]
                print(f"\n🔄 使用上次導航：({s[0]}, {s[1]}) -> ({e[0]}, {e[1]})，時速 {sp} km/h")
                await spoofer.walk(tuple(s), tuple(e), speed_kmh=sp)
            elif choice == "q":
                break
        except KeyboardInterrupt:
            print("\n👋 程式已結束。")
            break

if __name__ == "__main__":
    asyncio.run(main())
