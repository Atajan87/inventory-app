import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
import plotly.express as px
import json

# ==========================================
# 1. НАСТРОЙКИ И КОНФИГУРАЦИЯ
# ==========================================
st.set_page_config(page_title="Склад Pro: Облако", layout="wide", initial_sidebar_state="expanded")

# Имя вашей Google Таблицы
SPREADSHEET_NAME = "Store_03_Database"

# Пароль для сброса базы
ADMIN_PASSWORD = "admin"

# ==========================================
# 2. ПОДКЛЮЧЕНИЕ К GOOGLE (Самая важная часть)
# ==========================================
@st.cache_resource
def get_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Сценарий А: Запуск в облаке (Streamlit Cloud)
    if "gcp_service_account" in st.secrets:
        # Превращаем объект secrets в обычный словарь Python
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # ЛЕЧЕНИЕ КЛЮЧА: Исправляем переносы строк, которые ломаются при копировании
        if "private_key" in creds_dict:
            # Заменяем экранированные \n на реальные переносы
            key = creds_dict["private_key"]
            creds_dict["private_key"] = key.replace("\\n", "\n")
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # Сценарий Б: Запуск на компьютере (Локально)
    else:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        except FileNotFoundError:
            st.error("❌ Ошибка: Не найден файл credentials.json и нет секретов в облаке.")
            st.stop()
            
    client = gspread.authorize(creds)
    return client

# ==========================================
# 3. РАБОТА С ДАННЫМИ
# ==========================================
def load_data():
    client = get_connection()
    try:
        sh = client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        st.error(f"❌ Не могу найти таблицу: {SPREADSHEET_NAME}. Проверьте название в Google.")
        st.stop()

    # Функция чтения листа с защитой от пустоты
    def read_sheet(name, cols):
        try:
            ws = sh.worksheet(name)
            data = ws.get_all_records()
            if not data:
                return pd.DataFrame(columns=cols)
            return pd.DataFrame(data)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=name, rows=1000, cols=10)
            ws.append_row(cols)
            return pd.DataFrame(columns=cols)

    # Читаем 3 листа
    df_store = read_sheet("Store", ['Unic_Mat_№', 'Description', 'Place', 'Unit', 'Reminder', 'Price', 'Group', 'Remarks'])
    df_in = read_sheet("In", ['Unic_Mat_№', 'Description', 'QTY', 'Date', 'Delivery_man', 'Remarks'])
    df_out = read_sheet("Out", ['Unic_Mat_№', 'Description', 'QTY', 'Date', 'Applicant', 'Remarks'])

    # Чистим типы данных
    df_store['Reminder'] = pd.to_numeric(df_store['Reminder'], errors='coerce').fillna(0)
    df_store['Price'] = pd.to_numeric(df_store['Price'], errors='coerce').fillna(0)
    
    # Даты
    df_in['Date'] = pd.to_datetime(df_in['Date'], errors='coerce').dt.date
    df_out['Date'] = pd.to_datetime(df_out['Date'], errors='coerce').dt.date

    return df_store, df_in, df_out

def save_sheet(df, worksheet_name):
    """Сохраняет DataFrame обратно в Google Sheet"""
    client = get_connection()
    sh = client.open(SPREADSHEET_NAME)
    ws = sh.worksheet(worksheet_name)
    
    # Конвертируем даты в строки перед отправкой, чтобы JSON не ломался
    df_export = df.copy()
    if 'Date' in df_export.columns:
        df_export['Date'] = df_export['Date'].astype(str)
        
    ws.clear()
    ws.update([df_export.columns.values.tolist()] + df_export.values.tolist())

# ==========================================
# 4. ИНТЕРФЕЙС ПРИЛОЖЕНИЯ
# ==========================================

# Инициализация данных
if 'data_loaded' not in st.session_state:
    with st.spinner('📡 Соединение с сервером Google...'):
        st.session_state.df_store, st.session_state.df_in, st.session_state.df_out = load_data()
    st.session_state.data_loaded = True

# Кнопка обновления в сайдбаре
with st.sidebar:
    st.title("🗂 Меню Склада")
    if st.button("🔄 Обновить данные", type="primary"):
        st.cache_resource.clear()
        st.session_state.data_loaded = False
        st.rerun()

