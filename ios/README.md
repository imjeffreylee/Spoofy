# Spoofy iPhone 原型

這個原型透過 iPhone 的開發者定位模擬服務設定單一座標、模擬兩點移動和恢復實際定位。專案的最低安裝版本是 iOS 17.4，實際能否連線還須在目標 iPhone 的 iOS 版本上驗證。

模擬器版本使用 iOS 26.5 或更新的執行環境，可查看介面。定位模擬服務須使用實體 iPhone 驗證。

## 用 Xcode 安裝到自己的 iPhone

1. 在 Mac 開啟 Xcode，完成首次啟動和授權確認。
2. 在 repo 根目錄執行 `bash ios/fetch-idevice.sh`。它會驗證 [idevice v0.1.68](https://github.com/jkcoxson/idevice/releases/tag/v0.1.68) 的 SHA-256，並把 iOS 和模擬器版本放進 `ios/Vendor/`。
3. 開啟 `ios/Spoofy.xcodeproj`，在 Spoofy target 的 **Signing & Capabilities** 選擇自己的 Apple 帳號或 Personal Team。若簽名畫面顯示 Bundle Identifier 已被使用，換成自己的識別碼。
4. 連接解鎖的 iPhone，在 Xcode 選它為執行裝置並按 Run。依 Xcode 提示在 iPhone 上啟用開發者模式，並完成裝置的開發者支援準備。 [Apple 開發者模式說明](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)

## 首次配對

1. 在 Mac 用支援 **RPPairing** 的 `idevice_pair` 為自己的 iPhone 產生配對檔案，將 `.mobiledevicepairing` 或 `.plist` 檔案傳到 iPhone「檔案」App。配對檔含裝置憑證，請保存在本機。 [配對工具](https://github.com/jkcoxson/idevice_pair/releases/tag/v0.1.9-rppairing)
2. 在 iPhone 安裝並連接 LocalDevVPN，使用預設的 **Device IP** `10.7.0.1`。開啟 Spoofy 後按「匯入配對紀錄」，選取該檔案。如果 iOS 詢問本機網路權限，選擇允許。 [LocalDevVPN](https://apps.apple.com/tw/app/localdevvpn/id6755608044)

## 真機驗收

1. 先在 Apple 地圖確認目前位置。從 Xcode 停止除錯並拔掉 USB，再從 iPhone 主畫面啟動 Spoofy。
2. 輸入一個離目前位置夠遠的公開地標座標，例如 `25.0339, 121.5644`。按「設定座標」並選擇「使用 App 期間允許」定位。待 Spoofy 顯示正在維持座標後，切換到 Apple 地圖或 Google Maps 並點目前位置，確認藍點移到測試地點。留在地圖至少 2 分鐘，確認藍點仍在該處。
3. 回到 Spoofy 按「停止模擬」，再次在 Apple 地圖點目前位置，確認藍點回到實際位置。
4. 若有連線錯誤，先檢查本機網路權限、LocalDevVPN、開發者模式及配對檔，再重試。若清除失敗且地圖仍顯示模擬位置，重開 iPhone 後確認實際位置已恢復。

## 模擬移動

1. 保持 LocalDevVPN 連線，選「模擬移動」，貼上起點與終點座標。
2. 選「步行道路」或「直線」，設定速度（預設 19 km/h，可調整為 1 至 20 km/h），再點「開始移動」。步行路線由 Apple 地圖規劃，需要網路連線。
3. 第一次開始移動時，選擇「使用 App 期間允許」定位。播放路線時，切換 App 會繼續移動。若已拒絕定位權限，請到 iPhone 的「設定 → App → Spoofy → 位置」允許後重試。 [Apple 背景定位說明](https://developer.apple.com/documentation/corelocation/handling-location-updates-in-the-background)
4. 抵達後保留終點位置。可隨時點「停止模擬」，中止路線並恢復實際定位。
5. 成功開始移動後，Spoofy 會記住起點、終點、路線類型和速度。下次開啟時，在「模擬移動」點「開始上次路線」即可從上次的起點重新播放。
