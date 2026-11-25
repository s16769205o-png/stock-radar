# 小G股票雷達

## 🇺🇸 SEC 原始財報核對（1.37，選配）

美股分頁的「季度財報研究」目前是 Yahoo Finance 的季度整理資料試驗區。
新增的 SEC XBRL 核對功能**預設關閉**，網站會逐檔標示「SEC 官方核對尚未啟用」，
不會把 Yahoo 整理數據冒充已由 SEC 驗證。

SEC 官方公司財報來源：https://www.sec.gov/search-filings/edgar-application-programming-interfaces

### 啟用方式（可選）

1. 先確認願意用真實、合法的程式名稱與聯絡方式遵循 SEC 公平存取政策。
2. 在 GitHub 倉庫 Settings → Secrets and variables → Actions 建立 **Repository secret**，
   名稱填 `SEC_USER_AGENT`；值用自己的真實程式識別及聯絡 Email
   （格式範例：`ResearchApp contact@your-real-domain.example`，示例不可原樣當真實身分使用）。
3. 下次 GitHub Actions 執行股票掃描時，會以低頻率讀取 SEC 公司清單及最多八家公司
   的 companyfacts JSON。沒有設定秘密變數時完全不發送 SEC API 請求。

**不要把真實聯絡資訊填在 README、程式碼或網站 HTML。** 也不要使用不屬於自己的 Email。
這是讀取公開申報內容的「研究資料交叉核對」，不是 SEC 對股票雷達的認證。

核對條件：同公司、同起訖日的單季 10-Q 財務數據、相同 SEC 申報編號和
不得晚於掃描日的申報日期；缺少配對、10-K/累計數、資料來源衝突時不標「一致」。
指標只比較該季營收年增與淨利率，四捨五入容許差為 0.25 個百分點。
任何不一致都顯示警示，不自動用 SEC 數字覆蓋 Yahoo 值。

所有功能仍限固定股票池的研究觀察，非完整產業指數、可執行交易的推薦或歷史回測。
