import sqlite3
from datetime import date, datetime, time, timedelta
from contextlib import contextmanager

import pandas as pd
import streamlit as st


# =========================================================
# CẤU HÌNH ỨNG DỤNG
# =========================================================

st.set_page_config(
    page_title="HotelPro - Quản lý khách sạn",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_NAME = "hotel.db"


# =========================================================
# KẾT NỐI VÀ KHỞI TẠO DATABASE
# =========================================================

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT NOT NULL UNIQUE,
            room_type TEXT NOT NULL,
            capacity INTEGER NOT NULL DEFAULT 2,
            price REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Trống'
        );

        CREATE TABLE IF NOT EXISTS stays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            checkin TEXT NOT NULL,
            checkout TEXT NOT NULL,
            guests_count INTEGER NOT NULL DEFAULT 1,
            total REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Đã đặt',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guest_id) REFERENCES guests(id),
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );

        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            location TEXT DEFAULT '',
            description TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS restaurant_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            capacity INTEGER NOT NULL DEFAULT 4,
            status TEXT NOT NULL DEFAULT 'Hoạt động',
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
            UNIQUE(restaurant_id, table_name)
        );

        CREATE TABLE IF NOT EXISTS table_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id INTEGER NOT NULL,
            table_id INTEGER NOT NULL,
            booking_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            guests_count INTEGER NOT NULL DEFAULT 1,
            note TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Đã đặt',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guest_id) REFERENCES guests(id),
            FOREIGN KEY (table_id) REFERENCES restaurant_tables(id)
        );

        CREATE TABLE IF NOT EXISTS spa_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            duration INTEGER NOT NULL DEFAULT 60,
            price REAL NOT NULL DEFAULT 0,
            description TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS spa_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_name TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'Hoạt động'
        );

        CREATE TABLE IF NOT EXISTS spa_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            spa_room_id INTEGER NOT NULL,
            booking_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            note TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Đã đặt',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guest_id) REFERENCES guests(id),
            FOREIGN KEY (service_id) REFERENCES spa_services(id),
            FOREIGN KEY (spa_room_id) REFERENCES spa_rooms(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            description TEXT DEFAULT '',
            payment_date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guest_id) REFERENCES guests(id)
        );
        """)

        # Dữ liệu mẫu để có thể dùng ngay
        conn.execute("""
            INSERT OR IGNORE INTO restaurants(name, location, description)
            VALUES ('Nhà hàng chính', 'Tầng 1', 'Nhà hàng phục vụ khách lưu trú')
        """)

        conn.execute("""
            INSERT OR IGNORE INTO restaurants(name, location, description)
            VALUES ('Nhà hàng sân vườn', 'Khu sân vườn', 'Nhà hàng ngoài trời')
        """)

        conn.execute("""
            INSERT OR IGNORE INTO spa_services(name, duration, price, description)
            VALUES ('Massage thư giãn', 60, 500000, 'Massage toàn thân')
        """)

        conn.execute("""
            INSERT OR IGNORE INTO spa_services(name, duration, price, description)
            VALUES ('Chăm sóc da mặt', 45, 350000, 'Chăm sóc da cơ bản')
        """)

        conn.execute("""
            INSERT OR IGNORE INTO spa_rooms(room_name)
            VALUES ('Phòng Spa 1')
        """)

        conn.execute("""
            INSERT OR IGNORE INTO spa_rooms(room_name)
            VALUES ('Phòng Spa 2')
        """)

        conn.execute("""
            INSERT OR IGNORE INTO restaurant_tables(
                restaurant_id, table_name, capacity
            )
            SELECT id, 'Bàn 1', 4 FROM restaurants
            WHERE name = 'Nhà hàng chính'
        """)

        conn.execute("""
            INSERT OR IGNORE INTO restaurant_tables(
                restaurant_id, table_name, capacity
            )
            SELECT id, 'Bàn 2', 4 FROM restaurants
            WHERE name = 'Nhà hàng chính'
        """)

        conn.execute("""
            INSERT OR IGNORE INTO restaurant_tables(
                restaurant_id, table_name, capacity
            )
            SELECT id, 'Bàn 1', 6 FROM restaurants
            WHERE name = 'Nhà hàng sân vườn'
        """)


init_db()


# =========================================================
# HÀM HỖ TRỢ
# =========================================================

def query_df(sql, params=()):
    with get_db() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def query_one(sql, params=()):
    with get_db() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql, params=()):
    with get_db() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def money(value):
    return f"{float(value or 0):,.0f} VNĐ"


def get_guest_options():
    return query_df(
        "SELECT id, name, phone FROM guests ORDER BY name"
    )


def guest_label(row):
    return f"{row['name']} - {row['phone']} (ID: {row['id']})"


def get_guest_id(options, selected_label):
    row = options[options.apply(
        lambda r: guest_label(r), axis=1
    ) == selected_label].iloc[0]
    return int(row["id"])


def get_guest_name(guest_id):
    row = query_one(
        "SELECT name FROM guests WHERE id = ?", (guest_id,)
    )
    return row["name"] if row else "Không xác định"


def show_df(df):
    if df.empty:
        st.info("Chưa có dữ liệu.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def time_to_minutes(value):
    h, m = map(int, value.split(":"))
    return h * 60 + m


def check_overlap(
    table_name,
    resource_column,
    resource_id,
    booking_date,
    start_time,
    end_time,
    exclude_id=None,
):
    """
    Kiểm tra hai khoảng thời gian có giao nhau hay không.
    Điều kiện giao nhau: start < existing_end và end > existing_start.
    """
    sql = f"""
        SELECT id
        FROM {table_name}
        WHERE {resource_column} = ?
          AND booking_date = ?
          AND status NOT IN ('Đã hủy', 'Đã hoàn thành')
          AND start_time < ?
          AND end_time > ?
    """
    params = [resource_id, booking_date, end_time, start_time]

    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)

    return query_one(sql, tuple(params)) is not None


def add_or_get_guest(name, phone, email=""):
    name = name.strip()
    phone = phone.strip()

    if not name or not phone:
        raise ValueError("Vui lòng nhập tên và số điện thoại khách.")

    existing = query_one(
        "SELECT id FROM guests WHERE phone = ?", (phone,)
    )

    if existing:
        execute(
            "UPDATE guests SET name = ?, email = ? WHERE id = ?",
            (name, email.strip(), existing["id"]),
        )
        return int(existing["id"])

    return execute(
        "INSERT INTO guests(name, phone, email) VALUES (?, ?, ?)",
        (name, phone, email.strip()),
    )


def guest_form(prefix):
    name = st.text_input("Họ và tên khách", key=f"{prefix}_name")
    phone = st.text_input("Số điện thoại", key=f"{prefix}_phone")
    email = st.text_input(
        "Email (không bắt buộc)", key=f"{prefix}_email"
    )
    return name, phone, email


def get_booking_guest():
    guests = get_guest_options()

    choice = st.radio(
        "Thông tin khách hàng",
        ["Khách đã có", "Khách mới"],
        horizontal=True,
    )

    if choice == "Khách đã có":
        if guests.empty:
            st.warning("Chưa có khách hàng. Vui lòng thêm khách mới.")
            return None

        labels = [guest_label(row) for _, row in guests.iterrows()]
        selected = st.selectbox("Chọn khách hàng", labels)
        return get_guest_id(guests, selected)

    name, phone, email = guest_form("newguest")

    if st.button("Lưu khách hàng", key="save_new_guest"):
        try:
            guest_id = add_or_get_guest(name, phone, email)
            st.session_state["selected_guest_id"] = guest_id
            st.success("Đã lưu khách hàng.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

    return st.session_state.get("selected_guest_id")


def status_badge(status):
    colors = {
        "Đã đặt": "🟡",
        "Đang sử dụng": "🔵",
        "Đã nhận phòng": "🔵",
        "Đã hoàn thành": "🟢",
        "Đã hủy": "🔴",
        "Trống": "🟢",
        "Đang dọn": "🟠",
        "Bảo trì": "🔴",
    }
    return f"{colors.get(status, '⚪')} {status}"


# =========================================================
# THANH ĐIỀU HƯỚNG
# =========================================================

st.sidebar.title("🏨 HotelPro")
st.sidebar.caption("Hệ thống quản lý khách sạn")

page = st.sidebar.radio(
    "Danh mục",
    [
        "📊 Tổng quan",
        "🛏️ Quản lý phòng",
        "📅 Đặt phòng",
        "👥 Khách hàng",
        "🍽️ Nhà hàng & đặt bàn",
        "💆 Spa & đặt lịch",
        "💳 Thanh toán",
        "📈 Báo cáo & dữ liệu",
    ],
)

st.sidebar.divider()
st.sidebar.caption("HotelPro • Quản lý khách sạn")


# =========================================================
# TRANG TỔNG QUAN
# =========================================================

if page == "📊 Tổng quan":
    st.title("📊 Tổng quan khách sạn")
    st.caption("Tổng hợp tình hình hoạt động hiện tại")

    room_count = query_one("SELECT COUNT(*) AS n FROM rooms")["n"]
    room_free = query_one(
        "SELECT COUNT(*) AS n FROM rooms WHERE status = 'Trống'"
    )["n"]
    guest_count = query_one("SELECT COUNT(*) AS n FROM guests")["n"]
    stay_count = query_one(
        "SELECT COUNT(*) AS n FROM stays WHERE status IN ('Đã đặt', 'Đã nhận phòng')"
    )["n"]
    restaurant_count = query_one(
        "SELECT COUNT(*) AS n FROM restaurants"
    )["n"]
    spa_count = query_one(
        "SELECT COUNT(*) AS n FROM spa_bookings WHERE status = 'Đã đặt'"
    )["n"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Tổng số phòng", room_count)
    c2.metric("Phòng đang trống", room_free)
    c3.metric("Khách hàng", guest_count)

    c4, c5, c6 = st.columns(3)
    c4.metric("Lượt đặt phòng đang hoạt động", stay_count)
    c5.metric("Nhà hàng", restaurant_count)
    c6.metric("Lịch spa sắp tới", spa_count)

    st.divider()

    st.subheader("Phòng khách sạn")
    show_df(query_df("""
        SELECT room_number AS 'Số phòng',
               room_type AS 'Loại phòng',
               capacity AS 'Sức chứa',
               price AS 'Giá/đêm',
               status AS 'Trạng thái'
        FROM rooms
        ORDER BY room_number
        LIMIT 10
    """))

    st.subheader("Đặt phòng gần đây")
    show_df(query_df("""
        SELECT s.id AS 'Mã đặt phòng',
               g.name AS 'Khách hàng',
               r.room_number AS 'Phòng',
               s.checkin AS 'Ngày nhận',
               s.checkout AS 'Ngày trả',
               s.status AS 'Trạng thái'
        FROM stays s
        JOIN guests g ON g.id = s.guest_id
        JOIN rooms r ON r.id = s.room_id
        ORDER BY s.id DESC
        LIMIT 10
    """))


# =========================================================
# QUẢN LÝ PHÒNG
# =========================================================

elif page == "🛏️ Quản lý phòng":
    st.title("🛏️ Quản lý phòng khách sạn")

    tab1, tab2, tab3 = st.tabs([
        "Danh sách phòng",
        "Thêm phòng",
        "Sửa / xóa phòng",
    ])

    with tab1:
        show_df(query_df("""
            SELECT id AS 'ID',
                   room_number AS 'Số phòng',
                   room_type AS 'Loại phòng',
                   capacity AS 'Sức chứa',
                   price AS 'Giá/đêm',
                   status AS 'Trạng thái'
            FROM rooms
            ORDER BY room_number
        """))

    with tab2:
        with st.form("add_room_form"):
            room_number = st.text_input("Số phòng")
            room_type = st.selectbox(
                "Loại phòng",
                ["Standard", "Superior", "Deluxe", "Suite", "Family"],
            )
            capacity = st.number_input(
                "Sức chứa tối đa", min_value=1, max_value=20, value=2
            )
            price = st.number_input(
                "Giá phòng mỗi đêm (VNĐ)",
                min_value=0,
                value=500000,
                step=50000,
            )
            status = st.selectbox(
                "Trạng thái", ["Trống", "Đang dọn", "Bảo trì"]
            )
            submitted = st.form_submit_button("Thêm phòng")

            if submitted:
                if not room_number.strip():
                    st.error("Vui lòng nhập số phòng.")
                else:
                    try:
                        execute("""
                            INSERT INTO rooms(
                                room_number, room_type, capacity, price, status
                            ) VALUES (?, ?, ?, ?, ?)
                        """, (
                            room_number.strip(),
                            room_type,
                            int(capacity),
                            float(price),
                            status,
                        ))
                        st.success("Đã thêm phòng.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Số phòng đã tồn tại.")

    with tab3:
        rooms = query_df("SELECT * FROM rooms ORDER BY room_number")

        if rooms.empty:
            st.info("Chưa có phòng.")
        else:
            room_ids = rooms["id"].tolist()
            selected_id = st.selectbox(
                "Chọn phòng cần sửa",
                room_ids,
                format_func=lambda x: (
                    f"{rooms.loc[rooms.id == x, 'room_number'].iloc[0]} "
                    f"(ID: {x})"
                ),
            )

            room = query_one(
                "SELECT * FROM rooms WHERE id = ?", (selected_id,)
            )

            with st.form("edit_room_form"):
                new_number = st.text_input(
                    "Số phòng", value=room["room_number"]
                )
                new_type = st.selectbox(
                    "Loại phòng",
                    ["Standard", "Superior", "Deluxe", "Suite", "Family"],
                    index=[
                        "Standard", "Superior", "Deluxe", "Suite", "Family"
                    ].index(room["room_type"])
                    if room["room_type"] in
                    ["Standard", "Superior", "Deluxe", "Suite", "Family"]
                    else 0,
                )
                new_capacity = st.number_input(
                    "Sức chứa",
                    min_value=1,
                    max_value=20,
                    value=int(room["capacity"]),
                )
                new_price = st.number_input(
                    "Giá/đêm",
                    min_value=0,
                    value=int(room["price"]),
                    step=50000,
                )
                new_status = st.selectbox(
                    "Trạng thái",
                    ["Trống", "Đang dọn", "Bảo trì"],
                    index=["Trống", "Đang dọn", "Bảo trì"].index(
                        room["status"]
                    )
                    if room["status"] in ["Trống", "Đang dọn", "Bảo trì"]
                    else 0,
                )

                save = st.form_submit_button("Lưu thay đổi")

                if save:
                    try:
                        execute("""
                            UPDATE rooms
                            SET room_number = ?, room_type = ?,
                                capacity = ?, price = ?, status = ?
                            WHERE id = ?
                        """, (
                            new_number.strip(),
                            new_type,
                            int(new_capacity),
                            float(new_price),
                            new_status,
                            selected_id,
                        ))
                        st.success("Đã cập nhật phòng.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Số phòng đã tồn tại.")

            if st.button("🗑️ Xóa phòng", key="delete_room"):
                has_stays = query_one(
                    "SELECT id FROM stays WHERE room_id = ? LIMIT 1",
                    (selected_id,),
                )
                if has_stays:
                    st.error(
                        "Phòng đã có lịch sử đặt phòng, không thể xóa."
                    )
                else:
                    execute("DELETE FROM rooms WHERE id = ?", (selected_id,))
                    st.success("Đã xóa phòng.")
                    st.rerun()


# =========================================================
# ĐẶT PHÒNG
# =========================================================

elif page == "📅 Đặt phòng":
    st.title("📅 Quản lý đặt phòng")

    tab1, tab2 = st.tabs(["Tạo đặt phòng", "Danh sách đặt phòng"])

    with tab1:
        rooms = query_df("""
            SELECT * FROM rooms
            WHERE status != 'Bảo trì'
            ORDER BY room_number
        """)

        if rooms.empty:
            st.warning("Chưa có phòng. Vui lòng thêm phòng trước.")
        else:
            guests = get_guest_options()

            with st.form("create_stay_form"):
                st.subheader("Thông tin khách hàng")

                guest_mode = st.radio(
                    "Khách hàng",
                    ["Khách đã có", "Khách mới"],
                    horizontal=True,
                    key="stay_guest_mode",
                )

                guest_id = None

                if guest_mode == "Khách đã có":
                    if guests.empty:
                        st.warning("Chưa có khách hàng. Hãy chọn Khách mới.")
                    else:
                        labels = [
                            guest_label(row)
                            for _, row in guests.iterrows()
                        ]
                        selected_guest = st.selectbox(
                            "Chọn khách", labels
                        )
                        guest_id = get_guest_id(guests, selected_guest)
                else:
                    guest_name = st.text_input("Họ và tên")
                    guest_phone = st.text_input("Số điện thoại")
                    guest_email = st.text_input("Email")

                st.subheader("Thông tin đặt phòng")

                room_id = st.selectbox(
                    "Chọn phòng",
                    rooms["id"].tolist(),
                    format_func=lambda x: (
                        f"Phòng {rooms.loc[rooms.id == x, 'room_number'].iloc[0]} "
                        f"- {rooms.loc[rooms.id == x, 'room_type'].iloc[0]} "
                        f"- {money(rooms.loc[rooms.id == x, 'price'].iloc[0])}/đêm"
                    ),
                )

                col1, col2 = st.columns(2)
                with col1:
                    checkin = st.date_input("Ngày nhận phòng", value=date.today())
                with col2:
                    checkout = st.date_input(
                        "Ngày trả phòng",
                        value=date.today() + timedelta(days=1),
                    )

                guests_count = st.number_input(
                    "Số khách", min_value=1, max_value=20, value=1
                )

                submit_stay = st.form_submit_button("Tạo đặt phòng")

                if submit_stay:
                    if guest_mode == "Khách mới":
                        if not guest_name.strip() or not guest_phone.strip():
                            st.error("Vui lòng nhập tên và số điện thoại.")
                            st.stop()
                        guest_id = add_or_get_guest(
                            guest_name, guest_phone, guest_email
                        )

                    if guest_id is None:
                        st.error("Vui lòng chọn hoặc tạo khách hàng.")
                        st.stop()

                    if checkout <= checkin:
                        st.error("Ngày trả phòng phải sau ngày nhận phòng.")
                        st.stop()

                    room = query_one(
                        "SELECT * FROM rooms WHERE id = ?", (room_id,)
                    )

                    if guests_count > room["capacity"]:
                        st.error(
                            f"Phòng chỉ chứa tối đa {room['capacity']} khách."
                        )
                        st.stop()

                    conflict = query_one("""
                        SELECT id FROM stays
                        WHERE room_id = ?
                          AND status IN ('Đã đặt', 'Đã nhận phòng')
                          AND checkin < ?
                          AND checkout > ?
                    """, (
                        room_id,
                        checkout.isoformat(),
                        checkin.isoformat(),
                    ))

                    if conflict:
                        st.error("Phòng đã được đặt trong khoảng thời gian này.")
                        st.stop()

                    nights = (checkout - checkin).days
                    total = nights * float(room["price"])

                    execute("""
                        INSERT INTO stays(
                            guest_id, room_id, checkin, checkout,
                            guests_count, total, status
                        ) VALUES (?, ?, ?, ?, ?, ?, 'Đã đặt')
                    """, (
                        guest_id,
                        room_id,
                        checkin.isoformat(),
                        checkout.isoformat(),
                        int(guests_count),
                        total,
                    ))

                    st.success(
                        f"Đặt phòng thành công. Tổng tiền: {money(total)}"
                    )
                    st.rerun()

    with tab2:
        stays = query_df("""
            SELECT s.id AS 'Mã đặt phòng',
                   g.name AS 'Khách hàng',
                   g.phone AS 'Số điện thoại',
                   r.room_number AS 'Phòng',
                   s.checkin AS 'Ngày nhận',
                   s.checkout AS 'Ngày trả',
                   s.guests_count AS 'Số khách',
                   s.total AS 'Tổng tiền',
                   s.status AS 'Trạng thái'
            FROM stays s
            JOIN guests g ON g.id = s.guest_id
            JOIN rooms r ON r.id = s.room_id
            ORDER BY s.id DESC
        """)
        show_df(stays)

        if not stays.empty:
            selected_stay = st.selectbox(
                "Chọn mã đặt phòng để cập nhật",
                stays["Mã đặt phòng"].tolist(),
            )

            stay = query_one(
                "SELECT * FROM stays WHERE id = ?", (selected_stay,)
            )

            new_stay_status = st.selectbox(
                "Trạng thái đặt phòng",
                ["Đã đặt", "Đã nhận phòng", "Đã hoàn thành", "Đã hủy"],
                index=[
                    "Đã đặt", "Đã nhận phòng", "Đã hoàn thành", "Đã hủy"
                ].index(stay["status"]),
            )

            if st.button("Cập nhật trạng thái đặt phòng"):
                execute(
                    "UPDATE stays SET status = ? WHERE id = ?",
                    (new_stay_status, selected_stay),
                )

                # Cập nhật trạng thái phòng theo lượt lưu trú
                if new_stay_status == "Đã nhận phòng":
                    execute(
                        "UPDATE rooms SET status = 'Đang sử dụng' WHERE id = ?",
                        (stay["room_id"],),
                    )
                elif new_stay_status in ["Đã hoàn thành", "Đã hủy"]:
                    other_active = query_one("""
                        SELECT id FROM stays
                        WHERE room_id = ?
                          AND status = 'Đã nhận phòng'
                          AND id != ?
                        LIMIT 1
                    """, (stay["room_id"], selected_stay))

                    if not other_active:
                        execute(
                            "UPDATE rooms SET status = 'Trống' WHERE id = ?",
                            (stay["room_id"],),
                        )

                st.success("Đã cập nhật trạng thái.")
                st.rerun()


# =========================================================
# QUẢN LÝ KHÁCH HÀNG
# =========================================================

elif page == "👥 Khách hàng":
    st.title("👥 Quản lý khách hàng")

    tab1, tab2 = st.tabs(["Danh sách khách", "Thêm khách hàng"])

    with tab1:
        search = st.text_input("Tìm theo tên hoặc số điện thoại")

        sql = """
            SELECT id AS 'ID',
                   name AS 'Họ tên',
                   phone AS 'Số điện thoại',
                   email AS 'Email',
                   created_at AS 'Ngày tạo'
            FROM guests
        """

        if search.strip():
            sql += " WHERE name LIKE ? OR phone LIKE ?"
            params = (f"%{search}%", f"%{search}%")
        else:
            params = ()

        sql += " ORDER BY id DESC"
        show_df(query_df(sql, params))

    with tab2:
        with st.form("add_guest_form"):
            name = st.text_input("Họ và tên")
            phone = st.text_input("Số điện thoại")
            email = st.text_input("Email")

            submitted = st.form_submit_button("Thêm khách")

            if submitted:
                try:
                    add_or_get_guest(name, phone, email)
                    st.success("Đã lưu khách hàng.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


# =========================================================
# NHÀ HÀNG VÀ ĐẶT BÀN
# =========================================================

elif page == "🍽️ Nhà hàng & đặt bàn":
    st.title("🍽️ Quản lý nhà hàng và đặt bàn")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Đặt bàn",
        "Danh sách đặt bàn",
        "Quản lý nhà hàng",
        "Quản lý bàn",
    ])

    # ---------------- ĐẶT BÀN ----------------
    with tab1:
        restaurants = query_df(
            "SELECT * FROM restaurants ORDER BY name"
        )
        guests = get_guest_options()

        if restaurants.empty:
            st.warning("Chưa có nhà hàng. Hãy tạo nhà hàng trước.")
        else:
            with st.form("restaurant_booking_form"):
                guest_mode = st.radio(
                    "Khách hàng",
                    ["Khách đã có", "Khách mới"],
                    horizontal=True,
                    key="restaurant_guest_mode",
                )

                guest_id = None

                if guest_mode == "Khách đã có":
                    if guests.empty:
                        st.warning("Chưa có khách hàng.")
                    else:
                        labels = [
                            guest_label(row)
                            for _, row in guests.iterrows()
                        ]
                        selected_guest = st.selectbox(
                            "Chọn khách", labels, key="restaurant_guest"
                        )
                        guest_id = get_guest_id(guests, selected_guest)
                else:
                    guest_name = st.text_input("Tên khách")
                    guest_phone = st.text_input("Số điện thoại")
                    guest_email = st.text_input("Email")

                restaurant_id = st.selectbox(
                    "Nhà hàng",
                    restaurants["id"].tolist(),
                    format_func=lambda x: (
                        restaurants.loc[
                            restaurants.id == x, "name"
                        ].iloc[0]
                    ),
                )

                tables = query_df("""
                    SELECT * FROM restaurant_tables
                    WHERE restaurant_id = ? AND status = 'Hoạt động'
                    ORDER BY table_name
                """, (restaurant_id,))

                if tables.empty:
                    st.warning("Nhà hàng chưa có bàn hoạt động.")
                    table_id = None
                else:
                    table_id = st.selectbox(
                        "Chọn bàn",
                        tables["id"].tolist(),
                        format_func=lambda x: (
                            f"{tables.loc[tables.id == x, 'table_name'].iloc[0]} "
                            f"({tables.loc[tables.id == x, 'capacity'].iloc[0]} chỗ)"
                        ),
                    )

                col1, col2 = st.columns(2)
                with col1:
                    booking_date = st.date_input(
                        "Ngày đặt bàn", value=date.today()
                    )
                    start_time = st.time_input(
                        "Giờ bắt đầu", value=time(18, 0)
                    )
                with col2:
                    end_time = st.time_input(
                        "Giờ kết thúc", value=time(20, 0)
                    )
                    guests_count = st.number_input(
                        "Số khách", min_value=1, max_value=50, value=2
                    )

                note = st.text_area("Ghi chú (không bắt buộc)")

                submit = st.form_submit_button("Xác nhận đặt bàn")

                if submit:
                    if guest_mode == "Khách mới":
                        if not guest_name.strip() or not guest_phone.strip():
                            st.error("Vui lòng nhập tên và số điện thoại.")
                            st.stop()
                        guest_id = add_or_get_guest(
                            guest_name, guest_phone, guest_email
                        )

                    if guest_id is None or table_id is None:
                        st.error("Vui lòng chọn khách hàng và bàn.")
                        st.stop()

                    if end_time <= start_time:
                        st.error("Giờ kết thúc phải sau giờ bắt đầu.")
                        st.stop()

                    table = query_one(
                        "SELECT * FROM restaurant_tables WHERE id = ?",
                        (table_id,),
                    )

                    if guests_count > table["capacity"]:
                        st.error(
                            f"Bàn chỉ có {table['capacity']} chỗ ngồi."
                        )
                        st.stop()

                    conflict = check_overlap(
                        "table_bookings",
                        "table_id",
                        table_id,
                        booking_date.isoformat(),
                        start_time.strftime("%H:%M"),
                        end_time.strftime("%H:%M"),
                    )

                    if conflict:
                        st.error("Bàn đã được đặt trong khung giờ này.")
                        st.stop()

                    execute("""
                        INSERT INTO table_bookings(
                            guest_id, table_id, booking_date,
                            start_time, end_time, guests_count,
                            note, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Đã đặt')
                    """, (
                        guest_id,
                        table_id,
                        booking_date.isoformat(),
                        start_time.strftime("%H:%M"),
                        end_time.strftime("%H:%M"),
                        int(guests_count),
                        note,
                    ))

                    st.success("Đặt bàn thành công.")
                    st.rerun()

    # ---------------- DANH SÁCH ĐẶT BÀN ----------------
    with tab2:
        bookings = query_df("""
            SELECT b.id AS 'Mã đặt bàn',
                   g.name AS 'Khách hàng',
                   g.phone AS 'Số điện thoại',
                   r.name AS 'Nhà hàng',
                   t.table_name AS 'Bàn',
                   b.booking_date AS 'Ngày',
                   b.start_time AS 'Bắt đầu',
                   b.end_time AS 'Kết thúc',
                   b.guests_count AS 'Số khách',
                   b.status AS 'Trạng thái',
                   b.note AS 'Ghi chú'
            FROM table_bookings b
            JOIN guests g ON g.id = b.guest_id
            JOIN restaurant_tables t ON t.id = b.table_id
            JOIN restaurants r ON r.id = t.restaurant_id
            ORDER BY b.booking_date DESC, b.start_time DESC
        """)

        show_df(bookings)

        if not bookings.empty:
            booking_id = st.selectbox(
                "Chọn mã đặt bàn",
                bookings["Mã đặt bàn"].tolist(),
            )

            booking = query_one(
                "SELECT * FROM table_bookings WHERE id = ?",
                (booking_id,),
            )

            status = st.selectbox(
                "Trạng thái đặt bàn",
                ["Đã đặt", "Đã hoàn thành", "Đã hủy"],
                index=[
                    "Đã đặt", "Đã hoàn thành", "Đã hủy"
                ].index(booking["status"]),
            )

            if st.button("Cập nhật đặt bàn"):
                execute(
                    "UPDATE table_bookings SET status = ? WHERE id = ?",
                    (status, booking_id),
                )
                st.success("Đã cập nhật đặt bàn.")
                st.rerun()

    # ---------------- QUẢN LÝ NHÀ HÀNG ----------------
    with tab3:
        st.subheader("Danh sách nhà hàng")
        show_df(query_df("""
            SELECT id AS 'ID',
                   name AS 'Tên nhà hàng',
                   location AS 'Vị trí',
                   description AS 'Mô tả'
            FROM restaurants
            ORDER BY name
        """))

        with st.form("add_restaurant_form"):
            st.subheader("Thêm nhà hàng")
            name = st.text_input("Tên nhà hàng")
            location = st.text_input("Vị trí")
            description = st.text_area("Mô tả")

            submitted = st.form_submit_button("Thêm nhà hàng")

            if submitted:
                if not name.strip():
                    st.error("Vui lòng nhập tên nhà hàng.")
                else:
                    try:
                        execute("""
                            INSERT INTO restaurants(name, location, description)
                            VALUES (?, ?, ?)
                        """, (name.strip(), location, description))
                        st.success("Đã thêm nhà hàng.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Tên nhà hàng đã tồn tại.")

    # ---------------- QUẢN LÝ BÀN ----------------
    with tab4:
        st.subheader("Danh sách bàn")
        show_df(query_df("""
            SELECT t.id AS 'ID',
                   r.name AS 'Nhà hàng',
                   t.table_name AS 'Tên bàn',
                   t.capacity AS 'Sức chứa',
                   t.status AS 'Trạng thái'
            FROM restaurant_tables t
            JOIN restaurants r ON r.id = t.restaurant_id
            ORDER BY r.name, t.table_name
        """))

        restaurants = query_df("SELECT * FROM restaurants ORDER BY name")

        if restaurants.empty:
            st.warning("Hãy tạo nhà hàng trước.")
        else:
            with st.form("add_table_form"):
                st.subheader("Thêm bàn ăn")

                restaurant_id = st.selectbox(
                    "Nhà hàng",
                    restaurants["id"].tolist(),
                    format_func=lambda x: (
                        restaurants.loc[
                            restaurants.id == x, "name"
                        ].iloc[0]
                    ),
                    key="table_restaurant",
                )

                table_name = st.text_input("Tên bàn")
                capacity = st.number_input(
                    "Sức chứa", min_value=1, max_value=50, value=4
                )

                submitted = st.form_submit_button("Thêm bàn")

                if submitted:
                    if not table_name.strip():
                        st.error("Vui lòng nhập tên bàn.")
                    else:
                        try:
                            execute("""
                                INSERT INTO restaurant_tables(
                                    restaurant_id, table_name, capacity
                                ) VALUES (?, ?, ?)
                            """, (
                                restaurant_id,
                                table_name.strip(),
                                int(capacity),
                            ))
                            st.success("Đã thêm bàn.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Tên bàn đã tồn tại trong nhà hàng.")


# =========================================================
# SPA VÀ ĐẶT LỊCH DỊCH VỤ
# =========================================================

elif page == "💆 Spa & đặt lịch":
    st.title("💆 Quản lý spa và đặt lịch dịch vụ")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Đặt lịch spa",
        "Danh sách lịch",
        "Quản lý dịch vụ",
        "Quản lý phòng spa",
    ])

    # ---------------- ĐẶT LỊCH SPA ----------------
    with tab1:
        services = query_df(
            "SELECT * FROM spa_services ORDER BY name"
        )
        spa_rooms = query_df("""
            SELECT * FROM spa_rooms WHERE status = 'Hoạt động'
            ORDER BY room_name
        """)
        guests = get_guest_options()

        if services.empty:
            st.warning("Chưa có dịch vụ spa.")
        elif spa_rooms.empty:
            st.warning("Chưa có phòng spa hoạt động.")
        else:
            with st.form("spa_booking_form"):
                guest_mode = st.radio(
                    "Khách hàng",
                    ["Khách đã có", "Khách mới"],
                    horizontal=True,
                    key="spa_guest_mode",
                )

                guest_id = None

                if guest_mode == "Khách đã có":
                    if guests.empty:
                        st.warning("Chưa có khách hàng.")
                    else:
                        labels = [
                            guest_label(row)
                            for _, row in guests.iterrows()
                        ]
                        selected_guest = st.selectbox(
                            "Chọn khách", labels, key="spa_guest"
                        )
                        guest_id = get_guest_id(guests, selected_guest)
                else:
                    guest_name = st.text_input("Tên khách")
                    guest_phone = st.text_input("Số điện thoại")
                    guest_email = st.text_input("Email")

                service_id = st.selectbox(
                    "Dịch vụ",
                    services["id"].tolist(),
                    format_func=lambda x: (
                        f"{services.loc[services.id == x, 'name'].iloc[0]} "
                        f"- {int(services.loc[services.id == x, 'duration'].iloc[0])} phút "
                        f"- {money(services.loc[services.id == x, 'price'].iloc[0])}"
                    ),
                )

                spa_room_id = st.selectbox(
                    "Phòng spa",
                    spa_rooms["id"].tolist(),
                    format_func=lambda x: (
                        spa_rooms.loc[
                            spa_rooms.id == x, "room_name"
                        ].iloc[0]
                    ),
                )

                col1, col2 = st.columns(2)
                with col1:
                    booking_date = st.date_input(
                        "Ngày hẹn", value=date.today()
                    )
                    start_time = st.time_input(
                        "Giờ bắt đầu", value=time(9, 0)
                    )
                with col2:
                    st.markdown("**Thời lượng dịch vụ**")
                    service_duration = int(
                        services.loc[
                            services.id == service_id, "duration"
                        ].iloc[0]
                    )
                    st.info(f"{service_duration} phút")

                    end_time = (
                        datetime.combine(date.today(), start_time)
                        + timedelta(minutes=service_duration)
                    ).time()

                    st.write(
                        f"Giờ kết thúc dự kiến: **{end_time.strftime('%H:%M')}**"
                    )

                note = st.text_area("Ghi chú")

                submitted = st.form_submit_button("Xác nhận lịch spa")

                if submitted:
                    if guest_mode == "Khách mới":
                        if not guest_name.strip() or not guest_phone.strip():
                            st.error("Vui lòng nhập tên và số điện thoại.")
                            st.stop()
                        guest_id = add_or_get_guest(
                            guest_name, guest_phone, guest_email
                        )

                    if guest_id is None:
                        st.error("Vui lòng chọn hoặc tạo khách hàng.")
                        st.stop()

                    start_dt = datetime.combine(
                        booking_date, start_time
                    )
                    end_dt = start_dt + timedelta(
                        minutes=service_duration
                    )

                    if end_dt.date() != booking_date:
                        st.error(
                            "Dịch vụ không được kéo dài sang ngày hôm sau."
                        )
                        st.stop()

                    start_str = start_dt.strftime("%H:%M")
                    end_str = end_dt.strftime("%H:%M")

                    conflict = check_overlap(
                        "spa_bookings",
                        "spa_room_id",
                        spa_room_id,
                        booking_date.isoformat(),
                        start_str,
                        end_str,
                    )

                    if conflict:
                        st.error(
                            "Phòng spa đã có lịch trong khoảng thời gian này."
                        )
                        st.stop()

                    service = query_one(
                        "SELECT * FROM spa_services WHERE id = ?",
                        (service_id,),
                    )

                    execute("""
                        INSERT INTO spa_bookings(
                            guest_id, service_id, spa_room_id,
                            booking_date, start_time, end_time,
                            price, note, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Đã đặt')
                    """, (
                        guest_id,
                        service_id,
                        spa_room_id,
                        booking_date.isoformat(),
                        start_str,
                        end_str,
                        float(service["price"]),
                        note,
                    ))

                    st.success("Đặt lịch spa thành công.")
                    st.rerun()

    # ---------------- DANH SÁCH LỊCH SPA ----------------
    with tab2:
        spa_bookings = query_df("""
            SELECT b.id AS 'Mã lịch',
                   g.name AS 'Khách hàng',
                   g.phone AS 'Số điện thoại',
                   s.name AS 'Dịch vụ',
                   r.room_name AS 'Phòng spa',
                   b.booking_date AS 'Ngày',
                   b.start_time AS 'Bắt đầu',
                   b.end_time AS 'Kết thúc',
                   b.price AS 'Giá',
                   b.status AS 'Trạng thái',
                   b.note AS 'Ghi chú'
            FROM spa_bookings b
            JOIN guests g ON g.id = b.guest_id
            JOIN spa_services s ON s.id = b.service_id
            JOIN spa_rooms r ON r.id = b.spa_room_id
            ORDER BY b.booking_date DESC, b.start_time DESC
        """)

        show_df(spa_bookings)

        if not spa_bookings.empty:
            booking_id = st.selectbox(
                "Chọn mã lịch spa",
                spa_bookings["Mã lịch"].tolist(),
            )

            booking = query_one(
                "SELECT * FROM spa_bookings WHERE id = ?",
                (booking_id,),
            )

            status = st.selectbox(
                "Trạng thái lịch spa",
                ["Đã đặt", "Đã hoàn thành", "Đã hủy"],
                index=[
                    "Đã đặt", "Đã hoàn thành", "Đã hủy"
                ].index(booking["status"]),
            )

            if st.button("Cập nhật lịch spa"):
                execute(
                    "UPDATE spa_bookings SET status = ? WHERE id = ?",
                    (status, booking_id),
                )
                st.success("Đã cập nhật lịch spa.")
                st.rerun()

    # ---------------- QUẢN LÝ DỊCH VỤ ----------------
    with tab3:
        st.subheader("Danh sách dịch vụ")
        show_df(query_df("""
            SELECT id AS 'ID',
                   name AS 'Tên dịch vụ',
                   duration AS 'Thời lượng (phút)',
                   price AS 'Giá (VNĐ)',
                   description AS 'Mô tả'
            FROM spa_services
            ORDER BY name
        """))

        with st.form("add_spa_service_form"):
            st.subheader("Thêm dịch vụ spa")
            name = st.text_input("Tên dịch vụ")
            duration = st.number_input(
                "Thời lượng (phút)",
                min_value=5,
                max_value=480,
                value=60,
                step=5,
            )
            price = st.number_input(
                "Giá dịch vụ (VNĐ)",
                min_value=0,
                value=300000,
                step=50000,
            )
            description = st.text_area("Mô tả dịch vụ")

            submitted = st.form_submit_button("Thêm dịch vụ")

            if submitted:
                if not name.strip():
                    st.error("Vui lòng nhập tên dịch vụ.")
                else:
                    try:
                        execute("""
                            INSERT INTO spa_services(
                                name, duration, price, description
                            ) VALUES (?, ?, ?, ?)
                        """, (
                            name.strip(),
                            int(duration),
                            float(price),
                            description,
                        ))
                        st.success("Đã thêm dịch vụ.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Tên dịch vụ đã tồn tại.")

    # ---------------- QUẢN LÝ PHÒNG SPA ----------------
    with tab4:
        st.subheader("Danh sách phòng spa")
        show_df(query_df("""
            SELECT id AS 'ID',
                   room_name AS 'Tên phòng',
                   status AS 'Trạng thái'
            FROM spa_rooms
            ORDER BY room_name
        """))

        with st.form("add_spa_room_form"):
            room_name = st.text_input("Tên phòng spa")
            status = st.selectbox(
                "Trạng thái",
                ["Hoạt động", "Bảo trì"],
            )

            submitted = st.form_submit_button("Thêm phòng spa")

            if submitted:
                if not room_name.strip():
                    st.error("Vui lòng nhập tên phòng.")
                else:
                    try:
                        execute("""
                            INSERT INTO spa_rooms(room_name, status)
                            VALUES (?, ?)
                        """, (room_name.strip(), status))
                        st.success("Đã thêm phòng spa.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Tên phòng spa đã tồn tại.")


# =========================================================
# THANH TOÁN
# =========================================================

elif page == "💳 Thanh toán":
    st.title("💳 Quản lý thanh toán")

    guests = get_guest_options()

    tab1, tab2 = st.tabs(["Tạo thanh toán", "Lịch sử thanh toán"])

    with tab1:
        if guests.empty:
            st.warning("Chưa có khách hàng.")
        else:
            with st.form("payment_form"):
                labels = [
                    guest_label(row)
                    for _, row in guests.iterrows()
                ]
                selected_guest = st.selectbox(
                    "Chọn khách hàng", labels
                )
                guest_id = get_guest_id(guests, selected_guest)

                amount = st.number_input(
                    "Số tiền (VNĐ)",
                    min_value=0,
                    value=0,
                    step=50000,
                )

                method = st.selectbox(
                    "Phương thức thanh toán",
                    ["Tiền mặt", "Chuyển khoản", "Thẻ ngân hàng", "Khác"],
                )

                description = st.text_input("Nội dung thanh toán")
                payment_date = st.date_input(
                    "Ngày thanh toán", value=date.today()
                )

                submitted = st.form_submit_button("Lưu thanh toán")

                if submitted:
                    if amount <= 0:
                        st.error("Số tiền phải lớn hơn 0.")
                    else:
                        execute("""
                            INSERT INTO payments(
                                guest_id, amount, payment_method,
                                description, payment_date
                            ) VALUES (?, ?, ?, ?, ?)
                        """, (
                            guest_id,
                            float(amount),
                            method,
                            description,
                            payment_date.isoformat(),
                        ))
                        st.success("Đã lưu thanh toán.")
                        st.rerun()

    with tab2:
        show_df(query_df("""
            SELECT p.id AS 'Mã thanh toán',
                   g.name AS 'Khách hàng',
                   g.phone AS 'Số điện thoại',
                   p.amount AS 'Số tiền',
                   p.payment_method AS 'Phương thức',
                   p.description AS 'Nội dung',
                   p.payment_date AS 'Ngày thanh toán'
            FROM payments p
            JOIN guests g ON g.id = p.guest_id
            ORDER BY p.id DESC
        """))


# =========================================================
# BÁO CÁO VÀ XUẤT DỮ LIỆU
# =========================================================

elif page == "📈 Báo cáo & dữ liệu":
    st.title("📈 Báo cáo và dữ liệu")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Doanh thu",
        "Đặt phòng",
        "Đặt bàn",
        "Lịch spa",
    ])

    with tab1:
        payment_total = query_one(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments"
        )["total"]

        stay_total = query_one("""
            SELECT COALESCE(SUM(total), 0) AS total
            FROM stays
            WHERE status IN ('Đã nhận phòng', 'Đã hoàn thành')
        """)["total"]

        spa_total = query_one("""
            SELECT COALESCE(SUM(price), 0) AS total
            FROM spa_bookings
            WHERE status = 'Đã hoàn thành'
        """)["total"]

        st.metric("Tổng tiền thanh toán đã ghi nhận", money(payment_total))
        st.metric("Doanh thu lưu trú theo đặt phòng", money(stay_total))
        st.metric("Doanh thu spa hoàn thành", money(spa_total))

        show_df(query_df("""
            SELECT payment_date AS 'Ngày',
                   SUM(amount) AS 'Tổng thanh toán'
            FROM payments
            GROUP BY payment_date
            ORDER BY payment_date DESC
        """))

    with tab2:
        df = query_df("""
            SELECT s.id AS 'Mã đặt phòng',
                   g.name AS 'Khách hàng',
                   r.room_number AS 'Phòng',
                   s.checkin AS 'Ngày nhận',
                   s.checkout AS 'Ngày trả',
                   s.total AS 'Tổng tiền',
                   s.status AS 'Trạng thái'
            FROM stays s
            JOIN guests g ON g.id = s.guest_id
            JOIN rooms r ON r.id = s.room_id
            ORDER BY s.id DESC
        """)
        show_df(df)

        st.download_button(
            "⬇️ Tải báo cáo đặt phòng CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="bao_cao_dat_phong.csv",
            mime="text/csv",
        )

    with tab3:
        df = query_df("""
            SELECT b.id AS 'Mã đặt bàn',
                   g.name AS 'Khách hàng',
                   r.name AS 'Nhà hàng',
                   t.table_name AS 'Bàn',
                   b.booking_date AS 'Ngày',
                   b.start_time AS 'Giờ bắt đầu',
                   b.end_time AS 'Giờ kết thúc',
                   b.guests_count AS 'Số khách',
                   b.status AS 'Trạng thái'
            FROM table_bookings b
            JOIN guests g ON g.id = b.guest_id
            JOIN restaurant_tables t ON t.id = b.table_id
            JOIN restaurants r ON r.id = t.restaurant_id
            ORDER BY b.booking_date DESC
        """)
        show_df(df)

        st.download_button(
            "⬇️ Tải báo cáo đặt bàn CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="bao_cao_dat_ban.csv",
            mime="text/csv",
        )

    with tab4:
        df = query_df("""
            SELECT b.id AS 'Mã lịch spa',
                   g.name AS 'Khách hàng',
                   s.name AS 'Dịch vụ',
                   r.room_name AS 'Phòng spa',
                   b.booking_date AS 'Ngày',
                   b.start_time AS 'Giờ bắt đầu',
                   b.end_time AS 'Giờ kết thúc',
                   b.price AS 'Giá',
                   b.status AS 'Trạng thái'
            FROM spa_bookings b
            JOIN guests g ON g.id = b.guest_id
            JOIN spa_services s ON s.id = b.service_id
            JOIN spa_rooms r ON r.id = b.spa_room_id
            ORDER BY b.booking_date DESC
        """)
        show_df(df)

        st.download_button(
            "⬇️ Tải báo cáo spa CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="bao_cao_spa.csv",
            mime="text/csv",
        )


# =========================================================
# CHÂN TRANG
# =========================================================

st.sidebar.divider()
st.sidebar.caption("🏨 HotelPro | Quản lý khách sạn")
st.sidebar.caption("Dữ liệu được lưu trong file hotel.db")
