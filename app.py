import io
from datetime import date
import google.genai as genai
import pandas as pd
import streamlit as st
from supabase import Client, create_client

# ==========================================
# 1. 頁面基本設定
# ==========================================
st.set_page_config(
    page_title="各門市營業額記錄與 AI 智能查詢系統", page_icon="📊", layout="wide"
)

st.title("📊 各門市每日業績回報與 AI 查詢系統")


# ==========================================
# 2. 初始化 Supabase 與 Gemini API 連線
# ==========================================
@st.cache_resource
def init_supabase():
  url = st.secrets["SUPABASE_URL"]
  key = st.secrets["SUPABASE_KEY"]
  return create_client(url, key)


@st.cache_resource
def init_gemini():
  api_key = st.secrets["GEMINI_API_KEY"]
  return genai.Client(api_key=api_key)


try:
  supabase = init_supabase()
  ai_client = init_gemini()
except Exception as e:
  st.error(f"連線設定錯誤，請檢查 st.secrets 是否正確設定：{e}")
  st.stop()

# ==========================================
# 3. 側邊欄切換功能分頁
# ==========================================
menu = st.sidebar.selectbox(
    "選擇功能模組",
    [
        "📝 前台：店員打單",
        "🛠️ 後台：歷史資料編輯",
        "📊 業績圖表與 Excel 報表",
        "🤖 AI 智能數據對話框",
        "👥 後台：員工帳號管理",
    ],
)

# ------------------------------------------
# 模組一：前台店員打單
# ------------------------------------------
if menu == "📝 前台：店員打單":
  st.header("📝 每日門市業績回報")
  st.markdown("請輸入今日門市與線上訂單業績，並輸入您的姓名與驗證密碼。")

  with st.form("sales_entry_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
      store_name = st.selectbox(
          "選擇門市", ["虎尾店", "台北店", "台中店", "高雄店"]
      )
      record_date = st.date_input("營業日期", value=date.today())
      offline_sales = st.number_input(
          "門市實體業績 (元)", min_value=0, step=100, value=0
      )
    with col2:
      online_sales = st.number_input(
          "線上訂單業績 (元)", min_value=0, step=100, value=0
      )
      recorder_name = st.text_input("記錄人員名稱", placeholder="例如：小明")
      pin_code = st.text_input(
          "驗證密碼 / PIN 碼", type="password", placeholder="請輸入您的員工密碼"
      )

    submitted = st.form_submit_button("🚀 確認送出業績", type="primary")

    if submitted:
      if not recorder_name or not pin_code:
        st.warning("請完整填寫人員名稱與密碼！")
      else:
        emp_check = (
            supabase.table("employees")
            .select("*")
            .eq("name", recorder_name)
            .eq("pin", pin_code)
            .execute()
        )

        if len(emp_check.data) == 0:
          st.error("❌ 人員名稱或密碼錯誤，無法送出！")
        else:
          data_to_insert = {
              "date": str(record_date),
              "store_name": store_name,
              "offline_sales": offline_sales,
              "online_sales": online_sales,
              "total_sales": offline_sales + online_sales,
              "recorder_name": recorder_name,
          }
          res = (
              supabase.table("sales_records").insert(data_to_insert).execute()
          )
          if res.data:
            st.success(
                f"✅ 【{store_name}】{record_date}"
                f" 業績已成功送出！總業績：${offline_sales + online_sales:,}"
            )

# ------------------------------------------
# 模組二：後台歷史資料檢視與修改 (Data Editor)
# ------------------------------------------
elif menu == "🛠️ 後台：歷史資料編輯":
  st.header("🛠️ 歷史業績檢視與錯誤修正")
  st.markdown("您可以直接在表格中點選修改數據，修改完成後點擊下方的「儲存變更」按鈕。")

  response = (
      supabase.table("sales_records")
      .select("*")
      .order("date", desc=True)
      .limit(100)
      .execute()
  )
  df = pd.DataFrame(response.data)

  if not df.empty:
    edited_df = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, key="sales_data_editor"
    )

    if st.button("💾 儲存表格修改結果", type="primary"):
      try:
        for index, row in edited_df.iterrows():
          row_dict = row.to_dict()
          row_dict["total_sales"] = (
              row_dict["offline_sales"] + row_dict["online_sales"]
          )
          supabase.table("sales_records").update(row_dict).eq(
              "id", row_dict["id"]
          ).execute()
        st.success("🎉 所有修改已成功同步至 Supabase 資料庫！")
        st.rerun()
      except Exception as e:
        st.error(f"更新失敗：{e}")
  else:
    st.info("目前尚無業績資料。")

