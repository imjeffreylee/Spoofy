# Spoofy iPhone 原型

這個原型透過 iPhone 的開發者定位模擬服務設定與清除單一座標。專案的最低安裝版本是 iOS 17.4，實際能否連線還須在目標 iPhone 的 iOS 版本上驗證。首輪以 Wi‑Fi 驗證，鎖屏、長時間在背景執行、行動網路和路線播放會另行驗證。

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
2. 輸入一個離目前位置夠遠的公開地標座標，例如 `25.0339, 121.5644`。按「設定座標」，待 Spoofy 顯示已送出後，立即切換到 Apple 地圖並點目前位置，確認藍點移到測試地點。
3. 回到 Spoofy 按「停止模擬」，再次在 Apple 地圖點目前位置，確認藍點回到實際位置。
4. 若有連線錯誤，先檢查本機網路權限、LocalDevVPN、開發者模式及配對檔，再重試。若清除失敗且地圖仍顯示模擬位置，重開 iPhone 後確認實際位置已恢復。
