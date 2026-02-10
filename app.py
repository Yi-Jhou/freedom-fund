import streamlit as st
import pandas as pd

# ==========================================
# 1. 設定區 (改用 st.secrets 讀取雲端設定)
# ==========================================
try:
    # 讀取總資產儀表板連結
    DASHBOARD_URL = st.secrets["public_sheet_url"]
    # 讀取交易記錄表連結
    TRANS_URL = st.secrets["trans_sheet_url"]
except FileNotFoundError:
    st.error("找不到 Secrets 設定！請在 Streamlit Cloud 後台設定，或在本地建立 .streamlit/secrets.toml")
    st.stop()
except KeyError:
    # 為了方便本地測試，如果沒設 secrets，這裡提供一個備用方案 (可選)
    st.warning("⚠️ 警告：未設定 Secrets，嘗試使用預設連結 (僅供測試用)")
    DASHBOARD_URL = "你的總資產連結" 
    TRANS_URL = "你的交易紀錄連結"

# ==========================================
# 2. 讀取資料函數 (關鍵修正！)
# ==========================================
@st.cache_data(ttl=60)
def load_data(url):
    try:
        # 【修正 1】dtype={'股票代號': str}
        # 這行指令會強迫 Pandas 把「股票代號」這一欄當成文字讀取
        # 這樣 0050 就不會變成 50，00919 也不會變成 919
        df = pd.read_csv(url, dtype={'股票代號': str})
        return df
    except Exception as e:
        return None

# ==========================================
# 3. 資料清理小幫手 (共用函數)
# ==========================================
def clean_stock_code(series):
    # 【修正 2】強力清理邏輯
    return (
        series.astype(str)              # 先轉成字串
        .str.replace(r'\.0$', '', regex=True)  # 把奇怪的 ".0" (如 50.0) 切掉
        .str.strip()                    # 去除前後空白
        .str.zfill(4)                   # 如果少於 4 碼，自動補 0 (如 50 -> 0050)
    )

def clean_number(x):
    if pd.isna(x) or str(x).strip() in ["#N/A", "-", "nan", ""]:
        return 0
    # 只保留數字和小數點
    return pd.to_numeric(str(x).replace(',', '').replace('$', ''), errors='coerce')

# ==========================================
# 4. 網頁介面開始
# ==========================================
st.set_page_config(page_title="阿州 & 建蒼的投資看板", page_icon="📈", layout="wide") 

st.title("💰 我們的存股儀表板")

# 讀取兩份資料
df_dash = load_data(DASHBOARD_URL)
df_trans = load_data(TRANS_URL)

if df_dash is not None and not df_dash.empty:
    try:
        # --- A. 處理儀表板資料 ---
        df_dash = df_dash.astype(str)
        # 過濾「合計」列
        df_stocks = df_dash[~df_dash["股票代號"].str.contains("計|Total", na=False)].copy()
        
        # 應用強力清理
        df_stocks["股票代號"] = clean_stock_code(df_stocks["股票代號"])

        # 數值轉換
        for col in ["總投入本金", "目前市值", "帳面損益", "累積總股數", "平均成本", "目前股價"]:
            if col in df_stocks.columns:
                df_stocks[col] = df_stocks[col].apply(clean_number).fillna(0)
        
        # 過濾 0 股並修正無股價問題
        df_stocks = df_stocks[df_stocks["累積總股數"] > 0].copy()
        mask_missing = (df_stocks["目前市值"] == 0) & (df_stocks["總投入本金"] > 0)
        df_stocks.loc[mask_missing, "目前市值"] = df_stocks.loc[mask_missing, "總投入本金"]
        df_stocks.loc[mask_missing, "帳面損益"] = 0

        # --- B. 顯示上方大數據 ---
        total_cost = df_stocks["總投入本金"].sum()
        total_value = df_stocks["目前市值"].sum()
        total_profit = total_value - total_cost
        roi = (total_profit / total_cost * 100) if total_cost > 0 else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("目前總市值", f"${total_value:,.0f}", delta=f"{total_profit:,.0f} 元")
        col2.metric("總投入本金", f"${total_cost:,.0f}")
        roi_color = "🔴" if roi > 0 else "🟢" if roi < 0 else "⚪"
        col3.metric("總報酬率", f"{roi:.2f}%", delta=roi_color)

        st.divider()

        # --- C. 互動式表格 (點選功能) ---
        st.subheader("📋 持股清單 (點選股票查看明細)")

        display_df = df_stocks[["股票代號", "總投入本金", "累積總股數", "平均成本", "目前股價", "目前市值", "帳面損益"]].copy()

        # 設定顏色函數
        def color_profit(val):
            color = '#ff2b2b' if val > 0 else '#09ab3b' if val < 0 else 'black'
            return f'color: {color}; font-weight: bold'

        event = st.dataframe(
            display_df.style
            .format({
                "總投入本金": "{:,.0f}",
                "目前市值": "{:,.0f}",
                "帳面損益": "{:,.0f}", 
                "平均成本": "{:.2f}",
                "目前股價": "{:.2f}",
                "累積總股數": "{:,.0f}"
            })
            .map(color_profit, subset=['帳面損益'])
            .bar(subset=['帳面損益'], align='mid', color=['#90EE90', '#FFB6C1'])
            .background_gradient(cmap="Blues", subset=['目前市值']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        # --- D. 詳細交易紀錄區 (Drill-down) ---
        if len(event.selection.rows) > 0:
            selected_index = event.selection.rows[0]
            selected_stock_code = display_df.iloc[selected_index]["股票代號"]
            
            st.info(f"👇 您正在查看 **{selected_stock_code}** 的詳細交易紀錄")

            if df_trans is not None and not df_trans.empty:
                # 這裡也要確保欄位名稱正確
                # 為了避免 CSV 欄位名稱有空白 (例如 "股票代號 ")，我們先清理一下欄位名
                df_trans.columns = df_trans.columns.str.strip()
                
                if "股票代號" in df_trans.columns:
                    # 應用同樣的強力清理邏輯，確保兩邊的代號長得一模一樣
                    df_trans["股票代號"] = clean_stock_code(df_trans["股票代號"])
                    
                    # 篩選
                    my_trans = df_trans[df_trans["股票代號"] == selected_stock_code].copy()
                    
                    # 排除空白交易
                    if "投入金額" in my_trans.columns:
                         my_trans = my_trans[my_trans["投入金額"].apply(clean_number) > 0]
                    
                    if not my_trans.empty:
                        # 顯示詳細表格 (只選取重要的欄位)
                        cols_to_show = ["日期", "交易類別", "成交單價", "投入金額", "成交股數", "手續費"]
                        # 確保這些欄位真的存在，避免報錯
                        final_cols = [c for c in cols_to_show if c in my_trans.columns]
                        
                        st.dataframe(
                            my_trans[final_cols],
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.warning(f"這支股票 ({selected_stock_code}) 目前還沒有交易紀錄，或者紀錄中的代號格式不符。")
                else:
                    st.error(f"交易記錄表中找不到「股票代號」欄位。讀到的欄位有：{list(df_trans.columns)}")
            else:
                st.error("無法讀取交易記錄表。")
        else:
            st.caption("👆 請點擊上方表格中的任一股票，這裡就會顯示它的詳細買賣紀錄。")

        # --- 更新按鈕 ---
        if st.button('🔄 立即更新'):
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"程式錯誤：{e}")
else:
    st.error("讀取失敗")
