import asyncio
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from geopy.distance import geodesic

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.simulate_location import DtSimulateLocation
from pymobiledevice3.services.dvt.instruments.location_simulation import (
    LocationSimulation,
)
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.tunneld.api import get_tunneld_devices, TUNNELD_DEFAULT_ADDRESS

class LocationService:
    """Abstracts the differences between iOS 17+ and older versions."""
    def __init__(self, provider, is_ios17):
        self.provider = provider
        self.is_ios17 = is_ios17

    async def __aenter__(self):
        if self.is_ios17:
            self._dvt = DvtProvider(self.provider)
            await self._dvt.__aenter__()
            self._loc = LocationSimulation(self._dvt)
            await self._loc.__aenter__()
        else:
            self._loc = DtSimulateLocation(self.provider)
        return self._loc

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.is_ios17:
            await self._loc.__aexit__(exc_type, exc_val, exc_tb)
            await self._dvt.__aexit__(exc_type, exc_val, exc_tb)

async def get_device_provider():
    """Gets the appropriate device provider based on iOS version."""
    lockdown = await create_using_usbmux()
    res = lockdown.get_value(None, "ProductVersion")
    product_version = await res if asyncio.iscoroutine(res) else res
    is_ios17 = int(product_version.split(".")[0]) >= 17

    if is_ios17:
        rsds = await get_tunneld_devices(TUNNELD_DEFAULT_ADDRESS)
        if not rsds:
            raise RuntimeError("找不到 Tunnel 裝置，請先執行：sudo python3 -m pymobiledevice3 remote tunneld")
        return rsds[0], True
    return lockdown, False

class SpooferCore:
    def __init__(self, provider, is_ios17, log_callback=None, progress_callback=None):
        self.provider = provider
        self.is_ios17 = is_ios17
        self.log_callback = log_callback or print
        self.progress_callback = progress_callback or (lambda *args: None)
        self.current_coords = None

    async def get_route(self, start_coords, end_coords):
        """Fetches the route from OSRM."""
        start_lat, start_lng = start_coords
        end_lat, end_lng = end_coords
        url = f"http://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}?overview=full&geometries=geojson"

        def _fetch_route():
            with urllib.request.urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode())

        data = await asyncio.to_thread(_fetch_route)
        if data.get("code") == "Ok" and data.get("routes"):
            coords = data["routes"][0]["geometry"]["coordinates"]
            return [(lat, lng) for lng, lat in coords]
        
        self.log_callback(f"❌ 無法取得導航路徑：{data.get('message', '未知錯誤')}")
        return None

    async def teleport(self, lat, lng, lock_duration_hours=24):
        """Teleports to a specific location and locks it."""
        try:
            async with LocationService(self.provider, self.is_ios17) as loc:
                await loc.set(lat, lng)
                self.current_coords = (lat, lng)
                self.log_callback(f"🚀 成功定位至座標: 緯度 {lat}, 經度 {lng}")
                self.log_callback("🔒 定位已鎖定。")
                # Maintain the lock
                await asyncio.sleep(lock_duration_hours * 3600)
        except asyncio.CancelledError:
            self.log_callback("🛑 定位鎖定已解除。")
        except Exception as e:
            self.log_callback(f"❌ 定位失敗: {e}")
            raise

    async def walk(self, start_coords, end_coords, speed_kmh=5.0):
        """Simulates walking along a route."""
        self.log_callback("🔍 正在規劃真實道路路徑...")
        try:
            path = await self.get_route(start_coords, end_coords)
            if not path:
                self.log_callback("⚠️ 無法取得導航路徑，將改為直線移動。")
                path = [start_coords, end_coords]

            async with LocationService(self.provider, self.is_ios17) as loc:
                await self._do_walk(loc, path, speed_kmh)
                self.log_callback("🏁 抵達目的地！定位鎖定中...")
                await asyncio.sleep(86400) # Lock at destination
        except asyncio.CancelledError:
            self.log_callback("🛑 導航已中斷！")
        except Exception as e:
            self.log_callback(f"❌ 行走過程中發生錯誤: {e}")
            raise

    async def _do_walk(self, loc_service, path, speed_kmh):
        speed_ms = speed_kmh / 3.6
        segments = [geodesic(path[i], path[i + 1]).meters for i in range(len(path) - 1)]
        total_dist = sum(segments)

        if total_dist == 0:
            return

        total_time = total_dist / speed_ms
        finish_time = datetime.now() + timedelta(seconds=total_time)
        self.log_callback(f"🚶 開始導航！路徑距離: {total_dist:.2f} 公尺, 預計結束時間：{finish_time.strftime('%H:%M:%S')}")

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
                    ratio = (current_dist - acc_dist) / seg_dist if seg_dist > 0 else 1.0
                    p1, p2 = path[i], path[i + 1]
                    cur_lat = p1[0] + (p2[0] - p1[0]) * ratio
                    cur_lng = p1[1] + (p2[1] - p1[1]) * ratio
                    
                    await loc_service.set(cur_lat, cur_lng)
                    self.current_coords = (cur_lat, cur_lng)
                    
                    progress_pct = (current_dist / total_dist) * 100
                    self.progress_callback(progress_pct, cur_lat, cur_lng)
                    break
                acc_dist += seg_dist

            await asyncio.sleep(1)

        # Ensure we reach the exact final destination
        final_lat, final_lng = path[-1]
        await loc_service.set(final_lat, final_lng)
        self.current_coords = (final_lat, final_lng)
        self.progress_callback(100.0, final_lat, final_lng)
