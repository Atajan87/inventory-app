import json  # <--- ДОБАВИТЬ ЭТУ СТРОКУ
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
import plotly.express as px # Для красивых графиков

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(page_title="Склад Pro: Отчеты и Статистика", layout="wide")

# ПАРОЛЬ ДЛЯ СБРОСА БАЗЫ
ADMIN_PASSWORD = "admin123" 

# Имя вашей Google Таблицы
SPREADSHEET_NAME = "Store_03_Database"

# --- ПОДКЛЮЧЕНИЕ К GOOGLE SHEETS ---
# --- НОВАЯ БРОНЕБОЙНАЯ ФУНКЦИЯ ПОДКЛЮЧЕНИЯ ---
@st.cache_resource
def get_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. Читаем секрет как строку JSON
    if "service_account_json" in st.secrets:
        try:
            # Превращаем текст обратно в словарь
            creds_dict = json.loads(st.secrets["service_account_json"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except json.JSONDecodeError as e:
            st.error(f"Ошибка в формате JSON в Secrets: {e}")
            st.stop()
            
    # 2. Локальный файл (если запускаем с компа)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.load(open("credentials.json")), scope)
        
    client = gspread.authorize(creds)
    return client

def load_data():
    client = get_connection()
    try:
        sh = client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        st.error(f"❌ Таблица '{SPREADSHEET_NAME}' не найдена!")
        st.stop()

    def read_sheet(worksheet_name, columns):
        try:
            ws = sh.worksheet(worksheet_name)
            data = ws.get_all_records()
            if not data:
                return pd.DataFrame(columns=columns)
            return pd.DataFrame(data)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=worksheet_name, rows=1000, cols=10)
            ws.append_row(columns)
            return pd.DataFrame(columns=columns)

    df_store = read_sheet("Store", ['Unic_Mat_№', 'Description', 'Place', 'Unit', 'Reminder', 'Price', 'Group', 'Remarks'])
    df_in = read_sheet("In", ['Unic_Mat_№', 'Description', 'QTY', 'Date', 'Delivery_man', 'Remarks'])
    df_out = read_sheet("Out", ['Unic_Mat_№', 'Description', 'QTY', 'Date', 'Applicant', 'Remarks'])

    # Преобразование типов данных
    df_store['Reminder'] = pd.to_numeric(df_store['Reminder'], errors='coerce').fillna(0)
    df_store['Price'] = pd.to_numeric(df_store['Price'], errors='coerce').fillna(0)
    
    # Преобразование дат
    df_in['Date'] = pd.to_datetime(df_in['Date'], errors='coerce').dt.date
    df_out['Date'] = pd.to_datetime(df_out['Date'], errors='coerce').dt.date

    return df_store, df_in, df_out

def save_sheet(df, worksheet_name):
    client = get_connection()
    sh = client.open(SPREADSHEET_NAME)
    ws = sh.worksheet(worksheet_name)
    ws.clear()
    # Подготовка данных для записи (превращаем даты в строки обратно)
    df_export = df.copy()
    if 'Date' in df_export.columns:
        df_export['Date'] = df_export['Date'].astype(str)
        
    ws.update([df_export.columns.values.tolist()] + df_export.values.tolist())

# --- ЗАГРУЗКА ДАННЫХ ---
if 'data_loaded' not in st.session_state:
    with st.spinner('Связь с сервером Google...'):
        st.session_state.df_store, st.session_state.df_in, st.session_state.df_out = load_data()
    st.session_state.data_loaded = True

# Кнопка принудительного обновления
with st.sidebar:
    if st.button("🔄 Обновить данные из Облака"):
        st.cache_resource.clear()
        st.session_state.data_loaded = False
        st.rerun()

# --- МЕНЮ ---
st.sidebar.title("🗂 Меню Склада")
page = st.sidebar.radio("Перейти:", 
    ["📊 Статистика (Dash)", 
     "📦 Склад (Остатки)", 
     "🔄 Приход / Расход", 
     "🖨️ Отчеты и Печать", 
     "⚙️ Настройки (Сброс)"]
)

# ==========================================
# 1. СТАТИСТИКА (DASHBOARD)
# ==========================================
if page == "📊 Статистика (Dash)":
    st.title("📊 Аналитика Склада")
    
    df_s = st.session_state.df_store
    df_o = st.session_state.df_out

    # Метрики
    total_items = len(df_s)
    total_money = (df_s['Reminder'] * df_s['Price']).sum()
    zero_stock = len(df_s[df_s['Reminder'] <= 0])

    col1, col2, col3 = st.columns(3)
    col1.metric("Всего позиций", total_items)
    col2.metric("Общая стоимость (¥)", f"{total_money:,.2f}")
    col3.metric("Нет в наличии", zero_stock, delta_color="inverse")

    st.divider()

    # Графики
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        st.subheader("📉 Динамика расходов (последние 30 записей)")
        if not df_o.empty:
            daily_out = df_o.groupby('Date')['QTY'].sum().reset_index()
            fig = px.bar(daily_out, x='Date', y='QTY', title="Количество выданных единиц по дням")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Нет данных о расходах")

    with col_g2:
        st.subheader("🏆 Топ-5 популярных товаров")
        if not df_o.empty:
            top_items = df_o.groupby('Description')['QTY'].sum().nlargest(5).reset_index()
            fig2 = px.pie(top_items, values='QTY', names='Description', title="Доля выдачи")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Нет данных")

# ==========================================
# 2. СКЛАД (ОСТАТКИ)
# ==========================================
elif page == "📦 Склад (Остатки)":
    st.title("📦 Текущие остатки")
    search = st.text_input("🔍 Быстрый поиск")
    
    df = st.session_state.df_store
    if search:
        mask = df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
        df_display = df[mask]
    else:
        df_display = df

    edited_df = st.data_editor(
        df_display,
        use_container_width=True,
        height=600,
        column_config={
            "Reminder": st.column_config.NumberColumn("Остаток", help="Не меняйте вручную, лучше используйте Приход/Расход"),
            "Price": st.column_config.NumberColumn("Цена ¥", format="%.2f"),
            "Unic_Mat_№": st.column_config.TextColumn("ID", disabled=True)
        }
    )

    if st.button("💾 Сохранить правки"):
        st.session_state.df_store.update(edited_df)
        with st.spinner('Сохраняю...'):
            save_sheet(st.session_state.df_store, "Store")
        st.success("Сохранено!")

# ==========================================
# 3. ОПЕРАЦИИ (ПРИХОД / РАСХОД) + НОВЫЙ ТОВАР
# ==========================================
elif page == "🔄 Приход / Расход":
    st.title("Операции с товаром")
    
    mode = st.radio("Выберите действие:", ["📤 ВЫДАТЬ (Расход)", "📥 ПРИНЯТЬ (Приход)", "✨ СОЗДАТЬ НОВЫЙ ТОВАР"], horizontal=True)
    options = st.session_state.df_store['Unic_Mat_№'].astype(str) + " | " + st.session_state.df_store['Description'].astype(str)

    # --- РАСХОД ---
    if mode == "📤 ВЫДАТЬ (Расход)":
        st.subheader("Списание со склада")
        sel = st.selectbox("Какой товар выдать?", options)
        if sel:
            id_ = sel.split(" | ")[0]
            curr_stock = st.session_state.df_store.loc[st.session_state.df_store['Unic_Mat_№'] == id_, 'Reminder'].values[0]
            
            if curr_stock <= 0:
                st.error(f"Товара нет на складе! (0 шт)")
            else:
                st.info(f"Доступно: {curr_stock} шт.")
                with st.form("out_f"):
                    q = st.number_input("Количество", 1.0, float(curr_stock))
                    who = st.text_input("Кому (Applicant)")
                    rem = st.text_input("Назначение")
                    if st.form_submit_button("Списать"):
                        st.session_state.df_store.loc[st.session_state.df_store['Unic_Mat_№'] == id_, 'Reminder'] -= q
                        new_row = {'Unic_Mat_№': id_, 'Description': sel.split(" | ")[1], 'QTY': q, 'Date': datetime.now().date(), 'Applicant': who, 'Remarks': rem}
                        st.session_state.df_out = pd.concat([st.session_state.df_out, pd.DataFrame([new_row])], ignore_index=True)
                        save_sheet(st.session_state.df_store, "Store")
                        save_sheet(st.session_state.df_out, "Out")
                        st.success("Выдано!")
                        st.rerun()

    # --- ПРИХОД ---
    elif mode == "📥 ПРИНЯТЬ (Приход)":
        st.subheader("Пополнение")
        sel = st.selectbox("Какой товар пришел?", options)
        if sel:
            id_ = sel.split(" | ")[0]
            with st.form("in_f"):
                q = st.number_input("Количество", 1.0)
                who = st.text_input("Кто привез")
                rem = st.text_input("Инвойс")
                if st.form_submit_button("Принять"):
                    st.session_state.df_store.loc[st.session_state.df_store['Unic_Mat_№'] == id_, 'Reminder'] += q
                    new_row = {'Unic_Mat_№': id_, 'Description': sel.split(" | ")[1], 'QTY': q, 'Date': datetime.now().date(), 'Delivery_man': who, 'Remarks': rem}
                    st.session_state.df_in = pd.concat([st.session_state.df_in, pd.DataFrame([new_row])], ignore_index=True)
                    save_sheet(st.session_state.df_store, "Store")
                    save_sheet(st.session_state.df_in, "In")
                    st.success("Принято!")
                    st.rerun()

    # --- НОВЫЙ ТОВАР ---
    elif mode == "✨ СОЗДАТЬ НОВЫЙ ТОВАР":
        st.subheader("Создание карточки")
        with st.form("new_t"):
            uid = st.text_input("ID (Unique No)")
            desc = st.text_input("Описание")
            place = st.text_input("Место (Place)")
            price = st.number_input("Цена (Price)", 0.0)
            if st.form_submit_button("Создать"):
                if uid in st.session_state.df_store['Unic_Mat_№'].values:
                    st.error("Такой ID уже есть!")
                else:
                    new_row = {'Unic_Mat_№': uid, 'Description': desc, 'Place': place, 'Unit': 'ea', 'Reminder': 0, 'Price': price, 'Group': '', 'Remarks': ''}
                    st.session_state.df_store = pd.concat([st.session_state.df_store, pd.DataFrame([new_row])], ignore_index=True)
                    save_sheet(st.session_state.df_store, "Store")
                    st.success("Создано!")

# ==========================================
# 4. ОТЧЕТЫ И ПЕЧАТЬ (НОВАЯ ФУНКЦИЯ)
# ==========================================
elif page == "🖨️ Отчеты и Печать":
    st.title("🖨️ Генератор отчетов")
    
    tab1, tab2 = st.tabs(["📅 Отчет по движению (Неделя/Месяц)", "⚠️ Заказ (Low Stock Report)"])
    
    # --- ТАБ 1: Движение ---
    with tab1:
        st.subheader("История операций за период")
        
        col1, col2 = st.columns(2)
        start_date = col1.date_input("С даты:", value=date.today().replace(day=1))
        end_date = col2.date_input("По дату:", value=date.today())
        
        report_type = st.radio("Тип отчета:", ["Только Расход (Out)", "Только Приход (In)"], horizontal=True)
        
        if report_type == "Только Расход (Out)":
            df_source = st.session_state.df_out
        else:
            df_source = st.session_state.df_in
            
        # Фильтрация по датам
        mask = (df_source['Date'] >= start_date) & (df_source['Date'] <= end_date)
        df_report = df_source.loc[mask]
        
        st.write(f"Найдено записей: {len(df_report)}")
        st.dataframe(df_report, use_container_width=True)
        
        # Кнопка скачивания
        csv = df_report.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Скачать отчет (CSV/Excel)",
            data=csv,
            file_name=f"Report_{report_type}_{start_date}_{end_date}.csv",
            mime='text/csv',
        )

    # --- ТАБ 2: Order Report ---
    with tab2:
        st.subheader("⚠️ Список для заказа (Order List)")
        st.markdown("Показывает товары, остаток которых ниже указанного уровня.")
        
        limit = st.slider("Критический уровень остатка:", 1, 50, 5)
        
        df_low = st.session_state.df_store[st.session_state.df_store['Reminder'] <= limit]
        
        st.error(f"Найдено {len(df_low)} позиций, требующих заказа!")
        st.dataframe(df_low[['Unic_Mat_№', 'Description', 'Place', 'Reminder', 'Price']], use_container_width=True)
        
        csv_low = df_low.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Скачать Order List для закупки",
            data=csv_low,
            file_name=f"Order_List_Below_{limit}.csv",
            mime='text/csv',
        )

