import streamlit as st
import pandas as pd

# ==========================================
# 1. 設定區
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTH3RrFjPN4B4FU_hIScIIbAJ1F0-xERCwOwG-w6svMDU5_fwmOnm0eTXjElqm_gED2Y7_3chlOcoo9/pub?gid=1772726386&single=true&output=csv"

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
st.caption("目前持有標的")

# 讀取資料
df = load_data(SHEET_URL)

if df is not None and not df.empty:
    try:
        # --- 資料清理 ---
        df = df.astype(str)
        # 過濾「合計」列
        df_stocks = df[~df["股票代號"].str.contains("計|Total", na=False)].copy()
        df_stocks["股票代號"] = df_stocks["股票代號"].str.zfill(4)

        # 數值轉換
        def clean_number(x):
            if pd.isna(x) or x == "#N/A" or x == "-":
                return 0
            return pd.to_numeric(str(x).replace(',', '').replace('$', ''), errors='coerce')

        num_cols = ["總投入本金", "目前市值", "帳面損益", "累積總股數", "平均成本", "目前股價"]
        for col in num_cols:
            if col in df_stocks.columns:
                df_stocks[col] = df_stocks[col].apply(clean_number).fillna(0)
        
        # 過濾掉股數為 0 的股票
        df_stocks = df_stocks[df_stocks["累積總股數"] > 0].copy()

        # 處理 009816 缺股價問題
        mask_missing_price = (df_stocks["目前市值"] == 0) & (df_stocks["總投入本金"] > 0)
        df_stocks.loc[mask_missing_price, "目前市值"] = df_stocks.loc[mask_missing_price, "總投入本金"]
        df_stocks.loc[mask_missing_price, "帳面損益"] = 0

        if not df_stocks.empty:
            # --- 計算區 ---
            total_cost = df_stocks["總投入本金"].sum()
            total_value = df_stocks["目前市值"].sum()
            total_profit = total_value - total_cost
            roi = (total_profit / total_cost * 100) if total_cost > 0 else 0

            # --- A. 核心指標區 ---
            col1, col2, col3 = st.columns(3)
            col1.metric("目前總市值", f"${total_value:,.0f}", delta=f"{total_profit:,.0f} 元")
            col2.metric("總投入本金", f"${total_cost:,.0f}")
            
            roi_color = "🔴" if roi > 0 else "🟢" if roi < 0 else "⚪"
            col3.metric("總報酬率", f"{roi:.2f}%", delta=roi_color)

            st.divider()

            # --- B. 持股明細表格 ---
            st.subheader("📋 詳細數據")

            display_df = df_stocks[["股票代號", "總投入本金", "累積總股數", "平均成本", "目前股價", "目前市值", "帳面損益"]].copy()

            # 【新功能】設定顏色邏輯：這行會同時檢查每一列的損益
            # 如果賺錢，"目前市值" 和 "帳面損益" 都會變紅字
            def color_row_based_on_profit(row):
                profit = row['帳面損益']
                color = '#ff2b2b' if profit > 0 else '#09ab3b' if profit < 0 else 'black'
                # 回傳樣式：只對 '目前市值' 和 '帳面損益' 兩欄上色
                return [f'color: {color}; font-weight: bold' if col in ['目前市值', '帳面損益'] else '' for col in row.index]

            # 顯示表格
            st.dataframe(
                display_df.style
                .format({
                    "總投入本金": "{:,.0f}",
                    "目前市值": "{:,.0f}",
                    "帳面損益": "{:,.0f}", 
                    "平均成本": "{:.2f}",
                    "目前股價": "{:.2f}",
                    "累積總股數": "{:,.0f}"
                })
                # 1. 套用整列變色邏輯 (取代原本的 map)
                .apply(color_row_based_on_profit, axis=1)
                
                # 2. 保留損益條 (淡紅/淡綠背景條)
                .bar(subset=['帳面損益'], align='mid', color=['#90EE90', '#FFB6C1']),
                
                # 3. (已移除) 藍色漸層背景 .background_gradient...
                
                use_container_width=True,
                hide_index=True
            )

            if mask_missing_price.any():
                st.warning("⚠️ 部分股票暫無股價，市值以成本計算。")
        else:
            st.info("目前沒有持有任何股票（股數皆為 0）。")

        # --- 更新按鈕 ---
        if st.button('🔄 立即更新'):
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"程式錯誤：{e}")
else:
    st.error("讀取失敗")