# Навигация
page = st.sidebar.radio("Перейти к разделу:", 
    ["📊 Статистика", "📦 Склад (Остатки)", "📝 Операции (Приход/Расход)", "🖨️ Отчеты", "⚙️ Настройки"]
)

# --- 1. СТАТИСТИКА ---
if page == "📊 Статистика":
    st.title("📊 Панель управления")
    df_s = st.session_state.df_store
    df_o = st.session_state.df_out

    # Метрики
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Всего позиций", len(df_s))
    kpi2.metric("Сумма склада (¥)", f"{ (df_s['Reminder'] * df_s['Price']).sum():,.0f}")
    kpi3.metric("Закончились (0 шт)", len(df_s[df_s['Reminder'] <= 0]), delta_color="inverse")

    st.divider()
    
    # Графики
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Топ-5 по расходу")
        if not df_o.empty:
            top = df_o.groupby('Description')['QTY'].sum().nlargest(5).reset_index()
            fig = px.pie(top, values='QTY', names='Description', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Динамика выдачи")
        if not df_o.empty:
            daily = df_o.groupby('Date')['QTY'].sum().reset_index()
            fig2 = px.bar(daily, x='Date', y='QTY')
            st.plotly_chart(fig2, use_container_width=True)

# --- 2. СКЛАД ---
elif page == "📦 Склад (Остатки)":
    st.title("📦 Полный список")
    
    search = st.text_input("🔍 Поиск (ID или Название)")
    df = st.session_state.df_store
    
    if search:
        mask = df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
        df_display = df[mask]
    else:
        df_display = df

    # Редактируемая таблица
    edited_df = st.data_editor(
        df_display,
        height=600,
        use_container_width=True,
        column_config={
            "Unic_Mat_№": st.column_config.TextColumn("ID", disabled=True),
            "Reminder": st.column_config.NumberColumn("Остаток", format="%d"),
            "Price": st.column_config.NumberColumn("Цена", format="%.2f ¥"),
        }
    )

    if st.button("💾 Сохранить изменения"):
        st.session_state.df_store.update(edited_df)
        with st.spinner("Сохраняю в Google..."):
            save_sheet(st.session_state.df_store, "Store")
        st.success("✅ Данные обновлены!")

# --- 3. ОПЕРАЦИИ ---
elif page == "📝 Операции (Приход/Расход)":
    st.title("Движение товара")
    
    mode = st.tabs(["📤 РАСХОД (Выдача)", "📥 ПРИХОД (Пополнение)", "✨ НОВЫЙ ТОВАР"])
    options = st.session_state.df_store['Unic_Mat_№'].astype(str) + " | " + st.session_state.df_store['Description'].astype(str)

    # ВЫДАЧА
    with mode[0]:
        sel = st.selectbox("Что выдаем?", options, key="out_sel")
        if sel:
            id_ = sel.split(" | ")[0]
            curr = st.session_state.df_store.loc[st.session_state.df_store['Unic_Mat_№'] == id_, 'Reminder'].values[0]
            
            if curr <= 0:
                st.error("⛔ Товара нет в наличии!")
            else:
                st.info(f"Доступно: {curr}")
                with st.form("out_form"):
                    qty = st.number_input("Количество", 1.0, float(curr))
                    who = st.text_input("Получатель")
                    rem = st.text_input("Куда / Причина")
                    
                    if st.form_submit_button("🚀 Списать"):
                        st.session_state.df_store.loc[st.session_state.df_store['Unic_Mat_№'] == id_, 'Reminder'] -= qty
                        new_rec = {
                            'Unic_Mat_№': id_, 'Description': sel.split(" | ")[1], 
                            'QTY': qty, 'Date': date.today(), 'Applicant': who, 'Remarks': rem
                        }
                        st.session_state.df_out = pd.concat([st.session_state.df_out, pd.DataFrame([new_rec])], ignore_index=True)
                        save_sheet(st.session_state.df_store, "Store")
                        save_sheet(st.session_state.df_out, "Out")
                        st.success("Выдано!")
                        st.rerun()

    # ПОПОЛНЕНИЕ
    with mode[1]:
        sel_in = st.selectbox("Что пришло?", options, key="in_sel")
        if sel_in:
            id_in = sel_in.split(" | ")[0]
            with st.form("in_form"):
                qty = st.number_input("Количество", 1.0)
                who = st.text_input("Доставщик")
                rem = st.text_input("Инвойс / Инфо")
                if st.form_submit_button("📥 Принять"):
                    st.session_state.df_store.loc[st.session_state.df_store['Unic_Mat_№'] == id_in, 'Reminder'] += qty
                    new_rec = {
                        'Unic_Mat_№': id_in, 'Description': sel_in.split(" | ")[1], 
                        'QTY': qty, 'Date': date.today(), 'Delivery_man': who, 'Remarks': rem
                    }
                    st.session_state.df_in = pd.concat([st.session_state.df_in, pd.DataFrame([new_rec])], ignore_index=True)
                    save_sheet(st.session_state.df_store, "Store")
                    save_sheet(st.session_state.df_in, "In")
                    st.success("Принято!")
                    st.rerun()

    # НОВЫЙ ТОВАР
    with mode[2]:
        with st.form("new_item"):
            col1, col2 = st.columns(2)
            uid = col1.text_input("ID (Unic_Mat_№)")
            desc = col2.text_input("Описание (Description)")
            
            col3, col4, col5 = st.columns(3)
            place = col3.text_input("Место (Place)")
            price = col4.number_input("Цена", 0.0)
            unit = col5.text_input("Ед. изм.", "ea")
            
            if st.form_submit_button("Создать карточку"):
                if uid in st.session_state.df_store['Unic_Mat_№'].values:
                    st.error("Такой ID уже существует!")
                else:
                    new_row = {
                        'Unic_Mat_№': uid, 'Description': desc, 'Place': place, 
                        'Unit': unit, 'Reminder': 0, 'Price': price, 'Group': '', 'Remarks': ''
                    }
                    st.session_state.df_store = pd.concat([st.session_state.df_store, pd.DataFrame([new_row])], ignore_index=True)
                    save_sheet(st.session_state.df_store, "Store")
                    st.success("Товар создан!")

# --- 4. ОТЧЕТЫ ---
elif page == "🖨️ Отчеты":
    st.title("Генератор отчетов")
    
    t1, t2 = st.tabs(["Движение (История)", "Заказ (Low Stock)"])
    
    with t1:
        d1 = st.date_input("С даты", date.today().replace(day=1))
        d2 = st.date_input("По дату", date.today())
        
        # Фильтр для In и Out
        mask_in = (st.session_state.df_in['Date'] >= d1) & (st.session_state.df_in['Date'] <= d2)
        mask_out = (st.session_state.df_out['Date'] >= d1) & (st.session_state.df_out['Date'] <= d2)
        
        st.write("📥 Приходы за период:")
        st.dataframe(st.session_state.df_in[mask_in])
        st.write("📤 Расходы за период:")
        st.dataframe(st.session_state.df_out[mask_out])
        
    with t2:
        limit = st.slider("Критический уровень", 1, 20, 5)
        low_stock = st.session_state.df_store[st.session_state.df_store['Reminder'] <= limit]
        st.dataframe(low_stock)
        
        st.download_button(
            "⬇️ Скачать список для заказа (CSV)",
            low_stock.to_csv(index=False).encode('utf-8'),
            "order_list.csv",
            "text/csv"
        )

# --- 5. НАСТРОЙКИ ---
elif page == "⚙️ Настройки":
    st.title("Опасная зона")
    st.warning("Сброс удалит все данные из таблицы!")
    
    pwd = st.text_input("Пароль администратора", type="password")
    if st.button("🧨 СБРОСИТЬ БАЗУ"):
        if pwd == ADMIN_PASSWORD:
            # Создаем пустые таблицы
            empty_s = pd.DataFrame(columns=['Unic_Mat_№', 'Description', 'Place', 'Unit', 'Reminder', 'Price', 'Group', 'Remarks'])
            empty_i = pd.DataFrame(columns=['Unic_Mat_№', 'Description', 'QTY', 'Date', 'Delivery_man', 'Remarks'])
            empty_o = pd.DataFrame(columns=['Unic_Mat_№', 'Description', 'QTY', 'Date', 'Applicant', 'Remarks'])
            
            save_sheet(empty_s, "Store")
            save_sheet(empty_i, "In")
            save_sheet(empty_o, "Out")
            st.success("База очищена.")
            st.cache_resource.clear()
        else:
            st.error("Неверный пароль")
