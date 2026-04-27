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
        st.markdown("## 歡迎踏入\n## 🐔🐯大殿堂 ")
        password_input = st.text_input("🔒 請輸入神秘數字", type="password")
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
    FUND_URL = st.secrets["fund_sheet_url"]  # 新增資金表網址
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
# 3. 網頁主程式
# ==========================================
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

with st.expander("📝 發布新公告 "):
    with st.form("public_msg_form"):
        c1, c2 = st.columns([1, 3])
        nt = c1.selectbox("類型", ["🎉 慶祝", "🔔 提醒", "📢 一般", "🚨 緊急"])
        nc = c2.text_input("內容", placeholder="想在看板上說些什麼呢？")
        if st.form_submit_button("送出公告"):
            if nc.strip():
                requests.post(GAS_URL, json={"action": "msg", "date": datetime.now().strftime("%Y-%m-%d"), "type": nt, "content": nc})
                st.toast("✅ 公告已發布！"); st.cache_data.clear(); st.rerun()

# --- B. 儀表板核心數據 (5 大看板升級版) ---
df_dash = load_data(DASHBOARD_URL)
df_trans = load_data(TRANS_URL)
df_div = load_data(DIV_URL)
df_fund = load_data(FUND_URL)

# 1. 計算可用餘額邏輯 (關鍵對帳邏輯)
total_fund_in = 0  # 總入金
total_cash_out = 0 # 現金買入支出
total_cash_rev = 0 # 賣出股票收入
total_unused_div = 0 # 未使用股息
reinvest_dict = {}

# (1) 統計資金進出
if df_fund is not None and not df_fund.empty:
    total_fund_in = df_fund['金額'].apply(clean_number).sum()

# (2) 統計交易現金流 (排除股息再投入)
if df_trans is not None and not df_trans.empty:
    df_t = df_trans.copy()
    df_t.columns = df_t.columns.str.strip()
    df_t['股票代號'] = clean_stock_code(df_t['股票代號'])
    df_t['投入金額'] = df_t['投入金額'].apply(clean_number)
    
    # 識別股息再投入
    mask_reinvest = df_t['股息再投入'].astype(str).str.strip().isin(['Y', '✅', '✔️'])
    
    # 計算買入支出 (僅統計非再投入的買入)
    total_cash_out = df_t[(df_t['交易類別'] == '買入') & (~mask_reinvest)]['投入金額'].sum()
    # 計算賣出收入
    total_cash_rev = df_t[df_t['交易類別'] == '賣出']['投入金額'].sum()
    # 計算用於算法 B 的各股再投入總額
    reinvest_dict = df_t[mask_reinvest & (df_t['交易類別'] == '買入')].groupby('股票代號')['投入金額'].sum().to_dict()

# (3) 統計股利與閒置資金
total_div_all = 0
if df_div is not None and not df_div.empty:
    df_div.columns = df_div.columns.str.strip()
    df_div['實領金額'] = df_div['實領金額'].apply(clean_number)
    total_div_all = df_div['實領金額'].sum()
    # 累積尚未使用的股息
    total_unused_div = df_div[df_div['狀態'].fillna("未使用") == "未使用"]['實領金額'].sum()

# (4) 統整 5 大指標
if df_dash is not None and not df_dash.empty:
    try:
        df_stocks = df_dash[~df_dash["股票代號"].astype(str).str.contains("計|Total", na=False)].copy()
        df_stocks["股票代號"] = clean_stock_code(df_stocks["股票代號"])
        for col in ["總投入本金", "目前市值", "帳面損益", "累積總股數", "平均成本", "目前股價"]:
            if col in df_stocks.columns: df_stocks[col] = df_stocks[col].apply(clean_number).fillna(0)
        
        # 修正算法 B：真實口袋本金 (扣除再投入)
        df_stocks['再投入金額'] = df_stocks['股票代號'].map(reinvest_dict).fillna(0)
        df_stocks['總投入本金'] = (df_stocks['總投入本金'] - df_stocks['再投入金額']).apply(lambda x: max(x, 0))
        df_stocks['帳面損益'] = df_stocks['目前市值'] - df_stocks['總投入本金']
        
        total_cost = df_stocks["總投入本金"].sum()
        total_value = df_stocks["目前市值"].sum()
        total_profit = total_value - total_cost
        
        # ★ 計算可用餘額 = 總入金 - 現金買入支出 + 賣出收入 + 未使用股息
        available_cash = total_fund_in - total_cash_out + total_cash_rev + total_unused_div
        
        # 繪製 5 大看板
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("真實投入本金", f"${total_cost:,.0f}")
        col2.metric("目前總市值", f"${total_value:,.0f}", delta=f"{total_profit:,.0f} 元 (帳面損益)", delta_color="inverse")
        col3.metric("🏦 可用現金餘額", f"${available_cash:,.0f}", help="總入金 - 真實買入花費 + 賣出收入 + 閒置股息")
        col4.metric("💰 累積已領股息", f"${total_div_all:,.0f}", delta=f"未使用: ${total_unused_div:,.0f}", delta_color="normal")
        
        total_profit_with_div = total_profit + total_div_all
        roi_with_div = (total_profit_with_div / total_cost * 100) if total_cost > 0 else 0
        col5.metric("📈 含息總報酬率", f"{roi_with_div:.2f}%", delta=f"{total_profit_with_div:,.0f} 元 (真實獲利)", delta_color="inverse")
        
        st.caption("💡 註：系統已自動根據資金表與交易表對帳，呈現證券帳戶真實可用餘額與投入成本。")
        st.divider()

        # --- D. 持股清單 ---
        st.subheader("📋 持股清單")
        # 此處省略單檔股票含息報酬計算，維持原先邏輯...
        display_df = df_stocks[["股票代號", "目前市值", "帳面損益", "總投入本金", "目前股價", "累積總股數"]].copy()
        display_df["顯示名稱"] = display_df["股票代號"].map(stock_map_dict).fillna("")
        display_df["股票代號"] = display_df.apply(lambda x: f"{x['股票代號']} ({x['顯示名稱']})" if x['顯示名稱'] else x['股票代號'], axis=1)
        
        st.dataframe(display_df.style.format({"總投入本金": "{:,.0f}", "目前市值": "{:,.0f}", "帳面損益": "{:,.0f}", "目前股價": "{:.2f}", "累積總股數": "{:,.0f}"}), use_container_width=True, hide_index=True)

    except Exception as e: st.error(f"核心計算錯誤：{e}")

