# V32.2 — 全台57座球場即時觀測

## 本版範圍

- 以 V31.6 正式版的57座球場名稱、地址及固定座標建立觀測球場清單。
- 每10分鐘讀取一次中央氣象署 O-A0001-001（自動氣象站）及 O-A0002-001（雨量站）。
- 每座球場分別配對最近的氣象站與雨量站；只納入球場設定搜尋半徑30公里內的候選站。
- 寫入 Supabase，並產生公開前端使用的精簡快照 `data/live_observations.json`。
- 前端不得直接取得 Supabase Secret Key；快照只包含觀測欄位、站名、距離、品質狀態及時間，不包含原始API回應或任何金鑰。
- 預覽頁沿用 V31.6 的天氣圖示、逐時預報表及降雨判讀樣式，另外增加即時觀測卡。

## 上線前必做

1. 在 Supabase SQL Editor 先確認 V32.1 migration `202611130001_v32_1_observations.sql` 已執行。
2. 再執行本分支的 `supabase/migrations/202611160001_v32_2_all_course_registry.sql`。
3. 確認 `public.courses` 有57筆 active 球場資料，且 `observation_hourly` 有 `precipitation_10m_mm`、`precipitation_1h_mm` 欄位。
4. 確認 GitHub Actions Secrets 已設定：`CWA_API_KEY`、`SUPABASE_URL`、`SUPABASE_SECRET_KEY`。
5. 合併 V32.2 後，到 Actions 手動執行 `V32.2 Nationwide CWA Live Observation Collector`。
6. 確認 workflow 成功、`data/live_observations.json` 產生，並檢查57座球場各自的 weather/rainfall 欄位是否有資料。
7. 確認 GitHub Pages 自動部署完成，再測試 V32.2 預覽頁。

## 觀測站配對與品質原則

- 配對依球場與氣象站直線距離排序，限30公里內；目前是候選配對，並非已完成地形、海拔、迎風面或遮蔽評估的代表站。
- 天氣站與雨量站分開選擇，兩者可有不同站名、距離及觀測時間。
- 氣溫、濕度、風速、陣風、風向來自 O-A0001-001；近10分鐘與近1小時雨量來自 O-A0002-001。
- 缺漏值保持 null，不得解讀成0。
- 快照及各站觀測時間分開顯示；超過30分鐘標示稍舊，超過60分鐘標示延遲／不足。
- 體感溫度由氣溫、相對濕度及風速估算，前端必須標示「估算」，不可當成氣象站直接量測值。
- 若30公里內沒有可用觀測站，該球場即顯示「尚無即時資料」，不得用其他縣市或預報資料冒充實測。

## 更新頻率及限制

- GitHub Actions 每10分鐘排程一次；實際更新時間仍受 CWA 資料更新頻率、Actions 排程延遲及 Pages 部署時間影響。
- 若收集工作失敗，頁面保留上次快照並以快照時間判斷資料是否過期。
- GitHub Actions 需要允許 workflow 使用 `GITHUB_TOKEN` 寫入 repository contents，才能更新靜態快照。
- 全台57座球場都建立資料結構，不代表57座都一定有30公里內的合適即時觀測站。須以首輪收集後的覆蓋率報告為準。
