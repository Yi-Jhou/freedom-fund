import streamlit as st
import pandas as pd

# ==========================================
# 1. 設定區 (讀取雲端 Secrets)
# ==========================================
try:
    DASHBOARD_URL = st.secrets["public_sheet_url"]
    TRANS_URL = st.secrets["trans_sheet_url"]
except FileNotFoundError:
    st.error("找不到 Secrets 設定！請在 Streamlit Cloud 後台設定。")
    st.stop()   
# ==========================================
# 2. 資料處理函數
# ==========================================
@st.cache_data(ttl=60)
def load_data(url):
    try:
        # 強制將股票代號讀為字串，避免 0050 變 50
        df = pd.read_csv(url, dtype={'股票代號': str})
        return df
    except Exception as e:
        return None

def clean_stock_code(series):
    # 強力清理股票代號 (去除 .0, 空白, 補齊4位)
    return (
        series.astype(str)
        .str.replace(r'\.0$', '', regex=True)
        .str.strip()
        .str.zfill(4)
    )

def clean_number(x):
    if pd.isna(x) or str(x).strip() in ["#N/A", "-", "nan", ""]:
        return 0
    return pd.to_numeric(str(x).replace(',', '').replace('$', ''), errors='coerce')

# ==========================================
# 3. 網頁主程式
# ==========================================
st.set_page_config(page_title="雞與虎的投資看板", page_icon="📈", layout="wide") 

st.title("💰 存股儀表板")

# 讀取資料
df_dash = load_data(DASHBOARD_URL)
df_trans = load_data(TRANS_URL)

if df_dash is not None and not df_dash.empty:
    try:
        # --- A. 清理儀表板資料 ---
        df_dash = df_dash.astype(str)
        df_stocks = df_dash[~df_dash["股票代號"].str.contains("計|Total", na=False)].copy()
        
        # 1. 清理股票代號
        df_stocks["股票代號"] = clean_stock_code(df_stocks["股票代號"])

        # 2. 清理數值
        num_cols = ["總投入本金", "目前市值", "帳面損益", "累積總股數", "平均成本", "目前股價"]
        for col in num_cols:
            if col in df_stocks.columns:
                df_stocks[col] = df_stocks[col].apply(clean_number).fillna(0)
        
        # 3. 邏輯修正 (過濾 0 股, 補正市值)
        df_stocks = df_stocks[df_stocks["累積總股數"] > 0].copy()
        mask_missing = (df_stocks["目前市值"] == 0) & (df_stocks["總投入本金"] > 0)
        df_stocks.loc[mask_missing, "目前市值"] = df_stocks.loc[mask_missing, "總投入本金"]
        df_stocks.loc[mask_missing, "帳面損益"] = 0

        # --- B. 顯示上方概況 ---
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

        # --- C. 持股清單 (視覺化表格) ---
        st.subheader("📋 持股清單")

        display_df = df_stocks[["股票代號", "總投入本金", "累積總股數", "平均成本", "目前股價", "目前市值", "帳面損益"]].copy()

        # 【新功能】整列變色邏輯
        def style_row_by_profit(row):
            profit = row['帳面損益']
            # 定義顏色：賺錢紅，賠錢綠
            color = '#ff2b2b' if profit > 0 else '#09ab3b' if profit < 0 else 'black'
            
            # 設定樣式列表 (對應每一個欄位)
            styles = []
            for col in row.index:
                # 只讓「目前市值」和「帳面損益」變色
                if col in ['目前市值', '帳面損益']:
                    styles.append(f'color: {color}; font-weight: bold')
                else:
                    styles.append('') # 其他欄位維持原樣
            return styles

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
            # 1. 套用整列變色 (取代原本的 map)
            .apply(style_row_by_profit, axis=1)
            
            # 2. 保留損益條 (淡色背景條，視覺輔助)
            .bar(subset=['帳面損益'], align='mid', color=['#90EE90', '#FFB6C1']),
            
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        # --- D. 詳細交易紀錄區 ---
        if len(event.selection.rows) > 0:
            selected_index = event.selection.rows[0]
            selected_stock_code = display_df.iloc[selected_index]["股票代號"]
            
            st.info(f"👇 您正在查看 **{selected_stock_code}** 的詳細交易紀錄")

            if df_trans is not None and not df_trans.empty:
                # 清理交易紀錄的欄位與代號
                df_trans.columns = df_trans.columns.str.strip()
                if "股票代號" in df_trans.columns:
                    df_trans["股票代號"] = clean_stock_code(df_trans["股票代號"])
                    
                    # 篩選資料
                    my_trans = df_trans[df_trans["股票代號"] == selected_stock_code].copy()
                    
                    # 排除無效行
                    if "投入金額" in my_trans.columns:
                         my_trans = my_trans[my_trans["投入金額"].apply(clean_number) > 0]
                    
                    if not my_trans.empty:
                        # 顯示表格
                        cols_to_show = ["日期", "交易類別", "成交單價", "投入金額", "成交股數", "手續費"]
                        final_cols = [c for c in cols_to_show if c in my_trans.columns]
                        st.dataframe(my_trans[final_cols], use_container_width=True, hide_index=True)
                    else:
                        st.warning(f"找不到 {selected_stock_code} 的交易紀錄 (可能是交易表記錄尚未填寫)。")
                else:
                    st.error("交易表缺少「股票代號」欄位。")
            else:
                st.error("無法讀取交易記錄表。")
        else:
            st.caption("👆 點擊任一股票，即可顯示詳細買賣紀錄。")

        # --- 更新按鈕 ---
        if st.button('🔄 立即更新'):
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"程式錯誤：{e}")
else:
    st.error("讀取失敗")



