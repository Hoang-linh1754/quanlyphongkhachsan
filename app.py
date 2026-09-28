import sqlite3
from datetime import date, timedelta
import streamlit as st
import pandas as pd

DB_PATH = "hotel.db"

st.set_page_config(page_title="Quản lý khách sạn", page_icon="🏨", layout="wide")

def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_number TEXT UNIQUE NOT NULL,
                room_type TEXT NOT NULL,
                price REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Trống'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                room_id INTEGER NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                guests INTEGER NOT NULL DEFAULT 1,
                total REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Đã đặt',
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            )
        """)

def query(sql, params=()):
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=params)

def execute(sql, params=()):
    with connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid

init_db()

st.title("🏨 HỆ THỐNG QUẢN LÝ KHÁCH SẠN")
st.caption("Quản lý phòng, đặt phòng, khách hàng và doanh thu — dữ liệu lưu trong tệp hotel.db.")

# Cập nhật trạng thái phòng theo booking đang ở
today = date.today().isoformat()
with connect() as conn:
    conn.execute("""
        UPDATE rooms SET status = 'Trống'
        WHERE id NOT IN (
            SELECT room_id FROM bookings
            WHERE status IN ('Đã đặt', 'Đang ở')
              AND check_in <= ? AND check_out > ?
        )
        AND status != 'Bảo trì'
    """, (today, today))
    conn.execute("""
        UPDATE rooms SET status = 'Đang sử dụng'
        WHERE id IN (
            SELECT room_id FROM bookings
            WHERE status = 'Đang ở' AND check_in <= ? AND check_out > ?
        )
        AND status != 'Bảo trì'
    """, (today, today))
    conn.commit()

rooms = query("SELECT * FROM rooms")
bookings = query("""
    SELECT b.id, b.guest_name AS 'Khách hàng', b.phone AS 'Số điện thoại',
           r.room_number AS 'Phòng', r.room_type AS 'Loại phòng',
           b.check_in AS 'Ngày nhận', b.check_out AS 'Ngày trả',
           b.guests AS 'Số khách', b.total AS 'Tổng tiền', b.status AS 'Trạng thái'
    FROM bookings b JOIN rooms r ON b.room_id = r.id
    ORDER BY b.id DESC
