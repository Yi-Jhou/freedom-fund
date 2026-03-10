from playwright.sync_api import sync_playwright
import time

# 請替換成你的 Streamlit App 網址
URL = "https://freedom-fund-pfchwygorvhsrkuad3amcq.streamlit.app/#2d2efafd"

def run():
    with sync_playwright() as p:
        # 啟動 Chromium 瀏覽器 (無頭模式)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print(f"正在前往: {URL}")
        # 前往網址，並等待網路閒置，確保基礎資源載入
        page.goto(URL, wait_until="networkidle")
        
        # 強制等待 10 秒，確保 Streamlit 的 WebSocket 連線完全建立並判定為活躍
        print("等待 10 秒讓 Streamlit 建立 WebSocket 連線...")
        time.sleep(10)
        
        # 截圖存檔 (選用功能，方便你在 GitHub Actions 紀錄中檢查是否載入成功)
        # page.screenshot(path="screenshot.png")
        
        print("喚醒完成！關閉瀏覽器。")
        browser.close()

if __name__ == "__main__":
    run()
