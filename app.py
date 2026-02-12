import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# ==========================================
# 0. 登入系統 (門神)
# ==========================================
st.set_page_config(page_title="雞與虎的投資看板", page_icon="📈", layout="wide")

def check_password():
    """回傳 True 代表密碼正確，False 代表尚未登入或錯誤"""
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
    """讀取 Google Sheet 的股票清單，轉成字典 {'0050': '元大台灣50'}"""
    try:
        df = pd.read_csv(STOCK_MAP_URL, dtype=str)
        if '股票代號' in df.columns and '股票名稱' in df.columns:
            df['股票代號'] = df['股票代號'].str.strip()
            df['股票名稱'] = df['股票名稱'].str.strip()
            return dict(zip(df['股票代號'], df['股票名稱']))
        return {}
    except:
        return {}

# 載入股票對照表 (全域變數)
stock_map_dict = load_stock_map()

def clean_stock_code(series):
    return (series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(4))

def clean_number(x):
    if pd.isna(x) or str(x).strip() in ["#N/A", "-", "nan", ""]: return 0
    return pd.to_numeric(str(x).replace(',', '').replace('$', ''), errors='coerce')

# ==========================================
# 3. 網頁主程式
# ==========================================
st.title("💰 存股儀表板")

# --- A. 智慧公告欄 (倒序顯示最新) ---
df_msg = load_data(MSG_URL)

if df_msg is not None and not df_msg.empty:
    try:
        df_msg.columns = df_msg.columns.str.strip()
        if '日期' in df_msg.columns:
            df_msg['日期'] = pd.to_datetime(df_msg['日期'], errors='coerce')

        # 倒序：最新的在最上面
        df_reversed = df_msg.iloc[::-1].reset_index(drop=True)
        
        if not df_reversed.empty:
            def get_msg_style(msg_type):
                if '慶祝' in str(msg_type): return "🎉", st.success
                elif '提醒' in str(msg_type) or '重要' in str(msg_type): return "🔔", st.warning
                elif '緊急' in str(msg_type): return "🚨", st.error
                else: return "📢", st.info

            latest = df_reversed.iloc[0]
            l_type = latest['類型'] if '類型' in df_reversed.columns else '一般'
            l_icon, l_alert = get_msg_style(l_type)
            l_date_str = latest['日期'].strftime('%Y-%m-%d') if pd.notna(latest['日期']) else ""
            
            with st.container():
                l_alert(f"**{l_date_str}**：{latest['內容']}", icon=l_icon)
            
            if len(df_reversed) > 1:
                with st.expander("📜 查看近期公告"):
                    history_msgs = df_reversed.iloc[1:6]
                    for index, row in history_msgs.iterrows():
                        h_type = row['類型'] if '類型' in df_reversed.columns else '一般'
                        h_icon, h_alert = get_msg_style(h_type)
                        h_date_str = row['日期'].strftime('%Y-%m-%d') if pd.notna(row['日期']) else ""
                        h_alert(f"**{h_date_str}**：{row['內容']}", icon=h_icon)
    except Exception as e:
        pass 

# --- B. 儀表板核心數據 ---
df_dash = load_data(DASHBOARD_URL)
df_trans = load_data(TRANS_URL)

