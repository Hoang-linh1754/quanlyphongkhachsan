
import sqlite3
from datetime import date, timedelta

import pandas as pd
import streamlit as st


# ==================== CẤU HÌNH ====================

st.set_page_config(
    page_title="Quản lý phòng khách sạn",
    page_icon="🏨",
    layout="wide",
)

DB_NAME = "hotel.db"


# ==================== DATABASE ====================

def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT UNIQUE NOT NULL,
            room_type TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            capacity INTEGER NOT NULL DEFAULT 2,
            status TEXT NOT NULL DEFAULT 'Trống',
            customer_name TEXT DEFAULT '',
            customer_phone TEXT DEFAULT '',
            checkin TEXT DEFAULT '',
            checkout TEXT DEFAULT '',
            note TEXT DEFAULT ''
        );
        """)


def query_df(sql, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def query_one(sql, params=()):
    with get_connection() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql, params=()):
    with get_connection() as conn:
        conn.execute(sql, params)
        conn.commit()


init_db()


# ==================== GIAO DIỆN ====================

st.sidebar.title("🏨 HOTEL MANAGER")
page = st.sidebar.radio(
    "Chọn chức năng",
    [
        "📊 Tổng quan",
        "🛏️ Danh sách phòng",
        "➕ Thêm phòng",
        "📝 Đặt phòng và ghi chú khách",
        "🔄 Cập nhật trạng thái",
        "📋 Danh sách khách đang lưu trú",
    ],
)


# ==================== TỔNG QUAN ====================

if page == "📊 Tổng quan":
    st.title("📊 Tổng quan khách sạn")

    total = query_one("SELECT COUNT(*) AS n FROM rooms")["n"]
    available = query_one(
        "SELECT COUNT(*) AS n FROM rooms WHERE status = 'Trống'"
    )["n"]
    occupied = query_one(
        "SELECT COUNT(*) AS n FROM rooms WHERE status = 'Đang sử dụng'"
    )["n"]
    cleaning = query_one(
        "SELECT COUNT(*) AS n FROM rooms WHERE status = 'Đang dọn'"
    )["n"]
    maintenance = query_one(
        "SELECT COUNT(*) AS n FROM rooms WHERE status = 'Bảo trì'"
    )["n"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Tổng số phòng", total)
    c2.metric("Phòng trống", available)
    c3.metric("Đang sử dụng", occupied)
    c4.metric("Đang dọn", cleaning)
    c5.metric("Bảo trì", maintenance)

    st.divider()
    st.subheader("Khách đang lưu trú")

    df = query_df("""
        SELECT room_number AS 'Số phòng',
               room_type AS 'Loại phòng',
               customer_name AS 'Tên khách hàng',
               customer_phone AS 'Số điện thoại',
               checkin AS 'Ngày nhận phòng',
               checkout AS 'Ngày trả phòng',
               note AS 'Ghi chú'
        FROM rooms
        WHERE status = 'Đang sử dụng'
        ORDER BY room_number
    """)

    if df.empty:
        st.info("Hiện chưa có khách lưu trú.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


# ==================== DANH SÁCH PHÒNG ====================

elif page == "🛏️ Danh sách phòng":
    st.title("🛏️ Danh sách phòng khách sạn")

    df = query_df("""
        SELECT id AS 'ID',
               room_number AS 'Số phòng',
               room_type AS 'Loại phòng',
               price AS 'Giá/đêm',
               capacity AS 'Sức chứa',
               status AS 'Trạng thái',
               customer_name AS 'Tên khách hàng',
               customer_phone AS 'Số điện thoại',
               checkin AS 'Ngày nhận',
               checkout AS 'Ngày trả',
               note AS 'Ghi chú'
        FROM rooms
        ORDER BY room_number
    """)

    if df.empty:
        st.info("Chưa có phòng. Hãy thêm phòng mới.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Xuất danh sách phòng CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="danh_sach_phong.csv",
            mime="text/csv",
        )


# ==================== THÊM PHÒNG ====================

elif page == "➕ Thêm phòng":
    st.title("➕ Thêm phòng khách sạn")

    with st.form("add_room_form"):
        room_number = st.text_input("Số phòng")
        room_type = st.selectbox(
            "Loại phòng",
            ["Standard", "Superior", "Deluxe", "Suite", "Family"],
        )
        price = st.number_input(
            "Giá phòng mỗi đêm (VNĐ)",
            min_value=0,
            value=500000,
            step=50000,
        )
        capacity = st.number_input(
            "Sức chứa tối đa",
            min_value=1,
            max_value=20,
            value=2,
        )
        status = st.selectbox(
            "Trạng thái",
            ["Trống", "Đang dọn", "Bảo trì"],
        )

        submitted = st.form_submit_button("Thêm phòng")

        if submitted:
            if not room_number.strip():
                st.error("Vui lòng nhập số phòng.")
            else:
                try:
                    execute("""
                        INSERT INTO rooms(
                            room_number, room_type, price, capacity, status
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        room_number.strip(),
                        room_type,
                        float(price),
                        int(capacity),
                        status,
                    ))
                    st.success("Đã thêm phòng thành công.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Số phòng này đã tồn tại.")


# ==================== ĐẶT PHÒNG VÀ GHI CHÚ ====================

