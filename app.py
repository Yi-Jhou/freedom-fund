import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# ==========================================
# 0. 登入系統 (門神)
# ==========================================
st.set_page_config(page_title="🐔&🐯的投資看板", page_icon="📈", layout="wide")

def check_password():
    if st.session_state.get('password_correct', False):
        return True
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("## 🔒 歡迎踏入\n## 🐔🐯大殿堂 ")
        password_input = st.text_input("請輸入神秘數字", type="password")
        if password_input:
            try:
                correct_password = st.secrets["app_password"]
                if password_input == correct_password:
                    st.session_state['password_correct'] = True
                    st.rerun()
                else:
                    st.error("❌密碼錯誤，請贈與🐔一杯五十嵐。 ")
            except KeyError:
                st.error("系統錯誤：未設定密碼 (請檢查 Secrets)")
                return False
    return False

if not check_password():
    st.stop()

# ==========================================
# 1. 設定區
# ==========================================
try:
    DASHBOARD_URL = st.secrets["public_sheet_url"]
    TRANS_URL = st.secrets["trans_sheet_url"]
    MSG_URL = st.secrets["msg_sheet_url"]
    ACT_URL = st.secrets["act_sheet_url"]
    GAS_URL = st.secrets["gas_url"]
    STOCK_MAP_URL = st.secrets["stock_map_url"]
    DIV_URL = st.secrets["div_sheet_url"]
    FUND_URL = st.secrets["fund_sheet_url"]
except (FileNotFoundError, KeyError) as e:
    st.error(f"🔒 錯誤：找不到 Secrets 設定！請檢查 Streamlit Cloud 後台。\n缺少項目: {e}")
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

@st.cache_data(ttl=60)
def load_stock_map():
    try:
        df = pd.read_csv(STOCK_MAP_URL, dtype=str)
        if '股票代號' in df.columns and '股票名稱' in df.columns:
            df['股票代號'] = df['股票代號'].str.strip()
            df['股票名稱'] = df['股票名稱'].str.strip()
            return dict(zip(df['股票代號'], df['股票名稱']))
        return {}
    except:
        return {}

stock_map_dict = load_stock_map()

def clean_stock_code(series):
    return (series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(4))

def clean_number(x):
    if pd.isna(x) or str(x).strip() in ["#N/A", "-", "nan", ""]: return 0
    try:
        return float(str(x).replace(',', '').replace('$', ''))
    except:
        return 0

# ==========================================
# 3. 網頁主程式 (PWA 沉浸式改造)
# ==========================================
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .block-container {
                padding-top: 1.5rem;
                padding-bottom: 2rem;
                padding-left: 1rem;
                padding-right: 1rem;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

col_title, col_btn = st.columns([5, 1], gap="small")
with col_title:
    st.title("💰 存股儀表板")
with col_btn:
    st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)
    if st.button('🔄 更新', help="強制重新讀取 Google Sheet"):
        st.cache_data.clear()
        st.rerun()

# --- A. 智慧公告欄 ---
df_msg = load_data(MSG_URL)
if df_msg is not None and not df_msg.empty:
    try:
        df_msg.columns = df_msg.columns.str.strip()
        if '日期' in df_msg.columns:
            df_msg['日期'] = pd.to_datetime(df_msg['日期'], errors='coerce')
        df_reversed = df_msg.iloc[::-1].reset_index(drop=True)
        if not df_reversed.empty:
            latest = df_reversed.iloc[0]
            l_type = latest['類型'] if '類型' in df_reversed.columns else '一般'
            l_icon, alert_func = "📢", st.info
            if '慶祝' in str(l_type): l_icon, alert_func = "🎉", st.success
            elif '提醒' in str(l_type): l_icon, alert_func = "🔔", st.warning
            elif '緊急' in str(l_type): l_icon, alert_func = "🚨", st.error
            l_date_str = latest['日期'].strftime('%Y-%m-%d') if pd.notna(latest['日期']) else ""
            with st.container():
                alert_func(f"**{l_date_str}**：{latest['內容']}", icon=l_icon)
    except Exception as e: pass

