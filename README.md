# 🚀 iPhone 定位模擬器 (Spoofy)

這是一個支援 iOS 16 及 iOS 17+ 的 iPhone 定位模擬工具。透過簡單的指令，你可以實現瞬間移動、兩點路徑模擬等功能。

## 📥 如何從 GitHub 下載本專案

如果你不熟悉 GitHub，可以透過以下兩種方式取得程式：

### 方式 A：下載壓縮檔 (適合一般用戶)
1. 在本頁面右上方找到綠色的 **「Code」** 按鈕。
2. 點擊後選擇 **「Download ZIP」**。
3. 下載後解壓縮到你的電腦桌面或資料夾即可開始使用。

### 方式 B：使用 Git 指令 (適合開發者)
如果你已安裝 Git，可以直接在終端機執行：
```bash
git clone https://github.com/imjeffreylee/spoofy.git
```

## 🛠️ 安裝步驟

### 1. 安裝 Python 3 (必要前提)
請確保你的電腦已安裝 Python 3.8 或以上版本。
- [Python 官網下載](https://www.python.org/downloads/)
- **注意：** 安裝時請務必勾選「Add Python to PATH」。

### 2. 下載本專案並安裝套件
進入專案目錄後，根據你的作業系統執行：

#### 🍏 Mac / Linux 用戶：
開啟終端機執行下方指令（會自動幫你裝好所有東西）：
```bash
chmod +x setup.sh && ./setup.sh
```

#### 🪟 Windows 用戶：
開啟 CMD 或 PowerShell 執行：
```bash
pip install -r requirements.txt
```

### 3. 設定常用地點 (選填)
專案已內附 `config.example.json`，請手動複製並改名為 `config.json`：
```bash
cp config.example.json config.json
```
接著，你可以自行修改 `config.json` 裡的「住家」與「公司」座標：
```json
{
  "home": [25.0339, 121.5644],
  "company": [25.0479, 121.5173],
  "speed": 19.0
}
```
*(註：`config.json` 已被加入 `.gitignore` 中，上傳至 GitHub 時不會洩漏你的私人位置)*

---

## 📱 使用說明

### 準備工作
1. 將 iPhone 透過 USB 連接至電腦。
2. 解鎖手機，若跳出「信任此電腦」，請點選**信任**。
3. **[Windows 用戶必看]** 你必須在電腦上安裝 [Apple Devices 應用程式](https://apps.microsoft.com/detail/9np83lwlpz9k) 或 [iTunes](https://www.apple.com/itunes/)，這樣電腦才會有蘋果的 USB 驅動程式，否則程式無法抓到你的手機。
4. **[重要]** 進入 iPhone 的「設定」>「隱私權與安全性」> 滑到最下面開啟**「開發者模式」**（若沒有開啟，會需要重開機並再次確認）。

### 啟動程式
在終端機執行：
```bash
python3 spoofy.py
```

### 💡 iOS 17+ 使用者必看
若你的手機版本為 iOS 17 或以上，執行方式略有不同：
1. 開啟一個**新的終端機視窗**，執行：
   ```bash
   sudo python3 -m pymobiledevice3 remote tunneld
   ```
2. **保持該視窗開啟不要關閉**（它會負責建立與手機的加密連線）。
3. 回到原本的視窗執行 `python3 spoofy.py`。

---

## 🌟 功能簡介
1. **住家 -> 公司 (行走模擬)**：一鍵開始自動導航（座標於 `config.json` 設定）。
2. **手動輸入座標**：直接貼上 Google Maps 複製的座標數字即可瞬間移動。
3. **自訂導航移動**：手動輸入起點、終點與時速進行模擬。

## 🔒 關於定位鎖定
- 執行定位後，程式會自動進入「鎖定模式」防止手機自動跳回真實位置。
- 若要解除鎖定並回到主選單，只需在終端機按 **[Enter]** 鍵。
- 若要完全恢復手機真實定位，請**將 iPhone 重新開機**。

## ⚠️ 免責聲明
本工具僅供開發測試與學習使用，請勿用於任何非法用途或違反第三方服務條款之行為。