# ==========================================
# 5. НАСТРОЙКИ (СБРОС С ПАРОЛЕМ)
# ==========================================
elif page == "⚙️ Настройки (Сброс)":
    st.title("⚙️ Опасная зона")
    
    st.markdown("### 🧨 Полная очистка базы данных")
    st.warning("Это действие удалит ВСЕ записи о приходах, расходах и обнулит склад. Отменить нельзя.")
    
    password = st.text_input("Введите пароль администратора:", type="password")
    
    if st.button("💣 СБРОСИТЬ ВСЕ ДАННЫЕ"):
        if password == ADMIN_PASSWORD:
            # Сброс
            empty_store = pd.DataFrame(columns=['Unic_Mat_№', 'Description', 'Place', 'Unit', 'Reminder', 'Price', 'Group', 'Remarks'])
            empty_in = pd.DataFrame(columns=['Unic_Mat_№', 'Description', 'QTY', 'Date', 'Delivery_man', 'Remarks'])
            empty_out = pd.DataFrame(columns=['Unic_Mat_№', 'Description', 'QTY', 'Date', 'Applicant', 'Remarks'])
            
            save_sheet(empty_store, "Store")
            save_sheet(empty_in, "In")
            save_sheet(empty_out, "Out")
            
            st.session_state.data_loaded = False
            st.success("✅ База данных полностью очищена.")
            st.rerun()
        else:

            st.error("⛔ Неверный пароль! Доступ запрещен.")


