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

# ==========================================
# 2. 讀取資料函數
# ==========================================
@st.cache_data(ttl=60)
def load_data(url):
    try:
        df = pd.read_csv(url)
        return df
    except Exception as e:
        return None

# ==========================================
# 3. 網頁介面開始
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
        df_stocks["股票代號"] = df_stocks["股票代號"].str.zfill(4)

        # 數值轉換
        def clean_number(x):
            if pd.isna(x) or x == "#N/A" or x == "-":
                return 0
            return pd.to_numeric(str(x).replace(',', '').replace('$', ''), errors='coerce')

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
            # 從原始資料取值
            selected_stock_code = display_df.iloc[selected_index]["股票代號"]
            
            st.info(f"👇 您正在查看 **{selected_stock_code}** 的詳細交易紀錄")

            if df_trans is not None and not df_trans.empty:
                df_trans = df_trans.astype(str)
                if "股票代號" in df_trans.columns:
                    df_trans["股票代號"] = df_trans["股票代號"].str.zfill(4)
                    
                    # 篩選
                    my_trans = df_trans[df_trans["股票代號"] == selected_stock_code].copy()
                    
                    if "投入金額" in my_trans.columns:
                         my_trans = my_trans[my_trans["投入金額"] != "nan"]
                    
                    if not my_trans.empty:
                        st.dataframe(
                            my_trans,
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.warning(f"這支股票 ({selected_stock_code}) 目前還沒有交易紀錄。")
                else:
                    st.error("交易記錄表中找不到「股票代號」欄位。")
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
