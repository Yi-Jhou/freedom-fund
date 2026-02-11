import streamlit as st
import pandas as pd
import requests 
from datetime import datetime

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
                    st.error("密碼錯誤 ❌")
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
    GAS_URL = st.secrets["gas_url"] 
except (FileNotFoundError, KeyError):
    st.error("🔒 錯誤：找不到 Secrets 設定！請檢查 Streamlit Cloud 後台。")
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
                with st.expander("📜 查看近期公告 (近 5 則)"):
                    history_msgs = df_reversed.iloc[1:6]
                    for index, row in history_msgs.iterrows():
                        h_type = row['類型'] if '類型' in df_reversed.columns else '一般'
                        h_icon, h_alert = get_msg_style(h_type)
                        h_date_str = row['日期'].strftime('%Y-%m-%d') if pd.notna(row['日期']) else ""
                        h_alert(f"**{h_date_str}**：{row['內容']}", icon=h_icon)
    except Exception as e:
        pass 

# --- B. 儀表板與持股清單 ---
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
            st.caption("👆 (手機請左滑) 點擊框框可查看明細")

        if st.button('🔄 立即更新'):
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"程式錯誤：{e}")
else:
    st.error("讀取失敗，請檢查 Secrets 設定。")


# ==========================================
# 4. 管理員專區 (雙重驗證 + 自動通知版)
# ==========================================
st.markdown("---") 
st.markdown("### ⚙️ 後台管理")

# 判斷面板是否要保持開啟 (預設關閉)
if 'admin_expanded' not in st.session_state:
    st.session_state['admin_expanded'] = False

with st.expander("🔧 點擊開啟管理面板", expanded=st.session_state['admin_expanded']):
    
    # --- 檢查是否已經登入管理員 ---
    if not st.session_state.get('admin_logged_in', False):
        st.warning("⚠️ 此區域僅限管理員操作")
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password", key="admin_pass_input")
        
        if admin_input:
            try:
                if admin_input == st.secrets["admin_password"]:
                    st.session_state['admin_logged_in'] = True
                    st.session_state['admin_expanded'] = True # 登入成功後自動展開
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

        tab1, tab2, tab3 = st.tabs(["📢 發布公告", "💸 資金入帳", "📝 新增交易"])

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
                            
                            # ★★★ 改用 Toast (彈出式通知) ★★★
                            st.toast("✅ 公告已發布！", icon='🎉')
                            
                            # 保持面板開啟
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
                                # ★★★ 改用 Toast (彈出式通知) ★★★
                                st.toast(f"✅ 成功！已將款項填入 {f_date.month} 月的格子中。", icon='💸')
                                
                                st.session_state['admin_expanded'] = True
                            else:
                                st.error(f"❌ 寫入失敗：{result.get('message')}")
                        else:
                            st.error("❌ 連線錯誤")
                    except Exception as e:
                        st.error(f"錯誤：{e}")

        # === Tab 3: 新增交易 (Toast 版) ===
        with tab3:
            with st.form("trade_form"):
                col1, col2 = st.columns(2)
                with col1:
                    t_date = st.date_input("交易日期", datetime.now())
                    t_stock = st.selectbox("股票代號", ["0050", "006208", "00919", "00878", "2330"])
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
                        
                        # ★★★ 改用 Toast (彈出式通知) ★★★
                        # 這裡會從右下角/右上角跳出來，約 4 秒後自動消失
                        st.toast(f"✅ 已記錄：{t_type} {t_stock} {t_shares} 股！\n(投入 ${t_total_final:,}，手續費另計)", icon='📝')
                        
                        # 保持面板開啟，不用重開
                        st.session_state['admin_expanded'] = True
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"錯誤：{e}")