# ------------------------------------------
# 模組三：業績圖表與 Excel 報表匯出
# ------------------------------------------
elif menu == "📊 業績圖表與 Excel 報表":
  st.header("📈 各門市業績趨勢與報表匯出")

  response = supabase.table("sales_records").select("*").execute()
  df = pd.DataFrame(response.data)

  if not df.empty:
    df["date_dt"] = pd.to_datetime(df["date"])
    df["month"] = df["date_dt"].dt.to_period("M").astype(str)

    st.subheader("📊 每月總業績曲線圖")
    monthly_sales = (
        df.groupby(["month", "store_name"])["total_sales"].sum().unstack()
    )
    st.line_chart(monthly_sales)

    st.subheader("📥 下載 Excel 完整報表")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
      df.drop(columns=["date_dt"], errors="ignore").to_excel(
          writer, index=False, sheet_name="業績明細總表"
      )
      if not monthly_sales.empty:
        monthly_sales.to_excel(writer, sheet_name="每月門市統計")
    excel_data = output.getvalue()

    st.download_button(
        label="🟢 點此下載完整業績 Excel 報表 (.xlsx)",
        data=excel_data,
        file_name="門市營業額報表.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
  else:
    st.info("目前尚無足夠資料產生圖表。")

# ------------------------------------------
# 模組四：AI 智能數據對話框 (純讀取 Text-to-SQL)
# ------------------------------------------
elif menu == "🤖 AI 智能數據對話框":
  st.header("🤖 AI 數據小幫手（唯讀查詢）")
  st.info("💡 範例問法：「5月1號到5月9號的營業額差多少？」、「台北店這個月跟上個月業績差多少？」")

  if "messages" not in st.session_state:
    st.session_state.messages = []

  for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
      st.markdown(msg["content"])

  prompt = st.chat_input("請輸入你想查詢的業績問題...")

  if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
      st.markdown(prompt)

    with st.chat_message("assistant"):
      with st.status("AI 正在解析您的問題並查詢資料庫...", expanded=False):
        schema_description = """
                Table name: sales_records
                Columns:
                - id (uuid, primary key)
                - date (date, e.g. '2026-05-01')
                - store_name (text, e.g. '虎尾店', '台北店', '台中店', '高雄店')
                - offline_sales (integer, 門市實體業績)
                - online_sales (integer, 線上訂單業績)
                - total_sales (integer, 總業績 = offline_sales + online_sales)
                - recorder_name (text, 記錄人)
                """

        sql_prompt = f"""
                你是一個 PostgreSQL SQL 專家。請根據以下表格結構，將使用者的自然語言問題轉換成一條安全、唯讀的 PostgreSQL SELECT SQL 語句。
                注意：
                1. 只能回傳純 SQL 語句本身，前後不要有 markdown 程式碼區塊標記（如 ```sql ... ```），也不要有多餘解釋文字。
                2. 僅允許 SELECT 查詢，絕對不能有 INSERT, UPDATE, DELETE, DROP。
                
                {schema_description}
                使用者問題：{prompt}
                """

        response_sql = ai_client.models.generate_content(
            model="gemini-2.5-flash", contents=sql_prompt
        )
        generated_sql = (
            response_sql.text.strip()
            .replace("```sql", "")
            .replace("```", "")
            .strip()
        )
        st.code(generated_sql, language="sql")

      try:
        query_result = supabase.rpc(
            "execute_readonly_sql", {"sql_query": generated_sql}
        ).execute()
        query_data = query_result.data
      except Exception as e:
        query_data = f"查詢執行錯誤: {e}"

      answer_prompt = f"""
            使用者問的問題是：「{prompt}」
            從資料庫查詢到的原始數據是：{query_data}
            請用親切、清晰的台灣商業中文語氣，幫使用者解答這個問題。如果數據有差異，請把計算過程與結論精準列出。
            """

      final_response = ai_client.models.generate_content(
          model="gemini-2.5-flash", contents=answer_prompt
      )
      answer_text = final_response.text

      st.markdown(answer_text)
      st.session_state.messages.append(
          {"role": "assistant", "content": answer_text}
      )

# ------------------------------------------
# 模組五：後台員工帳號管理
# ------------------------------------------
elif menu == "👥 後台：員工帳號管理":
  st.header("👥 員工帳號與密碼管理")

  col_add, col_list = st.columns()

  with col_add:
    st.subheader("新增員工帳號")
    with st.form("add_emp", clear_on_submit=True):
      new_name = st.text_input("員工姓名")
      new_pin = st.text_input("設定 PIN 碼 (密碼)", type="password")
      new_store = st.selectbox(
          "所屬門市", ["虎尾店", "台北店", "台中店", "高雄店"]
      )
      btn_add = st.form_submit_button("➕ 新增員工")

      if btn_add:
        if new_name and new_pin:
          supabase.table("employees").insert({
              "name": new_name,
              "pin": new_pin,
              "store_name": new_store,
          }).execute()
          st.success(f"已新增員工：{new_name}")
          st.rerun()

  with col_list:
    st.subheader("現有員工清單")
    emp_res = supabase.table("employees").select("*").execute()
    emp_df = pd.DataFrame(emp_res.data)
    if not emp_df.empty:
      st.dataframe(
          emp_df[["name", "store_name", "created_at"]],
          use_container_width=True,
      )
