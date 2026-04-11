import asyncio
import sys
import ssl
import certifi
import re
import platform
import json
import os
import urllib.request
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.simulate_location import DtSimulateLocation
from pymobiledevice3.services.dvt.instruments.location_simulation import (
    LocationSimulation,
)
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.tunneld.api import get_tunneld_devices, TUNNELD_DEFAULT_ADDRESS

# 判斷作業系統
IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    import msvcrt
else:
    import tty
    import termios
    import select


class Spoofy:
    def __init__(self, provider, is_ios17):
        self.provider = provider
        self.is_ios17 = is_ios17
        print(f"成功連線至裝置 (iOS 17+: {is_ios17})")

    def preview_route(self, start_coords, end_coords):
        """在瀏覽器中開啟 Google Maps 預覽路徑"""
        start_lat, start_lng = start_coords
        end_lat, end_lng = end_coords
        url = f"https://www.google.com/maps/dir/?api=1&origin={start_lat},{start_lng}&destination={end_lat},{end_lng}&travelmode=bicycling"
        print(f"\n🔗 正在開啟瀏覽器預覽路徑...")
        webbrowser.open(url)

    async def teleport(self, lat, lng):
        """核心功能：執行定位修改並保持連線鎖定"""
        try:
            if self.is_ios17:
                async with (
                    DvtProvider(self.provider) as dvt,
                    LocationSimulation(dvt) as loc,
                ):
                    await loc.set(lat, lng)
                    print(f"\n🚀 成功定位至座標: 緯度 {lat}, 經度 {lng}")
                    print("🔒 目前正在『鎖定定位』中，防止 iPhone 自動跳回真實位置...")
                    print("👉 [提示] 在此狀態下您可以安心使用手機。")
                    # 使用 input 阻擋程式繼續執行，藉此保持 DVT 通道開啟
                    await asyncio.to_thread(
                        input, "\n↩️  若要結束鎖定並回到主選單，請按【Enter】鍵..."
                    )
            else:
                service = DtSimulateLocation(self.provider)
                await service.set(lat, lng)
                print(f"\n🚀 成功定位至座標: 緯度 {lat}, 經度 {lng}")
                print("🔒 目前正在『鎖定定位』中，防止 iPhone 自動跳回真實位置...")
                await asyncio.to_thread(
                    input, "\n↩️  若要結束鎖定並回到主選單，請按【Enter】鍵..."
                )
        except Exception as e:
            print(f"❌ 定位失敗: {e}")
            self._check_mount_error(e)

    async def get_route(self, start_coords, end_coords):
        """取得兩點間的真實路徑座標點 (使用 OSRM 公開 API)"""
        start_lat, start_lng = start_coords
        end_lat, end_lng = end_coords

        # OSRM 格式: lon,lat;lon,lat
        url = f"http://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}?overview=full&geometries=geojson"

        try:

            def _fetch_route():
                with urllib.request.urlopen(url, timeout=10) as response:
                    return json.loads(response.read().decode())

            data = await asyncio.to_thread(_fetch_route)

            if data.get("code") == "Ok" and data.get("routes"):
                # OSRM 回傳的是 [lng, lat]
                coords = data["routes"][0]["geometry"]["coordinates"]
                return [(lat, lng) for lng, lat in coords]
            else:
                print(f"❌ 無法取得導航路徑：{data.get('message', '未知錯誤')}")
                return None
        except Exception as e:
            print(f"❌ 網路連線錯誤 (取得路徑失敗): {e}")
            return None

    async def walk(self, start_coords, end_coords, speed_kmh=5.0):
        """功能 2：模擬兩點間行走 (支援真實道路導航)"""
        print("\n🔍 正在規劃真實道路路徑...")
        path = await self.get_route(start_coords, end_coords)

        if not path:
            print("⚠️ 無法取得導航路徑，將改為直線移動。")
            path = [start_coords, end_coords]

        print("💡 【提示】在導航過程中，您可以隨時按下 `Enter` 鍵中斷導航。")

        try:
            if self.is_ios17:
                async with (
                    DvtProvider(self.provider) as dvt,
                    LocationSimulation(dvt) as loc,
                ):
                    await self._do_walk(loc, path, speed_kmh)
                    print("\n🏁 抵達目的地！")
                    await asyncio.to_thread(
                        input, "\n↩️  導航結束。請按【Enter】鍵回到主選單..."
                    )
            else:
                service = DtSimulateLocation(self.provider)
                await self._do_walk(service, path, speed_kmh)
                print("\n🏁 抵達目的地！")
                await asyncio.to_thread(
                    input, "\n↩️  導航結束。請按【Enter】鍵回到主選單..."
                )
        except KeyboardInterrupt:
            print("\n🛑 導航已中斷！正在返回主選單...")
        except Exception as e:
            print(f"❌ 行走過程中發生錯誤: {e}")
            self._check_mount_error(e)

    async def _do_walk(self, loc_service, path, speed_kmh):
        if not IS_WINDOWS:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            # 設定為 cbreak 模式以即時讀取按鍵
            tty.setcbreak(fd)
            # 關閉流控制 (IXON)，否則 Ctrl+S 等按鍵可能被攔截
            new_settings = termios.tcgetattr(fd)
            new_settings[0] &= ~(termios.IXON | termios.IXOFF)
            termios.tcsetattr(fd, termios.TCSANOW, new_settings)

        speed_ms = speed_kmh / 3.6
        # 計算路徑段距離
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
        print(
            f"🚶 開始導航！路徑距離: {total_dist:.2f} 公尺, 預計耗時: {total_time:.1f} 秒"
        )
        print(f"🏁 預計結束時間：{finish_time.strftime('%H:%M:%S')}")

        current_dist = 0
        start_time = asyncio.get_event_loop().time()

        try:
            while current_dist < total_dist:
                # 檢查是否有按鍵輸入 (偵測 Enter 鍵)
                if IS_WINDOWS:
                    if msvcrt.kbhit():
                        char = msvcrt.getch()
                        if char in (b"\r", b"\n"):  # Enter 鍵
                            raise KeyboardInterrupt
                else:
                    if select.select([sys.stdin], [], [], 0)[0]:
                        char = sys.stdin.read(1)
                        if char in ("\n", "\r"):  # Enter 鍵
                            raise KeyboardInterrupt

                elapsed = asyncio.get_event_loop().time() - start_time
                current_dist = elapsed * speed_ms

                if current_dist >= total_dist:
                    break

                # 尋找當前位置在路徑中的段落
                acc_dist = 0
                for i, seg_dist in enumerate(segments):
                    if acc_dist + seg_dist >= current_dist:
                        ratio = (
                            (current_dist - acc_dist) / seg_dist
                            if seg_dist > 0
                            else 1.0
                        )
                        p1, p2 = path[i], path[i + 1]
                        cur_lat = p1[0] + (p2[0] - p1[0]) * ratio
                        cur_lng = p1[1] + (p2[1] - p1[1]) * ratio
                        await loc_service.set(cur_lat, cur_lng)
                        print(
                            f"進度 {current_dist / total_dist * 100:.1f}% | 當前位置: {cur_lat:.5f}, {cur_lng:.5f}    ",
                            end="\r",
                        )
                        break
                    acc_dist += seg_dist

                await asyncio.sleep(1)

            # 設定到最後一點
            await loc_service.set(path[-1][0], path[-1][1])
            print(f"進度 100.0% | 當前位置: {path[-1][0]:.5f}, {path[-1][1]:.5f}    ")
        except asyncio.CancelledError:
            pass
        finally:
            # 恢復終端機原始設定
            if not IS_WINDOWS:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    async def search_and_teleport(self):
        """功能 3：搜尋地點名稱"""
        query = input("\n請輸入想要搜尋的地點名稱 (例如：東京迪士尼)：")
        if not query.strip():
            return

        print(f"🔍 正在搜尋 '{query}' ...")
        ctx = ssl.create_default_context(cafile=certifi.where())
        geolocator = Nominatim(user_agent="spoofy_cli", ssl_context=ctx)

        try:
            results = await asyncio.to_thread(
                geolocator.geocode, query, exactly_one=False, limit=10
            )
        except Exception as e:
            print(f"❌ 搜尋時發生錯誤: {e}")
            return

        if not results:
            print("❌ 找不到地點。")
            return

        print("\n📍 搜尋結果：")
        for i, location in enumerate(results):
            print(f"[{i + 1}] {location.address}")

        try:
            selection = input(f"\n請輸入編號 (1-{len(results)}) 或 0 取消: ")
            idx = int(selection) - 1
            if idx >= 0 and idx < len(results):
                await self.teleport(results[idx].latitude, results[idx].longitude)
        except ValueError:
            print("❌ 輸入無效。")

    async def manual_input_teleport(self):
        """功能 4：手動輸入座標 (支援 Google Maps 格式)"""
        print("\n📍 請貼上座標 (格式如: 25.0339, 121.5644)")
        raw_input = input("座標：").strip()

        # 使用正則表達式嘗試提取經緯度數字
        coords = re.findall(r"[-+]?\d*\.\d+|\d+", raw_input)

        if len(coords) >= 2:
            try:
                lat = float(coords[0])
                lng = float(coords[1])
                print(f"解析成功：緯度 {lat}, 經度 {lng}")
                await self.teleport(lat, lng)
            except ValueError:
                print("❌ 無法解析座標數字。")
        else:
            print("❌ 格式不正確，請確保包含經度和緯度兩個數字。")

    async def custom_walk(self):
        """功能 3：自訂兩點導航"""
        print("\n📍 請輸入起點 A 的座標 (格式如: 25.0339, 121.5644)")
        raw_start = input("起點座標：").strip()
        coords_start = re.findall(r"[-+]?\d*\.\d+|\d+", raw_start)

        if len(coords_start) < 2:
            print("❌ 格式不正確，請確保包含起點的經度和緯度。")
            return

        try:
            start_lat = float(coords_start[0])
            start_lng = float(coords_start[1])
        except ValueError:
            print("❌ 無法解析起點座標數字。")
            return

        print("\n📍 請輸入終點 B 的座標 (格式如: 25.0479, 121.5173)")
        raw_end = input("終點座標：").strip()
        coords_end = re.findall(r"[-+]?\d*\.\d+|\d+", raw_end)

        if len(coords_end) < 2:
            print("❌ 格式不正確，請確保包含終點的經度和緯度。")
            return

        try:
            end_lat = float(coords_end[0])
            end_lng = float(coords_end[1])
        except ValueError:
            print("❌ 無法解析終點座標數字。")
            return

        print("\n🚗 請輸入導航時速 (km/h) [預設為 19]")
        raw_speed = input("時速：").strip()
        if not raw_speed:
            speed = 19.0
            print(f"ℹ️ 未輸入時速，使用預設值: {speed} km/h")
        else:
            try:
                speed = float(raw_speed)
                if speed <= 0:
                    print("❌ 時速必須大於 0。")
                    return
            except ValueError:
                print("❌ 無法解析時速數字。")
                return

        print(
            f"解析成功：從 ({start_lat}, {start_lng}) 導航至 ({end_lat}, {end_lng})，時速 {speed} km/h"
        )
        
        print("\n請選擇：")
        print("1. 預覽路徑 (在瀏覽器中開啟 Google Maps)")
        print("2. 開始導航")
        sub_choice = input("請選擇 (預設為 2): ").strip()
        
        if sub_choice == "1":
            self.preview_route((start_lat, start_lng), (end_lat, end_lng))
        else:
            await self.walk((start_lat, start_lng), (end_lat, end_lng), speed_kmh=speed)

    def _check_mount_error(self, error):
        if "ImageMount" in str(error) or "InvalidService" in str(error):
            print("\n⚠️ 手機可能尚未掛載開發者映像檔或啟動 tunneld。")
            if self.is_ios17:
                print("請啟動隧道：sudo python3 -m pymobiledevice3 remote tunneld")
            else:
                print("請嘗試掛載：python3 -m pymobiledevice3 mounter auto-mount")