elif page == "📝 Đặt phòng và ghi chú khách":
    st.title("📝 Đặt phòng và ghi chú khách hàng")

    rooms = query_df("""
        SELECT * FROM rooms
        WHERE status = 'Trống'
        ORDER BY room_number
    """)

    if rooms.empty:
        st.warning("Hiện không có phòng trống.")
    else:
        with st.form("booking_form"):
            room_id = st.selectbox(
                "Chọn phòng",
                rooms["id"].tolist(),
                format_func=lambda x: (
                    f"Phòng {rooms.loc[rooms.id == x, 'room_number'].iloc[0]} "
                    f"- {rooms.loc[rooms.id == x, 'room_type'].iloc[0]} "
                    f"- {rooms.loc[rooms.id == x, 'price'].iloc[0]:,.0f} VNĐ/đêm"
                ),
            )

            st.subheader("Thông tin khách hàng")

            customer_name = st.text_input("Tên khách hàng *")
            customer_phone = st.text_input("Số điện thoại")
            checkin = st.date_input(
                "Ngày nhận phòng",
                value=date.today(),
            )
            checkout = st.date_input(
                "Ngày trả phòng",
                value=date.today() + timedelta(days=1),
            )

            note = st.text_area(
                "Ghi chú khách hàng",
                placeholder=(
                    "Ví dụ: Khách muốn phòng yên tĩnh, "
                    "có trẻ em, yêu cầu giường phụ..."
                ),
            )

            submitted = st.form_submit_button("Xác nhận đặt phòng")

            if submitted:
                if not customer_name.strip():
                    st.error("Vui lòng nhập tên khách hàng.")
                elif checkout <= checkin:
                    st.error("Ngày trả phòng phải sau ngày nhận phòng.")
                else:
                    room = query_one(
                        "SELECT * FROM rooms WHERE id = ?",
                        (room_id,),
                    )

                    nights = (checkout - checkin).days
                    total = nights * float(room["price"])

                    execute("""
                        UPDATE rooms
                        SET status = 'Đang sử dụng',
                            customer_name = ?,
                            customer_phone = ?,
                            checkin = ?,
                            checkout = ?,
                            note = ?
                        WHERE id = ?
                    """, (
                        customer_name.strip(),
                        customer_phone.strip(),
                        checkin.isoformat(),
                        checkout.isoformat(),
                        note.strip(),
                        room_id,
                    ))

                    st.success(
                        f"Đã đặt phòng thành công! "
                        f"Tổng tiền dự kiến: {total:,.0f} VNĐ"
                    )
                    st.rerun()


# ==================== CẬP NHẬT TRẠNG THÁI ====================

elif page == "🔄 Cập nhật trạng thái":
    st.title("🔄 Cập nhật trạng thái phòng")

    rooms = query_df("SELECT * FROM rooms ORDER BY room_number")

    if rooms.empty:
        st.info("Chưa có phòng.")
    else:
        selected_id = st.selectbox(
            "Chọn phòng",
            rooms["id"].tolist(),
            format_func=lambda x: (
                f"Phòng {rooms.loc[rooms.id == x, 'room_number'].iloc[0]} "
                f"- {rooms.loc[rooms.id == x, 'status'].iloc[0]}"
            ),
        )

        room = query_one(
            "SELECT * FROM rooms WHERE id = ?",
            (selected_id,),
        )

        st.write(f"**Khách hàng:** {room['customer_name'] or 'Chưa có'}")
        st.write(f"**Số điện thoại:** {room['customer_phone'] or 'Chưa có'}")
        st.write(f"**Ngày nhận:** {room['checkin'] or 'Chưa có'}")
        st.write(f"**Ngày trả:** {room['checkout'] or 'Chưa có'}")
        st.write(f"**Ghi chú:** {room['note'] or 'Không có'}")

        status_options = [
            "Trống",
            "Đang sử dụng",
            "Đang dọn",
            "Bảo trì",
        ]

        new_status = st.selectbox(
            "Trạng thái mới",
            status_options,
            index=status_options.index(room["status"])
            if room["status"] in status_options
            else 0,
        )

        if st.button("Cập nhật trạng thái"):
            if new_status == "Trống":
                execute("""
                    UPDATE rooms
                    SET status = 'Trống',
                        customer_name = '',
                        customer_phone = '',
                        checkin = '',
                        checkout = '',
                        note = ''
                    WHERE id = ?
                """, (selected_id,))
            else:
                execute(
                    "UPDATE rooms SET status = ? WHERE id = ?",
                    (new_status, selected_id),
                )

            st.success("Đã cập nhật trạng thái phòng.")
            st.rerun()


# ==================== DANH SÁCH KHÁCH ĐANG LƯU TRÚ ====================

elif page == "📋 Danh sách khách đang lưu trú":
    st.title("📋 Danh sách khách đang lưu trú")

    search = st.text_input("Tìm theo tên khách hoặc số phòng")

    sql = """
        SELECT room_number AS 'Số phòng',
               room_type AS 'Loại phòng',
               customer_name AS 'Tên khách hàng',
               customer_phone AS 'Số điện thoại',
               checkin AS 'Ngày nhận phòng',
               checkout AS 'Ngày trả phòng',
               note AS 'Ghi chú'
        FROM rooms
        WHERE status = 'Đang sử dụng'
    """

    params = ()

    if search.strip():
        sql += " AND (customer_name LIKE ? OR room_number LIKE ?)"
        params = (f"%{search}%", f"%{search}%")

    sql += " ORDER BY room_number"

    df = query_df(sql, params)

    if df.empty:
        st.info("Không có khách đang lưu trú.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Xuất danh sách khách CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="danh_sach_khach.csv",
            mime="text/csv",
        )