""")

total_rooms = len(rooms)
vacant = int((rooms["status"] == "Trống").sum()) if total_rooms else 0
occupied = int((rooms["status"] == "Đang sử dụng").sum()) if total_rooms else 0
reserved = int((rooms["status"] == "Đã đặt").sum()) if total_rooms else 0
revenue = float(query("SELECT COALESCE(SUM(total),0) AS amount FROM bookings WHERE status IN ('Đang ở','Đã trả')").iloc[0]["amount"])

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Tổng số phòng", total_rooms)
m2.metric("Phòng trống", vacant)
m3.metric("Đang sử dụng", occupied)
m4.metric("Đã đặt", reserved)
m5.metric("Doanh thu ghi nhận", f"{revenue:,.0f} đ")

tabs = st.tabs(["📊 Tổng quan", "🛏️ Quản lý phòng", "📝 Đặt phòng", "👥 Khách hàng & lưu trú"])

with tabs[0]:
    left, right = st.columns(2)
    with left:
        st.subheader("Tình trạng phòng")
        if total_rooms:
            status_counts = rooms["status"].value_counts().rename_axis("Trạng thái").reset_index(name="Số phòng")
            st.bar_chart(status_counts.set_index("Trạng thái"))
        else:
            st.info("Chưa có phòng. Hãy thêm phòng trong mục Quản lý phòng.")
    with right:
        st.subheader("Đặt phòng gần đây")
        if bookings.empty:
            st.info("Chưa có lượt đặt phòng.")
        else:
            st.dataframe(bookings.drop(columns=["id"]).head(8), use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Danh sách phòng")
    if rooms.empty:
        st.info("Chưa có phòng. Thêm phòng bằng biểu mẫu bên dưới.")
    else:
        st.dataframe(rooms, use_container_width=True, hide_index=True)

    st.markdown("### Thêm phòng")
    with st.form("add_room_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        room_number = c1.text_input("Số phòng (ví dụ 101)")
        room_type = c2.selectbox("Loại phòng", ["Phòng đơn", "Phòng đôi", "Phòng gia đình", "Phòng VIP"])
        price = c3.number_input("Giá phòng / đêm (VNĐ)", min_value=0, value=500000, step=50000)
        add_room = st.form_submit_button("➕ Thêm phòng", use_container_width=True)
        if add_room:
            if not room_number.strip():
                st.error("Vui lòng nhập số phòng.")
            else:
                try:
                    execute("INSERT INTO rooms(room_number, room_type, price, status) VALUES(?,?,?,'Trống')",
                            (room_number.strip(), room_type, price))
                    st.success(f"Đã thêm phòng {room_number.strip()}.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Số phòng đã tồn tại.")

    if not rooms.empty:
        st.markdown("### Chỉnh sửa / xóa phòng")
        room_map = {f"{r['room_number']} — {r['room_type']}": int(r["id"]) for _, r in rooms.iterrows()}
        chosen_label = st.selectbox("Chọn phòng", list(room_map.keys()), key="edit_room_select")
        chosen_id = room_map[chosen_label]
        selected = rooms[rooms["id"] == chosen_id].iloc[0]
        with st.form("edit_room_form"):
            e1, e2, e3 = st.columns(3)
            new_number = e1.text_input("Số phòng", value=str(selected["room_number"]))
            types = ["Phòng đơn", "Phòng đôi", "Phòng gia đình", "Phòng VIP"]
            current_type = str(selected["room_type"])
            new_type = e2.selectbox("Loại phòng", types, index=types.index(current_type) if current_type in types else 0)
            new_price = e3.number_input("Giá / đêm (VNĐ)", min_value=0, value=int(selected["price"]), step=50000)
            status_options = ["Trống", "Đã đặt", "Đang sử dụng", "Đang dọn dẹp", "Bảo trì"]
            current_status = str(selected["status"])
            new_status = st.selectbox("Trạng thái phòng", status_options, index=status_options.index(current_status) if current_status in status_options else 0)
            save_room = st.form_submit_button("💾 Lưu thay đổi")
        if save_room:
            try:
                execute("UPDATE rooms SET room_number=?, room_type=?, price=?, status=? WHERE id=?",
                        (new_number.strip(), new_type, new_price, new_status, chosen_id))
                st.success("Đã cập nhật phòng.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Số phòng đã được sử dụng bởi phòng khác.")
        if st.button("🗑️ Xóa phòng đang chọn", type="secondary"):
            count = query("SELECT COUNT(*) AS n FROM bookings WHERE room_id=?", (chosen_id,)).iloc[0]["n"]
            if count:
                st.error("Không thể xóa phòng đã có lịch sử đặt phòng.")
            else:
                execute("DELETE FROM rooms WHERE id=?", (chosen_id,))
                st.success("Đã xóa phòng.")
                st.rerun()

with tabs[2]:
    st.subheader("Tạo đặt phòng mới")
    available_rooms = query("SELECT * FROM rooms WHERE status NOT IN ('Bảo trì','Đang dọn dẹp') ORDER BY room_number")
    if available_rooms.empty:
        st.warning("Chưa có phòng phù hợp. Hãy thêm phòng trước.")
    else:
        room_options = {
            f"{r['room_number']} | {r['room_type']} | {float(r['price']):,.0f} đ/đêm ({r['status']})": int(r["id"])
            for _, r in available_rooms.iterrows()
        }
        with st.form("booking_form", clear_on_submit=True):
            guest_name = st.text_input("Họ và tên khách")
            phone = st.text_input("Số điện thoại")
            room_label = st.selectbox("Chọn phòng", list(room_options.keys()))
            c1, c2, c3 = st.columns(3)
            check_in = c1.date_input("Ngày nhận phòng", value=date.today(), min_value=date.today())
            check_out = c2.date_input("Ngày trả phòng", value=date.today() + timedelta(days=1), min_value=date.today() + timedelta(days=1))
            guests = c3.number_input("Số khách", min_value=1, max_value=20, value=1)
            submit_booking = st.form_submit_button("✅ Tạo đặt phòng", use_container_width=True)
            if submit_booking:
                if not guest_name.strip() or not phone.strip():
                    st.error("Vui lòng nhập họ tên và số điện thoại.")
                elif check_out <= check_in:
                    st.error("Ngày trả phòng phải sau ngày nhận phòng.")
                else:
                    room_id = room_options[room_label]
                    room_row = available_rooms[available_rooms["id"] == room_id].iloc[0]
                    nights = (check_out - check_in).days
                    total = nights * float(room_row["price"])
                    # Kiểm tra trùng lịch phòng
                    overlap = query("""
                        SELECT COUNT(*) AS n FROM bookings
                        WHERE room_id=? AND status IN ('Đã đặt','Đang ở')
                          AND NOT (check_out <= ? OR check_in >= ?)
                    """, (room_id, check_in.isoformat(), check_out.isoformat())).iloc[0]["n"]
                    if overlap:
                        st.error("Phòng đã có đặt phòng trùng thời gian. Vui lòng chọn phòng hoặc ngày khác.")
                    else:
                        execute("""INSERT INTO bookings(guest_name,phone,room_id,check_in,check_out,guests,total,status)
                                   VALUES(?,?,?,?,?,?,?,'Đã đặt')""",
                                (guest_name.strip(), phone.strip(), room_id, check_in.isoformat(),
                                 check_out.isoformat(), int(guests), total))
                        st.success(f"Đã tạo đặt phòng. Tổng tiền dự kiến: {total:,.0f} đ ({nights} đêm).")
                        st.rerun()

with tabs[3]:
    st.subheader("Danh sách khách hàng và đặt phòng")
    all_bookings = query("""
        SELECT b.id, b.guest_name AS 'Khách hàng', b.phone AS 'Số điện thoại',
               r.room_number AS 'Phòng', r.room_type AS 'Loại phòng',
               b.check_in AS 'Ngày nhận', b.check_out AS 'Ngày trả',
               b.guests AS 'Số khách', b.total AS 'Tổng tiền', b.status AS 'Trạng thái'
        FROM bookings b JOIN rooms r ON b.room_id = r.id
        ORDER BY b.id DESC
    """)
    if all_bookings.empty:
        st.info("Chưa có thông tin khách hàng.")
    else:
        search = st.text_input("Tìm theo tên khách, số điện thoại hoặc số phòng")
        filtered = all_bookings.copy()
        if search.strip():
            mask = filtered.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, na=False)).any(axis=1)
            filtered = filtered[mask]
        st.dataframe(filtered.drop(columns=["id"]), use_container_width=True, hide_index=True)

        st.markdown("### Cập nhật trạng thái đặt phòng")
        booking_map = {
            f"#{int(r['id'])} — {r['Khách hàng']} — phòng {r['Phòng']} ({r['Ngày nhận']} → {r['Ngày trả']})": int(r["id"])
            for _, r in all_bookings.iterrows()
        }
        selected_booking_label = st.selectbox("Chọn lượt đặt phòng", list(booking_map.keys()))
        selected_booking_id = booking_map[selected_booking_label]
        current_booking_status = str(all_bookings[all_bookings["id"] == selected_booking_id].iloc[0]["Trạng thái"])
        booking_statuses = ["Đã đặt", "Đang ở", "Đã trả", "Đã hủy"]
        with st.form("booking_status_form"):
            new_booking_status = st.selectbox(
                "Trạng thái mới", booking_statuses,
                index=booking_statuses.index(current_booking_status) if current_booking_status in booking_statuses else 0
            )
            update_booking = st.form_submit_button("Cập nhật trạng thái")
        if update_booking:
            execute("UPDATE bookings SET status=? WHERE id=?", (new_booking_status, selected_booking_id))
            st.success("Đã cập nhật trạng thái đặt phòng.")
            st.rerun()

st.divider()
st.caption("Lưu ý: Đây là ứng dụng mẫu phục vụ học tập. Doanh thu được tính từ các lượt 'Đang ở' và 'Đã trả'; tiền phòng tính theo số đêm × giá phòng.")