if df_dash is not None and not df_dash.empty:
    try:
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

        # ==========================================
        # C. ⚡ 最新動態流水帳 (近 30 天)
        # ==========================================
        st.subheader("⚡ 最新動態 (近 30 天)")

        df_act = load_data(ACT_URL)

        if df_act is not None and not df_act.empty:
            try:
                df_act.columns = df_act.columns.str.strip()
                if '日期' in df_act.columns and '內容' in df_act.columns:
                    df_act['日期'] = pd.to_datetime(df_act['日期'], errors='coerce')
                    
                    cutoff_date = datetime.now() - timedelta(days=30)
                    df_recent = df_act[df_act['日期'] >= cutoff_date]
                    df_recent = df_recent.sort_values(by='日期', ascending=False).reset_index(drop=True)
                    
                    if not df_recent.empty:
                        for index, row in df_recent.iterrows():
                            icon = "🔹" 
                            row_type = str(row['類型']) if '類型' in df_act.columns else ""
                            content = str(row['內容'])
                            
                            if "入金" in row_type:
                                icon = "💰"
                            elif "交易" in row_type:
                                icon = "⚖️"
                            
                            if "(定期定額)" in content:
                                content = content.replace("(定期定額)", "🔴 **(定期定額)**")
                            
                            date_str = row['日期'].strftime('%Y/%m/%d') if pd.notna(row['日期']) else ""
                            st.markdown(f"{icon} **{date_str}** | {content}")
                    else:
                        st.caption("近一個月無動態")
                        
            except Exception as e:
                st.caption("尚無動態")
        else:
            st.caption("尚無動態資料")
            
        st.divider()

        # ==========================================
        # D. 持股清單 (整合股票名稱翻譯)
        # ==========================================
        st.subheader("📋 持股清單")
        
        display_df = df_stocks[["股票代號", "目前市值", "帳面損益", "總投入本金", "目前股價", "累積總股數"]].copy()

        # 1. 產生名稱對照
        display_df["顯示名稱"] = display_df["股票代號"].map(stock_map_dict).fillna("")
        
        # 2. 合併代號與名稱
        display_df["股票代號"] = display_df.apply(
            lambda x: f"{x['股票代號']} ({x['顯示名稱']})" if x['顯示名稱'] else x['股票代號'], 
            axis=1
        )

        # 3. ★ 刪除 "顯示名稱" 輔助欄位，避免在表格中重複顯示 ★
        display_df = display_df.drop(columns=["顯示名稱"])

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

        # --- 詳細交易紀錄 (整合翻譯還原) ---
        if len(event.selection.rows) > 0:
            selected_index = event.selection.rows[0]
            selected_display_name = display_df.iloc[selected_index]["股票代號"]
            selected_stock_code = selected_display_name.split(" ")[0]
            
            with st.container(border=True):
                st.info(f"👇 **{selected_display_name}** 詳細交易紀錄")
                
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
        # ★ 這裡原本的 st.caption 已經移除 ★

        if st.button('🔄 立即更新'):
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"程式錯誤：{e}")
else:
    st.error("讀取失敗，請檢查 Secrets 設定。")


# ==========================================
# 4. 管理員專區
# ==========================================
st.markdown("---") 
st.markdown("### ⚙️ 後台管理")

if 'admin_expanded' not in st.session_state:
    st.session_state['admin_expanded'] = False

