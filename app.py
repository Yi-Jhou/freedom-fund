import streamlit as st
import pandas as pd

# ==========================================
# 1. 設定區 (請填入兩份 CSV 的連結)
# ==========================================
# A. 總資產儀表板 (原本的)
DASHBOARD_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTH3RrFjPN4B4FU_hIScIIbAJ1F0-xERCwOwG-w6svMDU5_fwmOnm0eTXjElqm_gED2Y7_3chlOcoo9/pub?gid=1772726386&single=true&output=csv"

# B. 交易記錄表 (請把剛剛複製的新連結貼在下面引號內！)
TRANS_URL = "你的_交易記錄表_CSV連結_貼在這裡"

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

        # --- C. 互動式表格 (點擊功能) ---
        st.subheader("📋 持股清單 (點選股票可查看明細)")

        display_df = df_stocks[["股票代號", "目前市值", "帳面損益", "總投入本金", "累積總股數", "平均成本", "目前股價"]].copy()

        # 設定選取事件 (selection_mode='single-row')
        event = st.dataframe(
            display_df,
            column_config={
                "股票代號": st.column_config.TextColumn("股票代號", help="點擊查看詳細交易"),
                "目前市值": st.column_config.ProgressColumn("目前市值 (佔比)", format="$%d", min_value=0, max_value=int(display_df["目前市值"].max() * 1.2)),
                "帳面損益": st.column_config.NumberColumn("帳面損益", format="%d 元"),
                "總投入本金": st.column_config.NumberColumn("總投入本金", format="$%d"),
                "累積總股數": st.column_config.NumberColumn("股數", format="%d 股"),
                "平均成本": st.column_config.NumberColumn("平均成本", format="$%.2f"),
                "目前股價": st.column_config.NumberColumn("目前股價", format="$%.2f"),
            },
            use_container_width=True,
            hide_index=True,
            on_select="rerun",      # 點擊後重新執行
            selection_mode="single-row" # 一次只能選一行
        )

        # --- D. 詳細交易紀錄區 (Drill-down) ---
        if len(event.selection.rows) > 0:
            # 1. 抓出使用者點了哪一支股票
            selected_index = event.selection.rows[0]
            selected_stock_code = display_df.iloc[selected_index]["股票代號"]
            
            st.info(f"👇 您正在查看 **{selected_stock_code}** 的詳細交易紀錄")

            # 2. 處理交易紀錄資料
            if df_trans is not None and not df_trans.empty:
                df_trans = df_trans.astype(str)
                df_trans["股票代號"] = df_trans["股票代號"].str.zfill(4) # 確保代號格式一致
                
                # 篩選出這支股票的資料
                my_trans = df_trans[df_trans["股票代號"] == selected_stock_code].copy()
                
                # 清理一下無用的空白行 (如果還沒填資料的話)
                my_trans = my_trans[my_trans["投入金額"] != "nan"]
                
                if not my_trans.empty:
                    st.dataframe(
                        my_trans[["日期", "交易類別", "成交單價", "投入金額", "成交股數", "手續費"]],
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.warning("這支股票目前還沒有交易紀錄。")
            else:
                st.error("無法讀取交易記錄表，請檢查連結設定。")
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
