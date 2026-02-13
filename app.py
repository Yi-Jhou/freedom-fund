import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# ==========================================
# 0. 登入系統 (門神)
# ==========================================
st.set_page_config(page_title="雞與虎的投資看板", page_icon="📈", layout="wide")

def check_password():
    if st.session_state.get('password_correct', False):
        return True
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("## 🔒 歡迎踏入\n## 雞虎大殿堂 🐔🐯")
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
            if len(df_reversed) > 1:
                with st.expander("📜 查看近期公告"):
                    for index, row in df_reversed.iloc[1:6].iterrows():
                        d_str = row['日期'].strftime('%Y-%m-%d') if pd.notna(row['日期']) else ""
                        st.write(f"• **{d_str}** ({row.get('類型','-')})：{row['內容']}")
    except Exception as e: pass

# --- B. 儀表板核心數據 ---
df_dash = load_data(DASHBOARD_URL)
df_trans = load_data(TRANS_URL)
df_div = load_data(DIV_URL)

if df_dash is not None and not df_dash.empty:
    try:
        df_dash = df_dash.astype(str)
        df_stocks = df_dash[~df_dash["股票代號"].str.contains("計|Total", na=False)].copy()
        df_stocks["股票代號"] = clean_stock_code(df_stocks["股票代號"])
        for col in ["總投入本金", "目前市值", "帳面損益", "累積總股數", "平均成本", "目前股價"]:
            if col in df_stocks.columns: df_stocks[col] = df_stocks[col].apply(clean_number).fillna(0)
        df_stocks = df_stocks[df_stocks["累積總股數"] > 0].copy()
        mask_missing = (df_stocks["目前市值"] == 0) & (df_stocks["總投入本金"] > 0)
        df_stocks.loc[mask_missing, "目前市值"] = df_stocks.loc[mask_missing, "總投入本金"]
        df_stocks.loc[mask_missing, "帳面損益"] = 0
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

        # --- C. 最新動態 ---
        st.subheader("⚡ 最新動態 (近 30 天)")
        df_act = load_data(ACT_URL)
        if df_act is not None and not df_act.empty:
            try:
                df_act.columns = df_act.columns.str.strip()
                if '日期' in df_act.columns: df_act['日期'] = pd.to_datetime(df_act['日期'], errors='coerce')
                cutoff_date = datetime.now() - timedelta(days=30)
                df_recent = df_act[df_act['日期'] >= cutoff_date].sort_values(by='日期', ascending=False).reset_index(drop=True)
                if not df_recent.empty:
                    for index, row in df_recent.iterrows():
                        icon, r_type = "🔹", str(row.get('類型',''))
                        if "入金" in r_type: icon = "💰"
                        elif "交易" in r_type: icon = "⚖️"
                        elif "股利" in r_type: icon = "💸"
                        content = str(row.get('內容','')).replace("(定期定額)", "🔴 **(定期定額)**").replace("(股息再投入)", "♻️ **(股息再投入)**")
                        d_str = row['日期'].strftime('%Y/%m/%d') if pd.notna(row['日期']) else ""
                        st.markdown(f"{icon} **{d_str}** | {content}")
                else: st.caption("近一個月無動態")
            except: st.caption("尚無動態")
        else: st.caption("尚無動態資料")
        st.divider()

        # --- D. 持股清單 ---
        st.subheader("📋 持股清單")
        display_df = df_stocks[["股票代號", "目前市值", "帳面損益", "總投入本金", "目前股價", "累積總股數"]].copy()
        display_df["顯示名稱"] = display_df["股票代號"].map(stock_map_dict).fillna("")
        display_df["股票代號"] = display_df.apply(lambda x: f"{x['股票代號']} ({x['顯示名稱']})" if x['顯示名稱'] else x['股票代號'], axis=1)
        display_df = display_df.drop(columns=["顯示名稱"])
        
        def style_row(row):
            color = '#ff2b2b' if row['帳面損益'] > 0 else '#09ab3b' if row['帳面損益'] < 0 else 'black'
            return [f'color: {color}; font-weight: bold' if col in ['目前市值', '帳面損益'] else '' for col in row.index]

        event = st.dataframe(
            display_df.style.format({"總投入本金": "{:,.0f}", "目前市值": "{:,.0f}", "帳面損益": "{:,.0f}", "平均成本": "{:.2f}", "目前股價": "{:.2f}", "累積總股數": "{:,.0f}"}).apply(style_row, axis=1).bar(subset=['帳面損益'], align='mid', color=['#90EE90', '#FFB6C1']),
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )

        if len(event.selection.rows) > 0:
            sel_idx = event.selection.rows[0]
            sel_name = display_df.iloc[sel_idx]["股票代號"]
            sel_code = sel_name.split(" ")[0]
            
            with st.container(border=True):
                st.markdown(f"### 📂 {sel_name}")
                tab_trans, tab_div = st.tabs(["⚖️ 交易明細", "💸 領息紀錄"])
                
                with tab_trans:
                    if df_trans is not None and not df_trans.empty:
                        df_trans.columns = df_trans.columns.str.strip()
                        if "股票代號" in df_trans.columns:
                            df_trans["股票代號"] = clean_stock_code(df_trans["股票代號"])
                            my_trans = df_trans[df_trans["股票代號"] == sel_code].copy()
                            if "投入金額" in my_trans.columns:
                                my_trans = my_trans[my_trans["投入金額"].astype(str).str.strip() != ""]
                                my_trans = my_trans[my_trans["投入金額"].apply(clean_number) > 0]
                            if not my_trans.empty:
                                for col in ["成交單價", "投入金額", "成交股數"]:
                                    if col in my_trans.columns: my_trans[col] = my_trans[col].apply(clean_number)
                                cols = ["日期", "交易類別", "成交單價", "投入金額", "成交股數", "股息再投入"]
                                final = [c for c in cols if c in my_trans.columns]
                                
                                def highlight(v): return 'color: #ff2b2b; font-weight: bold' if v=='買入' else 'color: #09ab3b; font-weight: bold' if v=='賣出' else ''
                                st.dataframe(my_trans[final].style.map(highlight, subset=['交易類別']).format({"成交單價": "{:.2f}", "投入金額": "{:,.0f}", "成交股數": "{:,.0f}"}), use_container_width=True, hide_index=True)
                            else: st.warning("尚無交易紀錄。")
                
                with tab_div:
                    if df_div is not None and not df_div.empty:
                        df_div.columns = df_div.columns.str.strip()
                        if "股票代號" in df_div.columns:
                            df_div["股票代號"] = clean_stock_code(df_div["股票代號"])
                            my_div = df_div[df_div["股票代號"] == sel_code].copy()
                            if not my_div.empty:
                                for col in ["配息單價", "實領金額"]:
                                    if col in my_div.columns: my_div[col] = my_div[col].apply(clean_number)
                                total_div = my_div["實領金額"].sum()
                                st.metric("💰 累積領息總額", f"${total_div:,.0f}")

                                cols = ["發放日期", "季", "配息單價", "實領金額", "狀態"]
                                final = [c for c in cols if c in my_div.columns]
                                if "發放日期" in my_div.columns: my_div = my_div.sort_values(by="發放日期", ascending=False)
                                
                                def style_status(v):
                                    if v == '未使用': return 'background-color: #ffeebb; color: black;'
                                    if v == '再投入股票': return 'background-color: #ccffcc; color: black;'
                                    if v == '領出': return 'background-color: #ffcccc; color: black;'
                                    return ''

                                if "狀態" in final:
                                    st.dataframe(my_div[final].style.map(style_status, subset=['狀態']).format({"配息單價": "{:.2f}", "實領金額": "{:,.0f}"}), use_container_width=True, hide_index=True)
                                else:
                                    st.dataframe(my_div[final].style.format({"配息單價": "{:.2f}", "實領金額": "{:,.0f}"}), use_container_width=True, hide_index=True)
                            else: st.info("尚無領息紀錄")
                    else: st.info("尚無股利資料表")

    except Exception as e: st.error(f"程式錯誤：{e}")