with st.expander("📝 發布新公告"):
    with st.form("public_msg_form"):
        c1, c2 = st.columns([1, 3])
        nt = c1.selectbox("類型", ["🎉 慶祝", "🔔 提醒", "📢 一般", "🚨 緊急"])
        nc = c2.text_input("內容", placeholder="想在看板上說些什麼呢？")
        if st.form_submit_button("送出公告"):
            if nc.strip():
                requests.post(GAS_URL, json={"action": "msg", "date": datetime.now().strftime("%Y-%m-%d"), "type": nt, "content": nc})
                st.toast("✅ 公告已發布！"); st.cache_data.clear(); st.rerun()

# --- B. 核心數據處理 (自動對帳邏輯) ---
df_dash = load_data(DASHBOARD_URL)
df_trans = load_data(TRANS_URL)
df_div = load_data(DIV_URL)
df_fund = load_data(FUND_URL)

# 1. 統計可用餘額與本金邏輯
total_fund_in = 0
total_cash_spent = 0
total_cash_revenue = 0
total_unused_div = 0
reinvest_dict = {}

if df_fund is not None and not df_fund.empty:
    total_fund_in = df_fund['金額'].apply(clean_number).sum()

if df_trans is not None and not df_trans.empty:
    df_trans_clean = df_trans.copy()
    df_trans_clean.columns = df_trans_clean.columns.str.strip()
    df_trans_clean['股票代號'] = clean_stock_code(df_trans_clean['股票代號'])
    df_trans_clean['投入金額'] = df_trans_clean['投入金額'].apply(clean_number)
    
    # 統計「真實口袋掏出的錢」
    mask_reinvest = df_trans_clean['股息再投入'].astype(str).str.strip().isin(['Y', '✅', '✔️'])
    reinvest_dict = df_trans_clean[mask_reinvest & (df_trans_clean['交易類別'] == '買入')].groupby('股票代號')['投入金額'].sum().to_dict()
    
    # 計算可用餘額用的現金支出 (不含股息再投入)
    total_cash_spent = df_trans_clean[(df_trans_clean['交易類別'] == '買入') & (~mask_reinvest)]['投入金額'].sum()
    total_cash_revenue = df_trans_clean[df_trans_clean['交易類別'] == '賣出']['投入金額'].sum()

# 2. 股利處理
total_div_all = 0
if df_div is not None and not df_div.empty:
    df_div.columns = df_div.columns.str.strip()
    df_div['實領金額'] = df_div['實領金額'].apply(clean_number)
    total_div_all = df_div['實領金額'].sum()
    total_unused_div = df_div[df_div['狀態'].fillna("未使用") == "未使用"]['實領金額'].sum()