async def get_device_provider():
    try:
        # 根據報錯，您的版本 create_using_usbmux 必須使用 await
        try:
            lockdown = await create_using_usbmux()
        except Exception as e:
            print(f"❌ 無法透過 USB 偵測到裝置：{e}")
            print("💡 請確認手機已接上、已解鎖，並已點選「信任此電腦」。")
            sys.exit(1)

        # 取得系統資訊在部分版本也可能是異步
        res = lockdown.get_value(None, "ProductVersion")
        if asyncio.iscoroutine(res):
            product_version = await res
        else:
            product_version = res

        is_ios17 = int(product_version.split(".")[0]) >= 17

        if is_ios17:
            print(f"偵測到 iOS {product_version}，正在檢查 Tunneld...")
            try:
                rsds = await get_tunneld_devices(TUNNELD_DEFAULT_ADDRESS)
                if not rsds:
                    print(
                        "\n❌ 找不到 Tunnel 裝置，請先執行：sudo python3 -m pymobiledevice3 remote tunneld"
                    )
                    sys.exit(1)
                return rsds[0], True
            except Exception as e:
                print(f"\n❌ 無法連線至 Tunneld：{e}")
                sys.exit(1)
        else:
            return lockdown, False
    except Exception as e:
        print(f"❌ 發生未知錯誤：{e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def load_config():
    """從 config.json 載入常用地點座標"""
    default_config = {
        "start": {"name": "預設起點", "coords": [25.027718192429898, 121.54652202461413]},
        "end": {"name": "預設終點", "coords": [25.127024499013306, 121.47395879902238]},
        "speed": 19.0,
        "frequent_locations": [],
    }

    config_path = os.path.join(os.path.dirname(__file__), "config.json")

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                
                start_data = config.get("start", default_config["start"])
                # 相容舊格式 (如果是 list 直接當成 coords)
                start_coords = start_data.get("coords") if isinstance(start_data, dict) else start_data
                
                end_data = config.get("end", default_config["end"])
                end_coords = end_data.get("coords") if isinstance(end_data, dict) else end_data
                
                return (
                    tuple(start_coords),
                    tuple(end_coords),
                    float(config.get("speed", default_config["speed"])),
                    config.get(
                        "frequent_locations", default_config["frequent_locations"]
                    ),
                    start_data,
                    end_data
                )
        except Exception as e:
            print(f"⚠️ 讀取設定檔發生錯誤: {e}，將使用預設座標。")

    return (
        tuple(default_config["start"]["coords"]),
        tuple(default_config["end"]["coords"]),
        default_config["speed"],
        default_config["frequent_locations"],
        default_config["start"],
        default_config["end"]
    )


async def main():
    print("========================================================================")
    print("🚀 iPhone 定位模擬器 (Spoofy)")
    print("👉 詳細使用說明請參考專案中的 README.md")
    print("========================================================================")

    # 載入設定
    start_coords, end_coords, default_speed, frequent_locations, start_data, end_data = load_config()

    provider, is_ios17 = await get_device_provider()
    spoofer = Spoofy(provider, is_ios17)

    while True:
        try:
            start_name = start_data["name"] if isinstance(start_data, dict) else "常用起點"
            end_name = end_data["name"] if isinstance(end_data, dict) else "常用終點"
            
            print("\n請選擇功能：")
            print(f"1. {start_name} -> {end_name} (行走模擬) - 預設時速 {default_speed} km/h")
            print("2. 手動輸入單一座標 (適合從 Google Maps 複製貼上)")
            print("3. 自訂導航移動 (輸入兩點座標及時速)")
            if frequent_locations:
                print("4. 傳送到常用地點")
            print("q. 離開程式")

            choice = input("輸入功能編號: ").strip().lower()

            if choice == "1":
                print("\n請選擇：")
                print("1. 預覽路徑 (在瀏覽器中開啟 Google Maps)")
                print("2. 開始導航")
                sub_choice = input("請選擇 (預設為 2): ").strip()
                
                if sub_choice == "1":
                    spoofer.preview_route(start_coords, end_coords)
                else:
                    await spoofer.walk(start_coords, end_coords, speed_kmh=default_speed)
            elif choice == "2":
                await spoofer.manual_input_teleport()
            elif choice == "3":
                await spoofer.custom_walk()
            elif choice == "4" and frequent_locations:
                print("\n📍 常用地點：")
                for i, loc in enumerate(frequent_locations):
                    print(
                        f"[{i + 1}] {loc['name']} ({loc['coords'][0]}, {loc['coords'][1]})"
                    )

                sel = input(
                    f"請選擇地點 (1-{len(frequent_locations)}) 或 0 取消: "
                ).strip()
                if sel.isdigit():
                    idx = int(sel) - 1
                    if 0 <= idx < len(frequent_locations):
                        target = frequent_locations[idx]
                        await spoofer.teleport(target["coords"][0], target["coords"][1])
            elif choice == "q":
                print("程式結束。")
                break
            else:
                print("❌ 輸入錯誤。")
        except KeyboardInterrupt:
            print("\n👋 程式已結束。")
            break


if __name__ == "__main__":
    asyncio.run(main())