with st.expander("🔧 點擊開啟管理面板", expanded=st.session_state['admin_expanded']):
    
    if not st.session_state.get('admin_logged_in', False):
        st.warning("⚠️ 此區域僅限管理員操作")
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password", key="admin_pass_input")
        
        if admin_input:
            try:
                if admin_input == st.secrets["admin_password"]:
                    st.session_state['admin_logged_in'] = True
                    st.session_state['admin_expanded'] = True 
                    st.success("身分驗證成功！")
                    st.rerun() 
                else:
                    st.error("密碼錯誤，請勿嘗試入侵 🚔")
            except KeyError:
                st.error("Secrets 未設定 admin_password")
    else:
        st.success("🔓 管理員模式已啟用")
        if st.button("🔒 登出管理員"):
            st.session_state['admin_logged_in'] = False
            st.session_state['admin_expanded'] = False
            st.rerun()

        tab1, tab2, tab3, tab4 = st.tabs(["📢 發布公告", "💸 資金入帳", "📝 新增交易", "🏷️ 管理股票"])

        # === Tab 1: 發公告 ===
        with tab1:
            with st.form("msg_form"):
                col1, col2 = st.columns([1, 3])
                with col1:
                    new_type = st.selectbox("類型", ["🎉 慶祝", "🔔 提醒", "📢 一般", "🚨 緊急"])
                with col2:
                    new_content = st.text_input("公告內容", placeholder="例如：資產突破 50 萬啦！")
                
                if st.form_submit_button("送出公告"):
                    if new_content:
                        try:
                            post_data = {
                                "action": "msg",
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "type": new_type,
                                "content": new_content
                            }
                            requests.post(GAS_URL, json=post_data)
                            st.toast("✅ 公告已發布！", icon='🎉')
                            st.session_state['admin_expanded'] = True
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"錯誤：{e}")

        # === Tab 2: 資金入帳 ===
        with tab2:
            with st.form("fund_form"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    f_date = st.date_input("入帳日期", datetime.now()) 
                with col2:
                    f_name = st.selectbox("誰轉錢進來？", ["建蒼", "奕州"]) 
                with col3:
                    f_amount = st.number_input("金額", min_value=0, step=1000, value=10000)
                
                f_note = st.text_input("備註", placeholder="例如：加碼金")

                if st.form_submit_button("💰 確認入帳"):
                    try:
                        post_data = {
                            "action": "fund", 
                            "date": f_date.strftime("%Y-%m-%d"), 
                            "name": f_name,
                            "amount": f_amount,
                            "note": f_note
                        }
                        response = requests.post(GAS_URL, json=post_data)
                        if response.status_code == 200:
                            result = response.json()
                            if result.get("status") == "success":
                                st.toast(f"✅ 成功！已將款項填入 {f_date.month} 月的格子中。", icon='💸')
                                st.session_state['admin_expanded'] = True
                            else:
                                st.error(f"❌ 寫入失敗：{result.get('message')}")
                        else:
                            st.error("❌ 連線錯誤")
                    except Exception as e:
                        st.error(f"錯誤：{e}")

        # === Tab 3: 新增交易 (使用動態股票清單) ===
        with tab3:
            with st.form("trade_form"):
                col1, col2 = st.columns(2)
                with col1:
                    t_date = st.date_input("交易日期", datetime.now())
                    
                    if stock_map_dict:
                        fav_options = [f"{k} ({v})" for k, v in stock_map_dict.items()]
                        fav_options.sort()
                    else:
                        fav_options = ["0050", "006208", "00919", "2330"] 

                    selected_option = st.selectbox("股票代號", fav_options + ["🖊️ 自行輸入"])
                    
                    if selected_option == "🖊️ 自行輸入":
                        t_stock_input = st.text_input("請輸入代號", placeholder="例如：2412").strip()
                        t_stock = t_stock_input 
                    else:
                        t_stock = selected_option.split(" ")[0]
                    
                    t_type = st.selectbox("交易類別", ["買入", "賣出"])
                    is_regular = st.checkbox("是定期定額嗎？", value=True)
                    
                with col2:
                    t_price = st.number_input("成交單價", min_value=0.0, step=0.1, format="%.2f")
                    t_shares = st.number_input("成交股數", min_value=0, step=100)
                    t_fee = st.number_input("手續費 (僅紀錄)", min_value=0, value=20)
                
                if st.form_submit_button("📝 記錄交易"):
                    try:
                        t_total_final = int(t_price * t_shares)
                        
                        post_data = {
                            "action": "trade",
                            "date": t_date.strftime("%Y-%m-%d"),
                            "stock": t_stock,
                            "type": t_type,
                            "price": t_price,
                            "total": t_total_final, 
                            "shares": t_shares,
                            "fee": t_fee,          
                            "regular": "Y" if is_regular else ""
                        }
                        
                        requests.post(GAS_URL, json=post_data)
                        
                        if is_regular and t_type == "買入":
                            msg = f"(定期定額) 買入 {t_stock} {t_shares}股 @ {t_price} ，總共 {t_total_final} 元"
                            st.toast(f"✅ {msg}", icon='📝')
                        else:
                            st.toast(f"✅ 已記錄：{t_type} {t_stock} {t_shares} 股 (總額 ${t_total_final:,})", icon='📝')
                        
                        st.session_state['admin_expanded'] = True
                        st.cache_data.clear()

                    except Exception as e:
                        st.error(f"錯誤：{e}")

        # === Tab 4: 管理股票 ===
        with tab4:
            st.info("💡 這裡設定的名稱，會自動套用到整個網站 (持股清單、交易明細)。")
            
            with st.form("stock_map_form"):
                col1, col2 = st.columns(2)
                with col1:
                    m_code = st.text_input("股票代號", placeholder="例如：0050").strip()
                with col2:
                    m_name = st.text_input("股票名稱", placeholder="例如：元大台灣50").strip()
                
                if st.form_submit_button("💾 儲存 / 更新"):
                    if m_code and m_name:
                        try:
                            post_data = {
                                "action": "update_stock", 
                                "stock": m_code,
                                "name": m_name
                            }
                            requests.post(GAS_URL, json=post_data)
                            
                            st.toast(f"✅ 已更新：{m_code} ➝ {m_name}", icon='🏷️')
                            st.cache_data.clear()
                            st.session_state['admin_expanded'] = True
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"錯誤：{e}")
                    else:
                        st.warning("⚠️ 代號和名稱都要填寫才能儲存喔！")

            st.divider()
            st.subheader("📋 目前已設定的股票")
            
            if stock_map_dict:
                df_map = pd.DataFrame(list(stock_map_dict.items()), columns=['股票代號', '股票名稱'])
                df_map = df_map.sort_values(by='股票代號')
                
                st.dataframe(
                    df_map, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "股票代號": st.column_config.TextColumn("代號", width="small"),
                        "股票名稱": st.column_config.TextColumn("顯示名稱", width="medium"),
                    }
                )
            else:
                st.info("尚無資料，請在上方新增股票。")
            
            if st.button("🔄 重新讀取清單"):
                st.cache_data.clear()
                st.rerun()