# 3. 儀表板整合
if df_dash is not None and not df_dash.empty:
    df_stocks = df_dash[~df_dash["股票代號"].astype(str).str.contains("計|Total", na=False)].copy()
    df_stocks["股票代號"] = clean_stock_code(df_stocks["股票代號"])
    for col in ["總投入本金", "目前市值", "帳面損益", "累積總股數", "目前股價"]:
        if col in df_stocks.columns: df_stocks[col] = df_stocks[col].apply(clean_number).fillna(0)
    
    # 算法B: 扣除再投入本金
    df_stocks['再投入金額'] = df_stocks['股票代號'].map(reinvest_dict).fillna(0)
    df_stocks['總投入本金'] = (df_stocks['總投入本金'] - df_stocks['再投入金額']).apply(lambda x: max(x, 0))
    df_stocks['帳面損益'] = df_stocks['目前市值'] - df_stocks['總投入本金']
    
    total_cost = df_stocks["總投入本金"].sum()
    total_value = df_stocks["目前市值"].sum()
    total_profit = total_value - total_cost
    
    # 可用餘額 = 總入金 - 現金買入 + 賣出收入 + 未使用股息
    cash_balance = total_fund_in - total_cash_spent + total_cash_revenue + total_unused_div
    
    # --- 繪製 5 大核心數據 ---
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("真實投入本金", f"${total_cost:,.0f}")
    c2.metric("目前總市值", f"${total_value:,.0f}", delta=f"{'🔴' if total_profit>0 else '🟢'} 帳面損益 {total_profit:,.0f}", delta_color="off")
    c3.metric("🏦 可用現金餘額", f"${cash_balance:,.0f}", help="總入金 - 買入支出 + 賣出收入 + 未使用股息")
    c4.metric("💰 累積已領股息", f"${total_div_all:,.0f}", delta=f"未使用股息: ${total_unused_div:,.0f}", delta_color="normal")
    
    total_profit_with_div = total_profit + total_div_all
    roi_with_div = (total_profit_with_div / total_cost * 100) if total_cost > 0 else 0
    c5.metric("📈 含息總報酬率", f"{roi_with_div:.2f}%", delta=f"{'🔴' if roi_with_div>0 else '🟢'} 真實獲利 {total_profit_with_div:,.0f}", delta_color="off")
    st.divider()

    # --- D. 持股清單 (省略部分顯示邏輯以維持精簡) ---
    st.subheader("📋 持股清單")
    display_df = df_stocks[["股票代號", "目前市值", "帳面損益", "總投入本金", "目前股價", "累積總股數"]].copy()
    display_df["顯示名稱"] = display_df["股票代號"].map(stock_map_dict).fillna("")
    display_df["股票代號"] = display_df.apply(lambda x: f"{x['股票代號']} ({x['顯示名稱']})" if x['顯示名稱'] else x['股票代號'], axis=1)
    
    st.dataframe(display_df.style.format({"總投入本金": "{:,.0f}", "目前市值": "{:,.0f}", "帳面損益": "{:,.0f}", "目前股價": "{:.2f}", "累積總股數": "{:,.0f}"}), use_container_width=True, hide_index=True)

# ==========================================
# 4. 管理員專區
# ==========================================
st.markdown("---") 
st.markdown("### ⚙️ 後台管理")
with st.expander("🔧 點擊開啟管理面板"):
    if not st.session_state.get('admin_logged_in', False):
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password")
        if admin_input == st.secrets["admin_password"]:
            st.session_state['admin_logged_in'] = True; st.rerun()
    else:
        t1, t2, t3, t4, t5 = st.tabs(["🏷️ 股票", "💸 資金入帳", "📝 交易紀錄", "💰 新增股利", "🏦 管理股利"])

        with t2:
            with st.form("fund_form"):
                fd = st.date_input("日期", datetime.now())
                fn = st.selectbox("姓名", ["建蒼", "奕州"])
                fa = st.number_input("金額 (出金請輸入負數)", step=1000)
                if st.form_submit_button("入帳"):
                    requests.post(GAS_URL, json={"action": "fund", "date": fd.strftime("%Y-%m-%d"), "name": fn, "amount": fa})
                    st.toast("✅ 資金紀錄已更新！"); st.cache_data.clear()

        with t3:
            st.info("💡 **【股票分割 / 配股操作指南】**\n1. 類別選「股票分割 (配股)」\n2. 單價輸入 0\n3. 股數輸入「額外多拿到」的數量")
            with st.form("trade_form"):
                td = st.date_input("日期", datetime.now())
                opts = [f"{k} ({v})" for k, v in stock_map_dict.items()] if stock_map_dict else ["0050"]
                ts = st.selectbox("代號", opts).split(" ")[0]
                tt = st.selectbox("類別", ["買入", "賣出", "股票分割 (配股)"])
                tp = st.number_input("成交單價", value=0.0)
                tsh = st.number_input("成交股數", step=100)
                ir = st.checkbox("定期定額", True)
                id = st.checkbox("股息再投入", False)
                if st.form_submit_button("記錄交易"):
                    tot = int(tp * tsh)
                    requests.post(GAS_URL, json={"action": "trade", "date": td.strftime("%Y-%m-%d"), "stock": ts, "type": tt, "price": tp, "total": tot, "shares": tsh, "regular": "✔️" if ir else "❌", "dividend": "✔️" if id else "❌"})
                    st.toast("✅ 交易已記錄！"); st.cache_data.clear()

        with t4:
            # (此處沿用之前優化過的即時連動股利表單邏輯...)
            st.write("請使用之前提供的即時連動股利表單程式碼填入此處")
