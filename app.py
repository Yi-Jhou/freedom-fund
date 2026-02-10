import streamlit as st
import pandas as pd
from datetime import datetime

# ==========================================
# 0. 登入系統 (門神)
# ==========================================
# 必須放在所有程式的最前面
st.set_page_config(page_title="雞與虎的投資看板", page_icon="📈", layout="wide") 

def check_password():
    """回傳 True 代表密碼正確，False 代表尚未登入或錯誤"""
    
    # 1. 如果已經登入成功過，就直接放行
    if st.session_state.get('password_correct', False):
        return True

    # 2. 顯示輸入框 (使用你的專屬文字)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.header("🔒 歡迎踏入雞虎大殿堂")
        password_input = st.text_input("請輸入神秘數字", type="password")

        # 3. 驗證邏輯
        if password_input:
            try:
                correct_password = st.secrets["app_password"]
                if password_input == correct_password:
                    st.session_state['password_correct'] = True
                    st.rerun()  # 密碼對了，重新整理頁面進入
                else:
                    st.error("密碼錯誤 ❌")
            except KeyError:
                st.error("系統錯誤：未設定密碼 (請檢查 Secrets)")
                return False
    
    return False

# ★★★ 關鍵點：如果 check_password() 回傳 False，就直接停止執行 ★★★
if not check_password():
    st.stop()  # 程式執行到這裡就會卡住，下面的程式碼完全不會跑

# ==========================================
# 1. 設定區 (讀取 3 個連結)
# ==========================================
try:
    DASHBOARD_URL = st.secrets["public_sheet_url"]
    TRANS_URL = st.secrets["trans_sheet_url"]
    MSG_URL = st.secrets["msg_sheet_url"] # 保留公告欄連結
except (FileNotFoundError, KeyError):
    st.error("🔒 錯誤：找不到 Secrets 設定！請在 Streamlit Cloud 後台設定。")
    st.stop()

# ==========================================
# 2. 資料處理函數
# ==========================================
@st.cache_data(ttl=60)
def load_data(url):
    try:
        df = pd.read_csv(url, dtype={'股票代號': str})
        return df
    except Exception as e:
        return None

def clean_stock_code(series):
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
st.title("💰 存股儀表板")

# --- 🔥 新功能：智慧公告欄 (保留功能) ---
df_msg = load_data(MSG_URL)

if df_msg is not None and not df_msg.empty:
    try:
        df_msg.columns = df_msg.columns.str.strip()
        if '日期' in df_msg.columns and '內容' in df_msg.columns:
            df_msg['日期'] = pd.to_datetime(df_msg['日期'], errors='coerce')
            df_msg = df_msg.dropna(subset=['日期'])
            
            if not df_msg.empty:
                latest_msg = df_msg.sort_values(by='日期', ascending=False).iloc[0]
                msg_content = latest_msg['內容']
                msg_date = latest_msg['日期'].strftime('%Y-%m-%d')
                msg_type = latest_msg['類型'] if '類型' in df_msg.columns else '一般'
                
                if '慶祝' in str(msg_type):
                    icon, alert_type = "🎉", "success"
                elif '提醒' in str(msg_type) or '重要' in str(msg_type):
                    icon, alert_type = "🔔", "warning"
                elif '緊急' in str(msg_type):
                    icon, alert_type = "🚨", "error"
                else:
                    icon, alert_type = "📢", "info"

                with st.container():
                    if alert_type == "success": st.success(f"**{msg_date} 公告**：{msg_content}", icon=icon)
                    elif alert_type == "warning": st.warning(f"**{msg_date} 公告**：{msg_content}", icon=icon)
                    elif alert_type == "error": st.error(f"**{msg_date} 公告**：{msg_content}", icon=icon)
                    else: st.info(f"**{msg_date} 公告**：{msg_content}", icon=icon)
    except Exception:
        pass

# 讀取主要資料
df_dash = load_data(DASHBOARD_URL)
df_trans = load_data(TRANS_URL)

if df_dash is not None and not df_dash.empty:
    try:
        # --- A. 清理資料 ---
        df_dash = df_dash.astype(str)
        df_stocks = df_dash[~df_dash["股票代號"].str.contains("計|Total", na=False)].copy()
        df_stocks["股票代號"] = clean_stock_code(df_stocks["股票代號"])

        for col in ["總投入本金", "目前市值", "帳面損益", "累積總股數", "平均成本", "目前股價"]:
            if col in df_stocks.columns:
                df_stocks[col] = df_stocks[col].apply(clean_number).fillna(0)
        
        df_stocks = df_stocks[df_stocks["累積總股數"] > 0].copy()
        mask_missing = (df_stocks["目前市值"] == 0) & (df_stocks["總投入本金"] > 0)
        df_stocks.loc[mask_missing, "目前市值"] = df_stocks.loc[mask_missing, "總投入本金"]
        df_stocks.loc[mask_missing, "帳面損益"] = 0

        # --- B. 核心指標 ---
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

        # --- C. 持股清單 ---
        st.subheader("📋 持股清單")
        display_df = df_stocks[["股票代號", "目前市值", "帳面損益", "總投入本金", "目前股價", "累積總股數"]].copy()

        def style_row_by_profit(row):
            profit = row['帳面損益']
            color = '#ff2b2b' if profit > 0 else '#09ab3b' if profit < 0 else 'black'
            styles = []
            for col in row.index:
                if col in ['目前市值', '帳面損益']:
                    styles.append(f'color: {color}; font-weight: bold')
                else:
                    styles.append('')
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
            .apply(style_row_by_profit, axis=1)
            .bar(subset=['帳面損益'], align='mid', color=['#90EE90', '#FFB6C1']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        # --- D. 詳細交易紀錄 ---
        if len(event.selection.rows) > 0:
            selected_index = event.selection.rows[0]
            selected_stock_code = display_df.iloc[selected_index]["股票代號"]
            
            with st.container(border=True):
                st.info(f"👇 **{selected_stock_code}** 詳細交易紀錄")
                if df_trans is not None and not df_trans.empty:
                    df_trans.columns = df_trans.columns.str.strip()
                    if "股票代號" in df_trans.columns:
                        df_trans["股票代號"] = clean_stock_code(df_trans["股票代號"])
                        my_trans = df_trans[df_trans["股票代號"] == selected_stock_code].copy()
                        if "投入金額" in my_trans.columns:
                             my_trans = my_trans[my_trans["投入金額"].apply(clean_number) > 0]
                        if not my_trans.empty:
                            cols_to_show = ["日期", "交易類別", "成交單價", "投入金額", "成交股數"]
                            final_cols = [c for c in cols_to_show if c in my_trans.columns]
                            st.dataframe(my_trans[final_cols], use_container_width=True, hide_index=True)
                        else:
                            st.warning(f"尚無交易紀錄。")
                    else:
                        st.error("交易表格式錯誤。")
                else:
                    st.error("無法讀取交易表。")
        else:
            st.caption("👆 (手機請左滑) 點擊股票可查看明細")

        if st.button('🔄 立即更新'):
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"程式錯誤：{e}")
else:
    st.error("讀取失敗，請檢查 Secrets 設定。")