else: st.error("讀取失敗，請檢查 Secrets 設定。")

# ==========================================
# 4. 管理員專區
# ==========================================
st.markdown("---") 
st.markdown("### ⚙️ 後台管理")
if 'admin_expanded' not in st.session_state: st.session_state['admin_expanded'] = False

with st.expander("🔧 點擊開啟管理面板", expanded=st.session_state['admin_expanded']):
    if not st.session_state.get('admin_logged_in', False):
        st.warning("⚠️ 此區域僅限管理員操作")
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password", key="admin_pass_input")
        if admin_input:
            try:
                if admin_input == st.secrets["admin_password"]:
                    st.session_state['admin_logged_in'] = True; st.session_state['admin_expanded'] = True; st.success("身分驗證成功！"); st.rerun()
                else: st.error("密碼錯誤 🚔")
            except: st.error("Secrets 未設定 admin_password")
    else:
        st.success("🔓 管理員模式已啟用")
        if st.button("🔒 登出"): st.session_state['admin_logged_in'] = False; st.session_state['admin_expanded'] = False; st.rerun()

        t1, t2, t3, t4, t5, t6 = st.tabs(["📢 公告", "🏷️ 股票", "💸 資金", "📝 交易", "💰 新增股利", "🏦 管理股利"])

        with t1:
            with st.form("msg_form"):
                c1, c2 = st.columns([1, 3])
                nt = c1.selectbox("類型", ["🎉 慶祝", "🔔 提醒", "📢 一般", "🚨 緊急"])
                nc = c2.text_input("內容")
                if st.form_submit_button("送出"):
                    requests.post(GAS_URL, json={"action": "msg", "date": datetime.now().strftime("%Y-%m-%d"), "type": nt, "content": nc})
                    st.toast("✅ 公告已發布！"); st.cache_data.clear()

        with t2:
            with st.form("stock_form"):
                c1, c2 = st.columns(2)
                mc = c1.text_input("代號", placeholder="0050").strip()
                mn = c2.text_input("名稱", placeholder="元大台灣50").strip()
                if st.form_submit_button("儲存"):
                    requests.post(GAS_URL, json={"action": "update_stock", "stock": mc, "name": mn})
                    st.toast(f"✅ 已更新：{mc} ➝ {mn}"); st.cache_data.clear(); st.rerun()
            if stock_map_dict:
                df_map = pd.DataFrame(list(stock_map_dict.items()), columns=['代號', '名稱']).sort_values('代號')
                st.dataframe(df_map, use_container_width=True, hide_index=True)

        with t3:
            with st.form("fund_form"):
                c1, c2, c3 = st.columns(3)
                fd = c1.date_input("日期", datetime.now())
                fn = c2.selectbox("姓名", ["建蒼", "奕州"])
                fa = c3.number_input("金額", step=1000, value=10000)
                fnt = st.text_input("備註")
                if st.form_submit_button("入帳"):
                    requests.post(GAS_URL, json={"action": "fund", "date": fd.strftime("%Y-%m-%d"), "name": fn, "amount": fa, "note": fnt})
                    st.toast("✅ 入帳成功"); st.cache_data.clear()

        with t4:
            with st.form("trade_form"):
                c1, c2 = st.columns(2)
                td = c1.date_input("日期", datetime.now())
                opts = [f"{k} ({v})" for k, v in stock_map_dict.items()] if stock_map_dict else ["0050", "006208"]
                sel = c1.selectbox("代號", opts + ["🖊️ 自行輸入"])
                ts = c1.text_input("輸入代號").strip() if sel == "🖊️ 自行輸入" else sel.split(" ")[0]
                tt = c1.selectbox("類別", ["買入", "賣出"])
                ir = c1.checkbox("定期定額", True)
                id = c1.checkbox("股息再投入", False)
                tp = c2.number_input("單價", step=0.1, format="%.2f")
                tsh = c2.number_input("股數", step=100)
                tf = c2.number_input("手續費", value=20)
                if st.form_submit_button("記錄"):
                    tot = int(tp * tsh)
                    requests.post(GAS_URL, json={"action": "trade", "date": td.strftime("%Y-%m-%d"), "stock": ts, "type": tt, "price": tp, "total": tot, "shares": tsh, "fee": tf, "regular": "Y" if ir else "", "dividend": "Y" if id else ""})
                    st.toast("✅ 交易已記錄"); st.cache_data.clear()

        with t5:
            st.caption("輸入收到股利通知單的資訊，預設狀態為「未使用」")
            with st.form("div_form"):
                c1, c2 = st.columns(2)
                dd = c1.date_input("發放日", datetime.now())
                opts = [f"{k} ({v})" for k, v in stock_map_dict.items()] if stock_map_dict else ["0050"]
                sel = c1.selectbox("代號", opts + ["🖊️ 自行輸入"], key="div_s")
                ds = c1.text_input("輸入代號", key="div_i").strip() if sel == "🖊️ 自行輸入" else sel.split(" ")[0]
                dsea = c1.selectbox("季度", ["Q1", "Q2", "Q3", "Q4", "上半年", "下半年", "年度"])
                dh = c2.number_input("除息股數", step=100)
                dp = c2.number_input("配息單價", step=0.01)
                dt = c2.number_input("實領金額", step=100)
                if st.form_submit_button("記錄股利"):
                    requests.post(GAS_URL, json={"action": "dividend", "date": dd.strftime("%Y-%m-%d"), "stock": ds, "season": dsea, "held_shares": dh, "div_price": dp, "total": dt})
                    st.toast("✅ 股利已記錄"); st.cache_data.clear()

        with t6: # ★ 強化版 管理股利 (加入實領金額一併傳送給後端比對)
            st.info("這裡列出所有「未使用」的股利，你可以選擇將其領出或再投入。")
            if df_div is not None and not df_div.empty:
                df_div_local = df_div.copy()
                df_div_local.columns = df_div_local.columns.str.strip()
                if "狀態" in df_div_local.columns:
                    df_div_local["狀態"] = df_div_local["狀態"].fillna("未使用")
                    df_unused = df_div_local[df_div_local["狀態"] == "未使用"].copy()
                    
                    if not df_unused.empty:
                        df_unused["股票代號"] = clean_stock_code(df_unused["股票代號"])
                        df_unused["標籤"] = df_unused.apply(lambda x: f"{x['發放日期']} | {x['股票代號']} | ${clean_number(x['實領金額']):,.0f} ({x['季']})", axis=1)
                        
                        target_div = st.selectbox("選擇一筆股利", df_unused["標籤"])
                        selected_row = df_unused[df_unused["標籤"] == target_div].iloc[0]
                        
                        st.write(f"目前選定：**{selected_row['股票代號']}** 金額 **${clean_number(selected_row['實領金額']):,.0f}**")
                        new_status = st.radio("變更狀態為：", ["領出", "再投入股票"], horizontal=True)
                        
                        if st.button("確認變更狀態"):
                            try:
                                res = requests.post(GAS_URL, json={
                                    "action": "update_div_status",
                                    "date": str(selected_row['發放日期']).strip(),
                                    "stock": str(selected_row['股票代號']).strip(),
                                    "season": str(selected_row['季']).strip(),
                                    "amount": float(clean_number(selected_row['實領金額'])), # ★ 把金額送過去作保險比對
                                    "new_status": new_status
                                })
                                if res.status_code == 200:
                                    res_data = res.json()
                                    if res_data.get("status") == "success":
                                        st.toast(f"✅ 更新成功！已變更為：{new_status}")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Excel 更新失敗：{res_data.get('message')}")
                                else:
                                    st.error("❌ 連線錯誤")
                            except Exception as e:
                                st.error(f"連線錯誤：{e}")
                    else:
                        st.success("🎉 目前沒有閒置的股利！")
                else:
                    st.warning("⚠️ 股利記錄表中缺少「狀態」欄位，請確認 Excel 的 G 欄標題有寫上「狀態」！")
            else:
                st.warning("無法讀取股利表")