# ==========================================
# 4. 管理員專區
# ==========================================
st.markdown("---") 
st.markdown("### ⚙️ 後台管理")
with st.expander("🔧 點擊開啟管理面板"):
    if not st.session_state.get('admin_logged_in', False):
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password", key="admin_pass")
        if admin_input == st.secrets["admin_password"]:
            st.session_state['admin_logged_in'] = True; st.rerun()
    else:
        st.success("🔓 管理員模式已啟用")
        t1, t2, t3, t4, t5 = st.tabs(["🏷️ 股票", "💸 資金入帳", "📝 交易紀錄", "💰 新增股利", "🏦 管理股利"])

        with t2:
            st.info("紀錄匯入或匯出證券交割戶的款項 (出金請輸入負數)")
            with st.form("fund_form"):
                fd = st.date_input("日期", datetime.now())
                fn = st.selectbox("姓名", ["建蒼", "奕州"])
                fa = st.number_input("金額", step=1000, value=0)
                if st.form_submit_button("入帳"):
                    requests.post(GAS_URL, json={"action": "fund", "date": fd.strftime("%Y-%m-%d"), "name": fn, "amount": fa})
                    st.toast("✅ 資金紀錄已更新！"); st.cache_data.clear(); st.rerun()

        with t3:
            st.info("💡 **【股票分割 / 配股操作指南】**\n1. 類別選「股票分割 (配股)」\n2. 單價輸入 0\n3. 股數輸入「額外多拿到」的數量")
            # 偵測股票切換以自動帶入股數...
            opts = [f"{k} ({v})" for k, v in stock_map_dict.items()] if stock_map_dict else ["0050"]
            sel = st.selectbox("代號", opts + ["🖊️ 自行輸入"], key="trade_stock_sel")
            ts = st.text_input("輸入代號", key="trade_stock_input").strip() if sel == "🖊️ 自行輸入" else sel.split(" ")[0]
            
            with st.form("trade_form"):
                td = st.date_input("日期", datetime.now())
                tt = st.selectbox("類別", ["買入", "賣出", "股票分割 (配股)"])
                tp = st.number_input("成交單價", step=0.1, format="%.2f", value=0.0)
                tsh = st.number_input("成交股數", step=100, value=0)
                ir = st.checkbox("定期定額", True)
                id = st.checkbox("股息再投入", False)
                if st.form_submit_button("記錄交易"):
                    tot = int(tp * tsh)
                    requests.post(GAS_URL, json={"action": "trade", "date": td.strftime("%Y-%m-%d"), "stock": ts, "type": tt, "price": tp, "total": tot, "shares": tsh, "regular": "✔️" if ir else "❌", "dividend": "✔️" if id else "❌"})
                    st.toast("✅ 交易已記錄！"); st.cache_data.clear(); st.rerun()

        with t4:
            # (此處保留你之前指定的「即時連動股利表單」邏輯...)
            st.caption("💡 系統已升級「即時連動」：選好股票後，會自動帶入現有股數，並幫你算好實領金額！")
            opts = [f"{k} ({v})" for k, v in stock_map_dict.items()] if stock_map_dict else ["0050"]
            div_sel = st.selectbox("代號", opts + ["🖊️ 自行輸入"], key="div_stock_sel")
            div_ds = st.text_input("輸入代號", key="div_stock_input").strip() if div_sel == "🖊️ 自行輸入" else div_sel.split(" ")[0]
            
            # 自動抓取股數邏輯
            curr_shares = 0
            if 'df_stocks' in locals() and not df_stocks.empty:
                matched = df_stocks[df_stocks["股票代號"] == div_ds]
                if not matched.empty: curr_shares = int(matched["累積總股數"].sum())

            div_dd = st.date_input("發放日", datetime.now(), key="div_date")
            div_sea = st.selectbox("季度", ["Q1", "Q2", "Q3", "Q4", "上半年", "下半年", "年度"], key="div_season")
            div_dh = st.number_input("除息股數", value=curr_shares, key="div_sh_val")
            div_dp = st.number_input("配息單價", step=0.01, format="%.3f")
            div_total = int(div_dh * div_dp)
            st.markdown(f"#### 💰 預計實領金額： <span style='color:#ff2b2b'>**${div_total:,.0f}**</span>", unsafe_allow_html=True)
            
            if st.button("記錄股利", type="primary", use_container_width=True):
                requests.post(GAS_URL, json={"action": "dividend", "date": div_dd.strftime("%Y-%m-%d"), "stock": div_ds, "season": div_sea, "held_shares": div_dh, "div_price": div_dp, "total": div_total})
                st.toast("✅ 股利已寫入！"); st.cache_data.clear(); st.rerun()
