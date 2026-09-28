import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# =========================
# CẤU HÌNH & CƠ SỞ DỮ LIỆU
# =========================
st.set_page_config(page_title="HotelPro | Quản lý khách sạn", page_icon="🏨", layout="wide")
DB_PATH = Path(__file__).with_name("hotel.db")
ROOM_STATUSES = ["Trống", "Đang sử dụng", "Đang dọn", "Bảo trì"]
BOOKING_STATUSES = ["Đã đặt", "Đang ở", "Đã trả", "Đã hủy"]
ROOM_TYPES = ["Phòng đơn", "Phòng đôi", "Phòng gia đình", "Phòng VIP", "Suite"]

def db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS rooms(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE,
            room_type TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            capacity INTEGER NOT NULL DEFAULT 2,
            floor INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'Trống',
            note TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS guests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT DEFAULT '',
            identity_no TEXT DEFAULT '',
            address TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS bookings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            guest_id INTEGER NOT NULL REFERENCES guests(id),
            room_id INTEGER NOT NULL REFERENCES rooms(id),
            check_in TEXT NOT NULL,
            check_out TEXT NOT NULL,
            adults INTEGER NOT NULL DEFAULT 1,
            children INTEGER NOT NULL DEFAULT 0,
            room_price REAL NOT NULL DEFAULT 0,
            discount REAL NOT NULL DEFAULT 0,
            deposit REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Đã đặt',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS services(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'lần',
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS service_orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL REFERENCES bookings(id),
            service_id INTEGER NOT NULL REFERENCES services(id),
            quantity REAL NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0,
            ordered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL REFERENCES bookings(id),
            amount REAL NOT NULL,
            method TEXT NOT NULL DEFAULT 'Tiền mặt',
            note TEXT DEFAULT '',
            paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS housekeeping(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL REFERENCES rooms(id),
            task TEXT NOT NULL DEFAULT 'Dọn phòng',
            staff TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Chờ xử lý',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT DEFAULT ''
        );
        """)
        # Dữ liệu dịch vụ mặc định chỉ thêm nếu chưa có
        for name, price, unit in [
            ("Nước suối", 10000, "chai"), ("Giặt ủi", 30000, "kg"),
            ("Ăn sáng", 80000, "suất"), ("Đưa đón sân bay", 250000, "chuyến"),
            ("Minibar", 50000, "lần")
        ]:
            con.execute("INSERT OR IGNORE INTO services(name,price,unit) VALUES(?,?,?)", (name, price, unit))

def read(sql, params=()):
    with db() as con:
        return pd.read_sql_query(sql, con, params=params)

def run(sql, params=()):
    with db() as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.lastrowid

def money(v):
    return f"{float(v or 0):,.0f} đ"

def nights(ci, co):
    return max(0, (date.fromisoformat(str(co)) - date.fromisoformat(str(ci))).days)

def booking_total(booking_id):
    b = read("SELECT * FROM bookings WHERE id=?", (booking_id,))
    if b.empty:
        return 0.0, 0.0, 0.0, 0.0
    x = b.iloc[0]
    room_total = nights(x["check_in"], x["check_out"]) * float(x["room_price"])
    extra = float(read("SELECT COALESCE(SUM(quantity*unit_price),0) AS n FROM service_orders WHERE booking_id=?", (booking_id,)).iloc[0]["n"])
    discount = float(x["discount"] or 0)
    total = max(0, room_total + extra - discount)
    paid = float(read("SELECT COALESCE(SUM(amount),0) AS n FROM payments WHERE booking_id=?", (booking_id,)).iloc[0]["n"])
    return room_total, extra, total, paid

def refresh_room_statuses():
    # Tự đồng bộ phòng đang ở theo các lượt lưu trú thực tế; không ghi đè dọn/bảo trì.
    today = date.today().isoformat()
    with db() as con:
        con.execute("""
            UPDATE rooms SET status='Đang sử dụng'
            WHERE id IN (SELECT room_id FROM bookings WHERE status='Đang ở' AND check_in<=? AND check_out>?)
            AND status NOT IN ('Bảo trì','Đang dọn')
        """, (today, today))
        con.execute("""
            UPDATE rooms SET status='Trống'
            WHERE status='Đang sử dụng'
            AND id NOT IN (SELECT room_id FROM bookings WHERE status='Đang ở' AND check_in<=? AND check_out>?)
        """, (today, today))

def overlaps(room_id, ci, co, exclude_id=None):
    sql = """SELECT COUNT(*) n FROM bookings
             WHERE room_id=? AND status IN ('Đã đặt','Đang ở')
             AND NOT (check_out<=? OR check_in>=?)"""
    params = [room_id, ci, co]
    if exclude_id:
        sql += " AND id<>?"
        params.append(exclude_id)
    return int(read(sql, tuple(params)).iloc[0]["n"]) > 0

def get_booking_rows(where="", params=()):
    sql = """
    SELECT b.id,b.code,g.full_name AS guest,g.phone,r.number AS room,r.room_type,
           b.check_in,b.check_out,b.adults,b.children,b.status,b.deposit,b.discount,
           b.room_price,b.note
    FROM bookings b JOIN guests g ON g.id=b.guest_id JOIN rooms r ON r.id=b.room_id
    """
    if where:
        sql += " WHERE " + where
    sql += " ORDER BY b.id DESC"
    return read(sql, params)

def add_guest(name, phone, email="", identity="", address=""):
    # Tận dụng hồ sơ đã có cùng số điện thoại
    found = read("SELECT id FROM guests WHERE phone=? ORDER BY id LIMIT 1", (phone.strip(),))
    if not found.empty:
        gid = int(found.iloc[0]["id"])
        run("UPDATE guests SET full_name=?,email=?,identity_no=?,address=? WHERE id=?",
            (name.strip(), email.strip(), identity.strip(), address.strip(), gid))
        return gid
    return run("INSERT INTO guests(full_name,phone,email,identity_no,address) VALUES(?,?,?,?,?)",
               (name.strip(), phone.strip(), email.strip(), identity.strip(), address.strip()))

init_db()
refresh_room_statuses()

# =========================
# GIAO DIỆN
# =========================
st.sidebar.title("🏨 HotelPro")
st.sidebar.caption("Hệ thống quản lý khách sạn")
page = st.sidebar.radio("MENU", [
    "📊 Tổng quan", "🛏️ Quản lý phòng", "📅 Đặt phòng", "🧾 Lễ tân & lưu trú",
    "👤 Khách hàng", "🛎️ Dịch vụ & hóa đơn", "🧹 Buồng phòng", "📈 Báo cáo", "⚙️ Cài đặt"
])
st.sidebar.divider()
st.sidebar.caption(f"Ngày hệ thống: {date.today().strftime('%d/%m/%Y')}")
st.sidebar.caption("Dữ liệu lưu tại hotel.db")

st.title("🏨 HotelPro — Quản lý khách sạn")
st.caption("Quản lý phòng • Đặt phòng • Khách hàng • Dịch vụ • Thanh toán • Buồng phòng")

# -------------------------
# TỔNG QUAN
# -------------------------
if page == "📊 Tổng quan":
    rooms = read("SELECT * FROM rooms")
    bookings = get_booking_rows()
    room_count = len(rooms)
    vacant = int((rooms.status == "Trống").sum()) if room_count else 0
    in_use = int((rooms.status == "Đang sử dụng").sum()) if room_count else 0
    cleaning = int((rooms.status == "Đang dọn").sum()) if room_count else 0
    maintenance = int((rooms.status == "Bảo trì").sum()) if room_count else 0
    today_s = date.today().isoformat()
    arrivals = int(read("SELECT COUNT(*) n FROM bookings WHERE check_in=? AND status='Đã đặt'", (today_s,)).iloc[0]["n"])
    departures = int(read("SELECT COUNT(*) n FROM bookings WHERE check_out=? AND status='Đang ở'", (today_s,)).iloc[0]["n"])
    revenue = float(read("SELECT COALESCE(SUM(amount),0) n FROM payments").iloc[0]["n"])
    c = st.columns(6)
    for col, label, val in zip(c, ["Tổng phòng", "Phòng trống", "Đang ở", "Đang dọn", "Bảo trì", "Lượt nhận hôm nay"],
                               [room_count, vacant, in_use, cleaning, maintenance, arrivals]):
        col.metric(label, val)
    st.metric("Tổng tiền đã thu", money(revenue))
    a, b = st.columns(2)
    with a:
        st.subheader("Cơ cấu trạng thái phòng")
        if rooms.empty:
            st.info("Chưa có dữ liệu phòng. Hãy thêm phòng ở mục Quản lý phòng.")
        else:
            counts = rooms["status"].value_counts().rename_axis("Trạng thái").reset_index(name="Số phòng")
            st.bar_chart(counts.set_index("Trạng thái"))
    with b:
        st.subheader("Lịch nhận / trả phòng hôm nay")
        st.write(f"**Nhận phòng:** {arrivals} lượt")
        st.write(f"**Trả phòng:** {departures} lượt")
        due = get_booking_rows("b.check_out=? AND b.status='Đang ở'", (today_s,))
        if due.empty:
            st.success("Không có lượt trả phòng đang chờ hôm nay.")
        else:
            st.dataframe(due[["code", "guest", "room", "check_out"]], use_container_width=True, hide_index=True)
    st.subheader("Đặt phòng mới nhất")
    if bookings.empty:
        st.info("Chưa có đặt phòng.")
    else:
        st.dataframe(bookings[["code", "guest", "room", "check_in", "check_out", "status"]].head(10),
                     use_container_width=True, hide_index=True)

# -------------------------
# QUẢN LÝ PHÒNG
# -------------------------
elif page == "🛏️ Quản lý phòng":
    st.subheader("Danh sách phòng")
    rooms = read("SELECT * FROM rooms ORDER BY CAST(number AS INTEGER), number")
    if not rooms.empty:
        f1, f2 = st.columns(2)
        status_filter = f1.selectbox("Lọc trạng thái", ["Tất cả"] + ROOM_STATUSES)
        type_filter = f2.selectbox("Lọc loại phòng", ["Tất cả"] + sorted(rooms.room_type.unique().tolist()))
        show = rooms.copy()
        if status_filter != "Tất cả":
            show = show[show.status == status_filter]
        if type_filter != "Tất cả":
            show = show[show.room_type == type_filter]
        st.dataframe(show, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có phòng. Thêm phòng bằng biểu mẫu bên dưới.")
    with st.expander("➕ Thêm phòng", expanded=rooms.empty):
        with st.form("add_room"):
            c1,c2,c3,c4,c5 = st.columns(5)
            number = c1.text_input("Số phòng *")
            typ = c2.selectbox("Loại phòng", ROOM_TYPES)
            price = c3.number_input("Giá / đêm (đ)", min_value=0, value=500000, step=50000)
            capacity = c4.number_input("Sức chứa", min_value=1, max_value=20, value=2)
            floor = c5.number_input("Tầng", min_value=0, max_value=100, value=1)
            note = st.text_input("Ghi chú")
            submitted = st.form_submit_button("Thêm phòng")
            if submitted:
                if not number.strip():
                    st.error("Vui lòng nhập số phòng.")
                else:
                    try:
                        run("INSERT INTO rooms(number,room_type,price,capacity,floor,note) VALUES(?,?,?,?,?,?)",
                            (number.strip(), typ, price, int(capacity), int(floor), note.strip()))
                        st.success("Đã thêm phòng.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Số phòng đã tồn tại.")
    if not rooms.empty:
        st.markdown("### Chỉnh sửa phòng")
        room_map = {f"{r['number']} — {r['room_type']}": int(r["id"]) for _,r in rooms.iterrows()}
        label = st.selectbox("Chọn phòng cần sửa", list(room_map))
        rid = room_map[label]
        r = rooms[rooms.id == rid].iloc[0]
        with st.form("edit_room"):
            c1,c2,c3 = st.columns(3)
            nnum = c1.text_input("Số phòng", str(r.number))
            ntype = c2.selectbox("Loại phòng", ROOM_TYPES, index=ROOM_TYPES.index(r.room_type) if r.room_type in ROOM_TYPES else 0)
            nprice = c3.number_input("Giá / đêm", min_value=0, value=int(r.price), step=50000)
            c4,c5,c6 = st.columns(3)
            ncap = c4.number_input("Sức chứa", min_value=1, max_value=20, value=int(r.capacity))
            nf = c5.number_input("Tầng", min_value=0, max_value=100, value=int(r.floor))
            nstatus = c6.selectbox("Trạng thái", ROOM_STATUSES, index=ROOM_STATUSES.index(r.status) if r.status in ROOM_STATUSES else 0)
            nnote = st.text_input("Ghi chú", str(r.note or ""))
            save = st.form_submit_button("Lưu thay đổi")
            if save:
                try:
                    run("UPDATE rooms SET number=?,room_type=?,price=?,capacity=?,floor=?,status=?,note=? WHERE id=?",
                        (nnum.strip(), ntype, nprice, int(ncap), int(nf), nstatus, nnote.strip(), rid))
                    st.success("Đã cập nhật phòng.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Số phòng bị trùng.")
        with st.expander("🗑️ Xóa phòng"):
            st.warning("Chỉ xóa được phòng chưa có lịch sử đặt phòng.")
            if st.button("Xóa phòng đã chọn", type="secondary"):
                used = int(read("SELECT COUNT(*) n FROM bookings WHERE room_id=?", (rid,)).iloc[0]["n"])
                if used:
                    st.error("Phòng đã có lịch sử đặt phòng, không thể xóa.")
                else:
                    run("DELETE FROM rooms WHERE id=?", (rid,))
                    st.success("Đã xóa phòng.")
                    st.rerun()

# -------------------------
# ĐẶT PHÒNG
# -------------------------
elif page == "📅 Đặt phòng":
    st.subheader("Tạo đặt phòng")
    room_df = read("SELECT * FROM rooms WHERE status NOT IN ('Bảo trì','Đang dọn') ORDER BY number")
    if room_df.empty:
        st.warning("Cần tạo phòng trước khi đặt.")
    else:
        with st.form("create_booking"):
            st.markdown("#### Thông tin khách")
            c1,c2,c3 = st.columns(3)
            guest_name = c1.text_input("Họ tên khách *")
            phone = c2.text_input("Số điện thoại *")
            email = c3.text_input("Email")
            c4,c5,c6 = st.columns(3)
            identity = c4.text_input("CCCD / Hộ chiếu")
            address = c5.text_input("Địa chỉ")
            room_options = {f"Phòng {r['number']} · {r['room_type']} · {money(r['price'])}/đêm": int(r["id"]) for _,r in room_df.iterrows()}
            room_label = c6.selectbox("Chọn phòng", list(room_options))
            c7,c8,c9,c10 = st.columns(4)
            ci = c7.date_input("Ngày nhận", value=date.today(), min_value=date.today())
            co = c8.date_input("Ngày trả", value=date.today()+timedelta(days=1), min_value=date.today()+timedelta(days=1))
            adults = c9.number_input("Người lớn", min_value=1, max_value=20, value=1)
            children = c10.number_input("Trẻ em", min_value=0, max_value=20, value=0)
            c11,c12,c13 = st.columns(3)
            discount = c11.number_input("Giảm giá (đ)", min_value=0, value=0, step=50000)
            deposit = c12.number_input("Tiền cọc (đ)", min_value=0, value=0, step=100000)
            note = c13.text_input("Ghi chú")
            submit = st.form_submit_button("Tạo đặt phòng", use_container_width=True)
            if submit:
                if not guest_name.strip() or not phone.strip():
                    st.error("Nhập họ tên và số điện thoại khách.")
                elif co <= ci:
                    st.error("Ngày trả phải sau ngày nhận.")
                else:
                    room_id = room_options[room_label]
                    rr = room_df[room_df.id == room_id].iloc[0]
                    if adults + children > int(rr.capacity):
                        st.error(f"Phòng này có sức chứa tối đa {int(rr.capacity)} người.")
                    elif overlaps(room_id, ci.isoformat(), co.isoformat()):
                        st.error("Phòng đã có lượt đặt trùng thời gian.")
                    else:
                        gid = add_guest(guest_name, phone, email, identity, address)
                        code = "BK" + datetime.now().strftime("%y%m%d%H%M%S") + str(gid)
                        bid = run("""INSERT INTO bookings(code,guest_id,room_id,check_in,check_out,adults,children,room_price,discount,deposit,status,note)
                                     VALUES(?,?,?,?,?,?,?,?,?,?, 'Đã đặt',?)""",
                                  (code,gid,room_id,ci.isoformat(),co.isoformat(),int(adults),int(children),
                                   float(rr.price),float(discount),float(deposit),note.strip()))
                        if deposit > 0:
                            run("INSERT INTO payments(booking_id,amount,method,note) VALUES(?,?,?,?)",
                                (bid,float(deposit),"Tiền mặt","Thu tiền cọc"))
                        st.success(f"Đã tạo đặt phòng {code}. Tiền phòng dự kiến: {money(nights(ci.isoformat(),co.isoformat())*float(rr.price)-discount)}")
                        st.rerun()
    st.divider()
    st.subheader("Danh sách đặt phòng")
    allb = get_booking_rows()
    if allb.empty:
        st.info("Chưa có lượt đặt phòng.")
    else:
        search = st.text_input("Tìm mã đặt phòng, tên khách, số điện thoại hoặc phòng")
        show = allb.copy()
        if search.strip():
            mask = show.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, na=False)).any(axis=1)
            show = show[mask]
        st.dataframe(show.drop(columns=["id"]), use_container_width=True, hide_index=True)

# -------------------------
# LỄ TÂN & LƯU TRÚ
# -------------------------
elif page == "🧾 Lễ tân & lưu trú":
    st.subheader("Nhận phòng / trả phòng / hủy")
    data = get_booking_rows("b.status IN ('Đã đặt','Đang ở')")
    if data.empty:
        st.info("Không có lượt đặt phòng đang chờ hoặc đang lưu trú.")
    else:
        opts = {f"{r['code']} · {r['guest']} · Phòng {r['room']} · {r['check_in']} → {r['check_out']} · {r['status']}": int(r.id)
                for _,r in data.iterrows()}
        selected = st.selectbox("Chọn lượt đặt phòng", list(opts))
        bid = opts[selected]
        row = data[data.id == bid].iloc[0]
        rt, extra, total, paid = booking_total(bid)
        c = st.columns(4)
        c[0].metric("Tiền phòng", money(rt))
        c[1].metric("Dịch vụ", money(extra))
        c[2].metric("Tổng hóa đơn", money(total))
        c[3].metric("Đã thanh toán", money(paid))
        st.write(f"**Còn phải thu:** {money(max(0,total-paid))}")
        c1,c2,c3 = st.columns(3)
        if row.status == "Đã đặt":
            if c1.button("🔑 Xác nhận nhận phòng", use_container_width=True):
                run("UPDATE bookings SET status='Đang ở' WHERE id=?", (bid,))
                run("UPDATE rooms SET status='Đang sử dụng' WHERE id=?", (int(read("SELECT room_id FROM bookings WHERE id=?", (bid,)).iloc[0]["room_id"]),))
                st.success("Đã nhận phòng.")
                st.rerun()
        if row.status == "Đang ở":
            if c2.button("🏁 Trả phòng", use_container_width=True):
                run("UPDATE bookings SET status='Đã trả' WHERE id=?", (bid,))
                room_id = int(read("SELECT room_id FROM bookings WHERE id=?", (bid,)).iloc[0]["room_id"])
                run("UPDATE rooms SET status='Đang dọn' WHERE id=?", (room_id,))
                run("INSERT INTO housekeeping(room_id,task,status,note) VALUES(?,?,?,?)",
                    (room_id,"Dọn phòng sau trả phòng","Chờ xử lý",f"Phòng từ booking {row['code']}"))
                st.success("Đã trả phòng. Đã tạo nhiệm vụ dọn phòng.")
                st.rerun()
        if c3.button("Hủy đặt phòng", disabled=(row.status != "Đã đặt"), use_container_width=True):
            run("UPDATE bookings SET status='Đã hủy' WHERE id=?", (bid,))
            st.success("Đã hủy đặt phòng.")
            st.rerun()
        st.markdown("#### Ghi chú lưu trú")
        note_value = st.text_area("Ghi chú", value=str(row.note or ""), key=f"note_{bid}")
        if st.button("Lưu ghi chú"):
            run("UPDATE bookings SET note=? WHERE id=?", (note_value, bid))
            st.success("Đã lưu ghi chú.")

# -------------------------
# KHÁCH HÀNG
# -------------------------
elif page == "👤 Khách hàng":
    st.subheader("Hồ sơ khách hàng")
    guests = read("""
        SELECT g.id,g.full_name AS 'Họ tên',g.phone AS 'Điện thoại',g.email AS 'Email',
               g.identity_no AS 'CCCD/Hộ chiếu',g.address AS 'Địa chỉ',
               COUNT(b.id) AS 'Số lượt đặt'
        FROM guests g LEFT JOIN bookings b ON b.guest_id=g.id
        GROUP BY g.id ORDER BY g.id DESC
    """)
    search = st.text_input("Tìm khách theo tên, số điện thoại, email hoặc giấy tờ")
    filtered = guests.copy()
    if search.strip() and not filtered.empty:
        mask = filtered.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, na=False)).any(axis=1)
        filtered = filtered[mask]
    st.dataframe(filtered.drop(columns=["id"]) if not filtered.empty else filtered,
                 use_container_width=True, hide_index=True)
    if not guests.empty:
        st.markdown("### Lịch sử đặt phòng của khách")
        gm = {f"{r['Họ tên']} — {r['Điện thoại']}": int(r.id) for _,r in guests.iterrows()}
        gl = st.selectbox("Chọn khách hàng", list(gm))
        history = read("""
            SELECT b.code AS 'Mã đặt phòng',r.number AS 'Phòng',b.check_in AS 'Ngày nhận',
                   b.check_out AS 'Ngày trả',b.status AS 'Trạng thái',b.room_price AS 'Giá/đêm'
            FROM bookings b JOIN rooms r ON r.id=b.room_id WHERE b.guest_id=? ORDER BY b.id DESC
        """, (gm[gl],))
        st.dataframe(history, use_container_width=True, hide_index=True)
    with st.expander("➕ Thêm hồ sơ khách hàng"):
        with st.form("new_guest"):
            a,b,c = st.columns(3)
            gn = a.text_input("Họ tên *")
            gp = b.text_input("Số điện thoại *")
            ge = c.text_input("Email")
            gi = st.text_input("CCCD / Hộ chiếu")
            ga = st.text_input("Địa chỉ")
            if st.form_submit_button("Lưu khách hàng"):
                if not gn.strip() or not gp.strip():
                    st.error("Họ tên và số điện thoại là bắt buộc.")
                else:
                    add_guest(gn,gp,ge,gi,ga)
                    st.success("Đã lưu hồ sơ khách.")
                    st.rerun()

# -------------------------
# DỊCH VỤ & HÓA ĐƠN
# -------------------------
elif page == "🛎️ Dịch vụ & hóa đơn":
    st.subheader("Danh mục dịch vụ")
    services = read("SELECT * FROM services ORDER BY active DESC,name")
    st.dataframe(services, use_container_width=True, hide_index=True)
    with st.expander("➕ Thêm dịch vụ"):
        with st.form("add_service"):
            a,b,c = st.columns(3)
            sn = a.text_input("Tên dịch vụ")
            sp = b.number_input("Đơn giá (đ)", min_value=0, value=20000, step=10000)
            su = c.text_input("Đơn vị", value="lần")
            if st.form_submit_button("Thêm dịch vụ"):
                if not sn.strip():
                    st.error("Nhập tên dịch vụ.")
                else:
                    try:
                        run("INSERT INTO services(name,price,unit) VALUES(?,?,?)", (sn.strip(),sp,su.strip() or "lần"))
                        st.success("Đã thêm dịch vụ.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Tên dịch vụ đã tồn tại.")
    if not services.empty:
        with st.expander("Sửa giá / bật tắt dịch vụ"):
            smap = {f"{r['name']} — {money(r['price'])}/{r['unit']}": int(r.id) for _,r in services.iterrows()}
            sl = st.selectbox("Chọn dịch vụ", list(smap))
            sid = smap[sl]
            sr = services[services.id == sid].iloc[0]
            with st.form("edit_service"):
                sp2 = st.number_input("Giá mới", min_value=0, value=int(sr.price), step=10000)
                su2 = st.text_input("Đơn vị", str(sr.unit))
                active2 = st.checkbox("Đang kinh doanh", value=bool(sr.active))
                if st.form_submit_button("Lưu dịch vụ"):
                    run("UPDATE services SET price=?,unit=?,active=? WHERE id=?", (sp2,su2,int(active2),sid))
                    st.success("Đã cập nhật.")
                    st.rerun()
    st.divider()
    st.subheader("Ghi nhận dịch vụ cho khách")
    live = get_booking_rows("b.status='Đang ở'")
    if live.empty:
        st.info("Chưa có khách đang lưu trú để ghi nhận dịch vụ.")
    elif services[services.active == 1].empty:
        st.info("Chưa có dịch vụ đang hoạt động.")
    else:
        bmap = {f"{r['code']} — {r['guest']} — phòng {r['room']}": int(r.id) for _,r in live.iterrows()}
        bl = st.selectbox("Chọn lượt lưu trú", list(bmap))
        bid = bmap[bl]
        active_services = services[services.active == 1]
        svmap = {f"{r['name']} · {money(r['price'])}/{r['unit']}": int(r.id) for _,r in active_services.iterrows()}
        with st.form("add_order"):
            svlabel = st.selectbox("Dịch vụ", list(svmap))
            qty = st.number_input("Số lượng", min_value=0.1, value=1.0, step=1.0)
            snote = st.text_input("Ghi chú")
            if st.form_submit_button("Ghi nhận dịch vụ"):
                sr = active_services[active_services.id == svmap[svlabel]].iloc[0]
                run("INSERT INTO service_orders(booking_id,service_id,quantity,unit_price,note) VALUES(?,?,?,?,?)",
                    (bid,int(sr.id),qty,float(sr.price),snote.strip()))
                st.success("Đã ghi nhận dịch vụ.")
                st.rerun()
    st.divider()
    st.subheader("Hóa đơn và thanh toán")
    bdata = get_booking_rows()
    if bdata.empty:
        st.info("Chưa có đặt phòng.")
    else:
        bmap2 = {f"{r['code']} — {r['guest']} — phòng {r['room']}": int(r.id) for _,r in bdata.iterrows()}
        bl2 = st.selectbox("Chọn đặt phòng để xem hóa đơn", list(bmap2), key="invoice_booking")
        bid2 = bmap2[bl2]
        br = bdata[bdata.id == bid2].iloc[0]
        rt, ex, total, paid = booking_total(bid2)
        st.markdown(f"### HÓA ĐƠN · {br['code']}")
        st.write(f"**Khách:** {br['guest']} · **Phòng:** {br['room']} · **Thời gian:** {br['check_in']} → {br['check_out']}")
        invoice_df = pd.DataFrame([
            {"Khoản": f"Tiền phòng ({nights(br['check_in'],br['check_out'])} đêm)", "Thành tiền": rt},
            {"Khoản": "Dịch vụ", "Thành tiền": ex},
            {"Khoản": "Giảm giá", "Thành tiền": -float(br["discount"] or 0)},
            {"Khoản": "TỔNG CỘNG", "Thành tiền": total},
            {"Khoản": "ĐÃ THANH TOÁN", "Thành tiền": paid},
            {"Khoản": "CÒN PHẢI THU", "Thành tiền": max(0,total-paid)},
        ])
        st.dataframe(invoice_df, use_container_width=True, hide_index=True)
        orders = read("""SELECT s.name AS 'Dịch vụ',o.quantity AS 'Số lượng',s.unit AS 'Đơn vị',
                         o.unit_price AS 'Đơn giá',o.quantity*o.unit_price AS 'Thành tiền',o.ordered_at AS 'Thời gian'
                         FROM service_orders o JOIN services s ON s.id=o.service_id WHERE o.booking_id=? ORDER BY o.id DESC""", (bid2,))
        if not orders.empty:
            st.markdown("**Chi tiết dịch vụ**")
            st.dataframe(orders, use_container_width=True, hide_index=True)
        payments = read("SELECT amount AS 'Số tiền',method AS 'Phương thức',note AS 'Ghi chú',paid_at AS 'Thời gian' FROM payments WHERE booking_id=? ORDER BY id DESC", (bid2,))
        if not payments.empty:
            st.markdown("**Lịch sử thanh toán**")
            st.dataframe(payments, use_container_width=True, hide_index=True)
        with st.expander("💳 Ghi nhận thanh toán"):
            with st.form("payment_form"):
                amount = st.number_input("Số tiền thanh toán (đ)", min_value=1000, value=max(1000,int(max(0,total-paid))), step=10000)
                method = st.selectbox("Phương thức", ["Tiền mặt","Chuyển khoản","Thẻ","Ví điện tử"])
                pnote = st.text_input("Ghi chú thanh toán")
                if st.form_submit_button("Ghi nhận thanh toán"):
                    run("INSERT INTO payments(booking_id,amount,method,note) VALUES(?,?,?,?)",
                        (bid2,amount,method,pnote.strip()))
                    st.success("Đã ghi nhận thanh toán.")
                    st.rerun()
        csv = invoice_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Tải bảng hóa đơn CSV", data=csv, file_name=f"hoa_don_{br['code']}.csv", mime="text/csv")

# -------------------------
# BUỒNG PHÒNG
# -------------------------
elif page == "🧹 Buồng phòng":
    st.subheader("Theo dõi công việc dọn phòng")
    tasks = read("""
        SELECT h.id,r.number AS 'Phòng',h.task AS 'Công việc',h.staff AS 'Nhân viên',
               h.status AS 'Trạng thái',h.note AS 'Ghi chú',h.created_at AS 'Tạo lúc'
        FROM housekeeping h JOIN rooms r ON r.id=h.room_id ORDER BY h.id DESC
    """)
    if tasks.empty:
        st.info("Chưa có nhiệm vụ dọn phòng.")
    else:
        st.dataframe(tasks, use_container_width=True, hide_index=True)
        task_map = {f"#{r['id']} · Phòng {r['Phòng']} · {r['Công việc']} · {r['Trạng thái']}": int(r.id) for _,r in tasks.iterrows()}
        tl = st.selectbox("Chọn nhiệm vụ cần cập nhật", list(task_map))
        tid = task_map[tl]
        tr = tasks[tasks.id == tid].iloc[0]
        with st.form("update_task"):
            staff = st.text_input("Nhân viên phụ trách", str(tr["Nhân viên"] or ""))
            task_status = st.selectbox("Trạng thái", ["Chờ xử lý","Đang thực hiện","Hoàn thành"],
                                       index=["Chờ xử lý","Đang thực hiện","Hoàn thành"].index(tr["Trạng thái"]) if tr["Trạng thái"] in ["Chờ xử lý","Đang thực hiện","Hoàn thành"] else 0)
            task_note = st.text_input("Ghi chú", str(tr["Ghi chú"] or ""))
            if st.form_submit_button("Cập nhật nhiệm vụ"):
                run("UPDATE housekeeping SET staff=?,status=?,note=?,completed_at=? WHERE id=?",
                    (staff,task_status,task_note,datetime.now().isoformat(timespec="seconds") if task_status=="Hoàn thành" else "",tid))
                if task_status == "Hoàn thành":
                    room_no = str(tr["Phòng"])
                    run("UPDATE rooms SET status='Trống' WHERE number=? AND status='Đang dọn'", (room_no,))
                st.success("Đã cập nhật nhiệm vụ.")
                st.rerun()
    st.divider()
    st.subheader("Tạo nhiệm vụ mới")
    room_df = read("SELECT id,number FROM rooms ORDER BY number")
    if room_df.empty:
        st.info("Chưa có phòng.")
    else:
        with st.form("new_task"):
            rmap = {f"Phòng {r['number']}": int(r.id) for _,r in room_df.iterrows()}
            rl = st.selectbox("Phòng", list(rmap))
            task_name = st.selectbox("Công việc", ["Dọn phòng","Kiểm tra minibar","Bảo trì","Kiểm tra thiết bị","Thay khăn / ga","Khác"])
            staff_name = st.text_input("Nhân viên")
            task_note = st.text_input("Ghi chú")
            if st.form_submit_button("Tạo nhiệm vụ"):
                rid = rmap[rl]
                run("INSERT INTO housekeeping(room_id,task,staff,status,note) VALUES(?,?,?,'Chờ xử lý',?)",
                    (rid,task_name,staff_name,task_note))
                if task_name == "Dọn phòng":
                    run("UPDATE rooms SET status='Đang dọn' WHERE id=? AND status!='Đang sử dụng'", (rid,))
                st.success("Đã tạo nhiệm vụ.")
                st.rerun()

# -------------------------
# BÁO CÁO
# -------------------------
elif page == "📈 Báo cáo":
    st.subheader("Báo cáo doanh thu & công suất")
    c1,c2 = st.columns(2)
    start = c1.date_input("Từ ngày", value=date.today().replace(day=1), key="report_start")
    end = c2.date_input("Đến ngày", value=date.today(), key="report_end")
    if end < start:
        st.error("Ngày kết thúc phải từ ngày bắt đầu trở đi.")
    else:
        payments = read("SELECT date(paid_at) AS ngay, SUM(amount) AS doanh_thu FROM payments WHERE date(paid_at) BETWEEN ? AND ? GROUP BY date(paid_at) ORDER BY ngay",
                        (start.isoformat(),end.isoformat()))
        total_rev = float(payments["doanh_thu"].sum()) if not payments.empty else 0
        st.metric("Doanh thu thu trong kỳ", money(total_rev))
        if payments.empty:
            st.info("Không có khoản thanh toán trong khoảng thời gian đã chọn.")
        else:
            st.line_chart(payments.set_index("ngay")["doanh_thu"])
            st.dataframe(payments, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Tải báo cáo doanh thu CSV",
                               data=payments.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"bao_cao_{start}_{end}.csv", mime="text/csv")
        st.markdown("### Thống kê đặt phòng theo trạng thái")
        stats = read("SELECT status AS 'Trạng thái', COUNT(*) AS 'Số lượt' FROM bookings WHERE date(created_at) BETWEEN ? AND ? GROUP BY status",
                     (start.isoformat(),end.isoformat()))
        if stats.empty:
            st.info("Không có đặt phòng được tạo trong kỳ.")
        else:
            st.dataframe(stats, use_container_width=True, hide_index=True)
        st.markdown("### Công suất phòng theo ngày nhận")
        occ = read("""SELECT check_in AS 'Ngày nhận',COUNT(*) AS 'Số lượt'
                      FROM bookings WHERE status IN ('Đã đặt','Đang ở','Đã trả')
                      AND check_in BETWEEN ? AND ? GROUP BY check_in ORDER BY check_in""",
                   (start.isoformat(),end.isoformat()))
        if not occ.empty:
            st.bar_chart(occ.set_index("Ngày nhận"))
        else:
            st.info("Không có dữ liệu lưu trú trong kỳ.")

# -------------------------
# CÀI ĐẶT / SAO LƯU
# -------------------------
elif page == "⚙️ Cài đặt":
    st.subheader("Cài đặt & sao lưu dữ liệu")
    st.info(f"Tệp cơ sở dữ liệu hiện tại: {DB_PATH}")
    st.markdown("### Xuất dữ liệu")
    tables = ["rooms","guests","bookings","services","service_orders","payments","housekeeping"]
    for table in tables:
        df = read(f"SELECT * FROM {table}")
        st.download_button(f"⬇️ Xuất {table}.csv", data=df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{table}.csv", mime="text/csv", key=f"export_{table}")
    st.markdown("### Sao lưu cơ sở dữ liệu")
    try:
        db_bytes = DB_PATH.read_bytes()
        st.download_button("⬇️ Tải bản sao lưu hotel.db", data=db_bytes, file_name=f"hotel_backup_{date.today().isoformat()}.db",
                           mime="application/octet-stream")
    except OSError:
        st.warning("Chưa tìm thấy tệp cơ sở dữ liệu.")
    st.warning("Không xóa hoặc chỉnh sửa trực tiếp hotel.db khi ứng dụng đang chạy. Hãy tải bản sao lưu trước khi thay đổi dữ liệu.")

