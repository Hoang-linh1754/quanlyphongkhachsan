
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# =========================================================
# 1. CẤU HÌNH
# =========================================================

st.set_page_config(
    page_title="Hotel Booking",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_NAME = "hotel.db"

STATUSES = [
    "Chờ xác nhận",
    "Đã xác nhận",
    "Đã hủy",
    "Đã từ chối",
    "Đã hoàn tất",
]

ROOM_STATUSES = ["Trống", "Có khách", "Đang dọn", "Bảo trì"]

ROOM_COLORS = {
    "Trống": "#16a34a",
    "Có khách": "#2563eb",
    "Đang dọn": "#d97706",
    "Bảo trì": "#dc2626",
}

STAFF_PASSWORD = os.getenv("STAFF_PASSWORD", "123456")


# =========================================================
# 2. DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT UNIQUE NOT NULL,
            room_type TEXT NOT NULL,
            floor INTEGER NOT NULL DEFAULT 1,
            capacity INTEGER NOT NULL DEFAULT 2,
            price REAL NOT NULL DEFAULT 0,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Trống',
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT DEFAULT '',
            room_id INTEGER NOT NULL,
            checkin TEXT NOT NULL,
            checkout TEXT NOT NULL,
            guests INTEGER NOT NULL,
            nights INTEGER NOT NULL,
            total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Chờ xác nhận',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            sender TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (code) REFERENCES bookings(code)
        )
    """)

    # Tạo dữ liệu phòng mẫu nếu database chưa có phòng.
    count = conn.execute(
        "SELECT COUNT(*) FROM rooms"
    ).fetchone()[0]

    if count == 0:
        sample_rooms = [
            ("101", "Phòng đơn", 1, 1, 350000,
             "Phòng đơn tiện nghi dành cho 1 khách.", "Trống"),
            ("102", "Phòng đôi", 1, 2, 500000,
             "Phòng đôi rộng rãi dành cho 2 khách.", "Có khách"),
            ("103", "Phòng VIP", 1, 2, 900000,
             "Phòng VIP tiện nghi cao cấp.", "Đang dọn"),
            ("201", "Phòng gia đình", 2, 4, 1200000,
             "Phòng gia đình phù hợp tối đa 4 khách.", "Trống"),
            ("202", "Phòng Deluxe", 2, 2, 750000,
             "Phòng Deluxe có không gian thoải mái.", "Có khách"),
            ("203", "Phòng đôi", 2, 2, 550000,
             "Phòng đôi đang được bảo trì.", "Bảo trì"),
        ]

        conn.executemany("""
            INSERT INTO rooms (
                room_number, room_type, floor, capacity,
                price, description, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_rooms)

    conn.commit()
    conn.close()


def get_rooms():
    conn = db()
    data = pd.read_sql_query("""
        SELECT *
        FROM rooms
        WHERE active = 1
        ORDER BY floor, room_number
    """, conn)
    conn.close()
    return data


def get_bookings():
    conn = db()
    data = pd.read_sql_query("""
        SELECT
            b.*,
            r.room_number,
            r.room_type,
            r.floor,
            r.capacity,
            r.price
        FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        ORDER BY b.created_at DESC
    """, conn)
    conn.close()
    return data


def get_booking(code):
    conn = db()
    row = conn.execute("""
        SELECT b.*, r.room_number, r.room_type, r.floor, r.price
        FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        WHERE b.code = ?
    """, (code.strip().upper(),)).fetchone()
    conn.close()
    return row


# =========================================================
# 3. KIỂM TRA PHÒNG TRỐNG THEO NGÀY
# =========================================================

def find_available_rooms(checkin, checkout, guests):
    """
    Phòng được xem là đã có lịch đặt nếu có đơn đang chờ
    xác nhận hoặc đã xác nhận bị trùng thời gian lưu trú.
    """

    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM rooms
        WHERE active = 1
          AND status != 'Bảo trì'
          AND capacity >= ?
          AND id NOT IN (
              SELECT room_id
              FROM bookings
              WHERE status IN ('Chờ xác nhận', 'Đã xác nhận')
                AND checkin < ?
                AND checkout > ?
          )
        ORDER BY price ASC
    """, (
        guests,
        checkout.isoformat(),
        checkin.isoformat(),
    )).fetchall()

    conn.close()
    return rows


# =========================================================
# 4. TẠO ĐẶT PHÒNG
# =========================================================

def create_booking(
    customer_name, phone, email, room_id,
    checkin, checkout, guests, note
):
    if checkout <= checkin:
        return False, "Ngày trả phòng phải sau ngày nhận phòng."

    nights = (checkout - checkin).days
    conn = db()

    try:
        conn.execute("BEGIN IMMEDIATE")

        room = conn.execute("""
            SELECT *
            FROM rooms
            WHERE id = ? AND active = 1
        """, (room_id,)).fetchone()

        if room is None:
            conn.rollback()
            return False, "Phòng không tồn tại."

        if room["status"] == "Bảo trì":
            conn.rollback()
            return False, "Phòng đang bảo trì."

        if guests > room["capacity"]:
            conn.rollback()
            return False, "Số khách vượt quá sức chứa của phòng."

        overlap = conn.execute("""
            SELECT COUNT(*)
            FROM bookings
            WHERE room_id = ?
              AND status IN ('Chờ xác nhận', 'Đã xác nhận')
              AND checkin < ?
              AND checkout > ?
        """, (
            room_id,
            checkout.isoformat(),
            checkin.isoformat(),
        )).fetchone()[0]

        if overlap:
            conn.rollback()
            return False, "Phòng đã được đặt trong khoảng ngày này."

        code = (
            "BK" + datetime.now().strftime("%y%m%d")
            + uuid.uuid4().hex[:6].upper()
        )

        total = float(room["price"]) * nights

        conn.execute("""
            INSERT INTO bookings (
                code, customer_name, phone, email,
                room_id, checkin, checkout, guests,
                nights, total, status, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            code, customer_name.strip(), phone.strip(),
            email.strip(), room_id, checkin.isoformat(),
            checkout.isoformat(), guests, nights, total,
            "Chờ xác nhận", note.strip(),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))

        conn.commit()
        return True, code

    except Exception as e:
        conn.rollback()
        return False, f"Lỗi tạo đặt phòng: {e}"

    finally:
        conn.close()


# =========================================================
# 5. CẬP NHẬT TRẠNG THÁI ĐƠN
# =========================================================

def update_booking_status(code, new_status):
    if new_status not in STATUSES:
        return False, "Trạng thái không hợp lệ."

    conn = db()

    try:
        conn.execute("BEGIN IMMEDIATE")

        booking = conn.execute(
            "SELECT * FROM bookings WHERE code = ?",
            (code,),
        ).fetchone()

        if booking is None:
            conn.rollback()
            return False, "Không tìm thấy đơn đặt phòng."

        if new_status == "Đã xác nhận":
            overlap = conn.execute("""
                SELECT COUNT(*)
                FROM bookings
                WHERE room_id = ?
                  AND code != ?
                  AND status IN ('Chờ xác nhận', 'Đã xác nhận')
                  AND checkin < ?
                  AND checkout > ?
            """, (
                booking["room_id"],
                code,
                booking["checkout"],
                booking["checkin"],
            )).fetchone()[0]

            if overlap:
                conn.rollback()
                return False, "Phòng đã có đơn trùng ngày."

        conn.execute("""
            UPDATE bookings
            SET status = ?
            WHERE code = ?
        """, (new_status, code))

        conn.commit()
        return True, "Cập nhật trạng thái thành công."

    except Exception as e:
        conn.rollback()
        return False, str(e)

    finally:
        conn.close()


# =========================================================
# 6. CHAT KHÁCH HÀNG VÀ NHÂN VIÊN
# =========================================================

def get_messages(code):
    conn = db()
    rows = conn.execute("""
        SELECT *
        FROM messages
        WHERE code = ?
        ORDER BY id ASC
    """, (code.strip().upper(),)).fetchall()
    conn.close()
    return rows


def save_message(code, sender, sender_name, message):
    message = message.strip()

    if not message:
        return False

    conn = db()

    exists = conn.execute(
        "SELECT 1 FROM bookings WHERE code = ?",
        (code.strip().upper(),),
    ).fetchone()

    if not exists:
        conn.close()
        return False

    conn.execute("""
        INSERT INTO messages (
            code, sender, sender_name, message, created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        code.strip().upper(),
        sender,
        sender_name,
        message,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ))

    conn.commit()
    conn.close()
    return True


def chat_interface(code, sender, sender_name):
    st.subheader("💬 Tin nhắn")

    messages = get_messages(code)

    if not messages:
        st.info("Chưa có tin nhắn. Hãy gửi lời nhắn đầu tiên.")

    for msg in messages:
        role = "assistant" if msg["sender"] != sender else "user"

        with st.chat_message(role):
            st.caption(
                f"{msg['sender_name']} · {msg['created_at']}"
            )
            st.markdown(msg["message"])

    with st.form(f"chat_{sender}_{code}", clear_on_submit=True):
        message = st.text_input(
            "Nội dung tin nhắn",
            placeholder="Nhập tin nhắn...",
        )
        submitted = st.form_submit_button(
            "📨 Gửi tin nhắn",
            use_container_width=True,
        )

        if submitted:
            if save_message(code, sender, sender_name, message):
                st.rerun()
            else:
                st.error("Không gửi được tin nhắn.")


# =========================================================
# 7. CHATBOX AI
# =========================================================

def get_api_key():
    try:
        key = st.secrets.get("OPENAI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass

    return os.getenv("OPENAI_API_KEY", "")


def get_ai_client():
    key = get_api_key()

    if not key or OpenAI is None:
        return None

    try:
        return OpenAI(api_key=key)
    except Exception:
        return None


def ai_answer(question):
    rooms = get_rooms()

    if rooms.empty:
        context = "Khách sạn chưa có dữ liệu phòng."
    else:
        context = "\n".join([
            f"Phòng {r['room_number']}: {r['room_type']}; "
            f"sức chứa {r['capacity']} người; "
            f"giá {r['price']:,.0f} VNĐ/đêm; "
            f"trạng thái hiện tại: {r['status']}; "
            f"{r['description']}"
            for _, r in rooms.iterrows()
        ])

    client = get_ai_client()

    if client is None:
        q = question.lower()

        if any(w in q for w in ["giá", "phòng", "loại phòng"]):
            return (
                "Thông tin phòng hiện có:\n\n"
                + context
                + "\n\nĐể kiểm tra phòng trống theo ngày, "
                "vui lòng vào mục Đặt phòng."
            )

        return (
            "Xin chào! Tôi là trợ lý khách sạn. "
            "Bạn có thể hỏi về loại phòng, giá phòng hoặc "
            "cách đặt phòng. Đây là chế độ minh họa chưa kết nối AI."
        )

    system_prompt = f"""
Bạn là trợ lý chăm sóc khách hàng khách sạn.
Trả lời bằng tiếng Việt, lịch sự, ngắn gọn.
Chỉ sử dụng dữ liệu bên dưới để tư vấn loại phòng và giá.
Không tự xác nhận đặt phòng hoặc cam kết phòng còn trống.
Hướng dẫn khách vào mục Đặt phòng để kiểm tra ngày cụ thể.
Không bịa thông tin.

DỮ LIỆU PHÒNG:
{context}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content or "AI chưa có câu trả lời."

    except Exception:
        return (
            "Không thể kết nối AI lúc này. "
            "Vui lòng thử lại hoặc liên hệ nhân viên."
        )


# =========================================================
# 8. HÀM HIỂN THỊ
# =========================================================

def money(value):
    return f"{float(value):,.0f} VNĐ".replace(",", ".")


def show_booking(booking):
    st.markdown(f"### 🧾 Mã đặt phòng: {booking['code']}")

    c1, c2 = st.columns(2)

    with c1:
        st.write(f"**Khách hàng:** {booking['customer_name']}")
        st.write(f"**Điện thoại:** {booking['phone']}")
        st.write(f"**Phòng:** {booking['room_number']} - {booking['room_type']}")

    with c2:
        st.write(f"**Nhận phòng:** {booking['checkin']}")
        st.write(f"**Trả phòng:** {booking['checkout']}")
        st.write(f"**Số đêm:** {booking['nights']}")
        st.write(f"**Số khách:** {booking['guests']}")

    st.write(f"**Tổng tiền:** {money(booking['total'])}")
    st.write(f"**Trạng thái:** {booking['status']}")


# =========================================================
# 9. KHỞI TẠO
# =========================================================

init_db()

if "staff_logged_in" not in st.session_state:
    st.session_state.staff_logged_in = False

if "customer_chat_code" not in st.session_state:
    st.session_state.customer_chat_code = ""

if "ai_history" not in st.session_state:
    st.session_state.ai_history = []


# =========================================================
# 10. MENU
# =========================================================

with st.sidebar:
    st.title("🏨 HOTEL BOOKING")

    page = st.radio(
        "MENU CHÍNH",
        [
            "🏠 Trang chủ",
            "🗺️ Sơ đồ phòng",
            "🛏️ Đặt phòng",
            "🔎 Tra cứu đặt phòng",
            "💬 Chat với nhân viên",
            "🤖 Chatbox AI",
            "👨‍💼 Quản lý nhân viên",
        ],
    )

    st.divider()
    st.caption("Hệ thống đặt phòng khách sạn")


# =========================================================
# 11. TRANG CHỦ
# =========================================================

if page == "🏠 Trang chủ":
    st.title("🏨 Chào mừng đến với khách sạn")

    st.write(
        "Đặt phòng trực tuyến, xem sơ đồ phòng và trò chuyện "
        "với nhân viên hoặc trợ lý AI."
    )

    rooms = get_rooms()

    c1, c2, c3 = st.columns(3)
    c1.metric("Tổng số phòng", len(rooms))
    c2.metric(
        "Phòng trống",
        int((rooms["status"] == "Trống").sum()) if not rooms.empty else 0,
    )
    c3.metric(
        "Phòng có khách",
        int((rooms["status"] == "Có khách").sum()) if not rooms.empty else 0,
    )

    st.divider()
    st.subheader("🛏️ Phòng khách sạn")

    cols = st.columns(3)

    for i, (_, room) in enumerate(rooms.iterrows()):
        with cols[i % 3]:
            with st.container(border=True):
                st.subheader(f"Phòng {room['room_number']}")
                st.write(f"**{room['room_type']}**")
                st.write(f"Sức chứa: {room['capacity']} người")
                st.write(f"Giá: **{money(room['price'])}/đêm**")
                st.write(f"Trạng thái: **{room['status']}**")
                st.caption(room["description"])


# =========================================================
# 12. SƠ ĐỒ PHÒNG
# =========================================================

elif page == "🗺️ Sơ đồ phòng":
    st.title("🗺️ Sơ đồ phòng khách sạn")

    st.markdown(
        "🟢 Trống　🔵 Có khách　🟠 Đang dọn　🔴 Bảo trì"
    )

    rooms = get_rooms()

    if rooms.empty:
        st.info("Chưa có phòng.")
    else:
        floors = sorted(rooms["floor"].unique())

        for floor in floors:
            st.subheader(f"🏢 Tầng {floor}")
            floor_rooms = rooms[rooms["floor"] == floor]
            cols = st.columns(4)

            for i, (_, room) in enumerate(floor_rooms.iterrows()):
                color = ROOM_COLORS.get(room["status"], "#64748b")

                with cols[i % 4]:
                    st.markdown(
                        f"""
                        <div style="
                            border:1px solid #e2e8f0;
                            border-top:6px solid {color};
                            border-radius:12px;
                            padding:16px;
                            margin-bottom:12px;
                            background:#ffffff;
                            color:#0f172a;
                        ">
                            <h2 style="margin:0">🚪 {room['room_number']}</h2>
                            <b>{room['room_type']}</b>
                            <p style="color:{color};font-weight:bold">
                                {room['status']}
                            </p>
                            <p>Sức chứa: {room['capacity']} người</p>
                            <p>Giá: {money(room['price'])}/đêm</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )


# =========================================================
# 13. ĐẶT PHÒNG
# =========================================================

elif page == "🛏️ Đặt phòng":
    st.title("🛏️ Đặt phòng khách sạn")

    with st.form("booking_form"):
        st.subheader("Thông tin lưu trú")

        c1, c2 = st.columns(2)

        with c1:
            checkin = st.date_input(
                "Ngày nhận phòng",
                value=date.today() + timedelta(days=1),
                min_value=date.today(),
            )

        with c2:
            checkout = st.date_input(
                "Ngày trả phòng",
                value=date.today() + timedelta(days=2),
                min_value=date.today() + timedelta(days=1),
            )

        guests = st.number_input(
            "Số khách",
            min_value=1,
            max_value=20,
            value=2,
        )

        st.subheader("Thông tin khách hàng")

        customer_name = st.text_input("Họ và tên *")
        phone = st.text_input("Số điện thoại *")
        email = st.text_input("Email")
        note = st.text_area("Yêu cầu đặc biệt")

        submitted = st.form_submit_button(
            "🔍 Tìm phòng phù hợp",
            use_container_width=True,
        )

    if submitted:
        if not customer_name.strip() or not phone.strip():
            st.error("Vui lòng nhập họ tên và số điện thoại.")
        elif checkout <= checkin:
            st.error("Ngày trả phòng phải sau ngày nhận phòng.")
        else:
            rooms_available = find_available_rooms(
                checkin, checkout, int(guests)
            )

            if not rooms_available:
                st.warning(
                    "Không có phòng phù hợp trong khoảng ngày đã chọn."
                )
            else:
                st.success(f"Tìm thấy {len(rooms_available)} phòng.")

                options = {
                    (
                        f"Phòng {r['room_number']} - {r['room_type']} | "
                        f"{money(r['price'])}/đêm | "
                        f"Tối đa {r['capacity']} khách"
                    ): r
                    for r in rooms_available
                }

                selected_label = st.selectbox(
                    "Chọn phòng",
                    list(options.keys()),
                )

                selected_room = options[selected_label]
                nights = (checkout - checkin).days
                total = selected_room["price"] * nights

                st.markdown(f"### Tổng tiền dự kiến: {money(total)}")
                st.caption(
                    f"{nights} đêm × {money(selected_room['price'])}/đêm"
                )

                if st.button(
                    "✅ Gửi yêu cầu đặt phòng",
                    type="primary",
                    use_container_width=True,
                ):
                    ok, result = create_booking(
                        customer_name,
                        phone,
                        email,
                        selected_room["id"],
                        checkin,
                        checkout,
                        int(guests),
                        note,
                    )

                    if ok:
                        st.success("Đặt phòng thành công!")
                        st.markdown(f"## Mã đặt phòng: `{result}`")
                        st.info(
                            "Đơn đang chờ nhân viên xác nhận. "
                            "Hãy lưu mã để tra cứu và trò chuyện."
                        )
                    else:
                        st.error(result)


# =========================================================
# 14. TRA CỨU ĐẶT PHÒNG
# =========================================================

elif page == "🔎 Tra cứu đặt phòng":
    st.title("🔎 Tra cứu đặt phòng")

    code = st.text_input("Nhập mã đặt phòng")

    if st.button("Tra cứu", use_container_width=True):
        booking = get_booking(code)

        if booking:
            show_booking(booking)
        else:
            st.error("Không tìm thấy đơn đặt phòng.")


# =========================================================
# 15. CHAT VỚI NHÂN VIÊN
# =========================================================

elif page == "💬 Chat với nhân viên":
    st.title("💬 Chat với nhân viên")

    code = st.text_input(
        "Mã đặt phòng",
        value=st.session_state.customer_chat_code,
    )

    if st.button("Mở cuộc trò chuyện"):
        booking = get_booking(code)

        if booking:
            st.session_state.customer_chat_code = code.strip().upper()
            st.rerun()
        else:
            st.error("Mã đặt phòng không hợp lệ.")

    code = st.session_state.customer_chat_code

    if code:
        booking = get_booking(code)

        if booking:
            st.success(
                f"Đơn {code} · Phòng {booking['room_number']}"
            )

            chat_interface(
                code,
                sender="customer",
                sender_name=booking["customer_name"],
            )


# =========================================================
# 16. CHATBOX AI
# =========================================================

elif page == "🤖 Chatbox AI":
    st.title("🤖 Trợ lý AI khách sạn")

    st.caption(
        "Hỏi về loại phòng, giá phòng, sức chứa và cách đặt phòng."
    )

    if get_api_key() and OpenAI is not None:
        st.success("Đã cấu hình OpenAI API.")
    else:
        st.info("Đang chạy chế độ minh họa.")

    for item in st.session_state.ai_history:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    prompt = st.chat_input("Nhập câu hỏi của bạn...")

    if prompt:
        st.session_state.ai_history.append({
            "role": "user",
            "content": prompt,
        })

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("AI đang trả lời..."):
                answer = ai_answer(prompt)
            st.markdown(answer)

        st.session_state.ai_history.append({
            "role": "assistant",
            "content": answer,
        })

    if st.session_state.ai_history:
        if st.button("🧹 Xóa lịch sử trò chuyện AI"):
            st.session_state.ai_history = []
            st.rerun()


# =========================================================
# 17. QUẢN LÝ NHÂN VIÊN
# =========================================================

elif page == "👨‍💼 Quản lý nhân viên":
    st.title("👨‍💼 Khu vực nhân viên")

    if not st.session_state.staff_logged_in:
        st.warning("Vui lòng đăng nhập.")

        with st.form("staff_login"):
            password = st.text_input("Mật khẩu", type="password")
            login = st.form_submit_button("Đăng nhập")

            if login:
                if password == STAFF_PASSWORD:
                    st.session_state.staff_logged_in = True
                    st.rerun()
                else:
                    st.error("Mật khẩu không đúng.")

    else:
        if st.button("Đăng xuất"):
            st.session_state.staff_logged_in = False
            st.rerun()

        bookings = get_bookings()

        c1, c2, c3 = st.columns(3)

        c1.metric("Tổng đơn", len(bookings))
        c2.metric(
            "Chờ xác nhận",
            int((bookings["status"] == "Chờ xác nhận").sum())
            if not bookings.empty else 0,
        )
        c3.metric(
            "Đã xác nhận",
            int((bookings["status"] == "Đã xác nhận").sum())
            if not bookings.empty else 0,
        )

        st.subheader("📋 Danh sách đặt phòng")

        if bookings.empty:
            st.info("Chưa có đơn đặt phòng.")
        else:
            st.dataframe(
                bookings[[
                    "code", "customer_name", "phone",
                    "room_number", "room_type", "checkin",
                    "checkout", "guests", "total", "status",
                ]].rename(columns={
                    "code": "Mã đơn",
                    "customer_name": "Khách hàng",
                    "phone": "Điện thoại",
                    "room_number": "Phòng",
                    "room_type": "Loại phòng",
                    "checkin": "Ngày nhận",
                    "checkout": "Ngày trả",
                    "guests": "Số khách",
                    "total": "Tổng tiền",
                    "status": "Trạng thái",
                }),
                use_container_width=True,
                hide_index=True,
            )

            st.divider()
            st.subheader("🔄 Xử lý đơn đặt phòng")

            booking_options = {
                (
                    f"{r['code']} | Phòng {r['room_number']} | "
                    f"{r['customer_name']} | {r['status']}"
                ): r["code"]
                for _, r in bookings.iterrows()
            }

            selected_label = st.selectbox(
                "Chọn đơn",
                list(booking_options.keys()),
            )

            selected_code = booking_options[selected_label]
            booking = get_booking(selected_code)

            show_booking(booking)

            new_status = st.selectbox(
                "Trạng thái mới",
                STATUSES,
                index=STATUSES.index(booking["status"]),
            )

            if st.button("💾 Cập nhật trạng thái"):
                ok, message = update_booking_status(
                    selected_code, new_status
                )

                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

            st.divider()

            st.subheader("💬 Trao đổi với khách hàng")

            chat_interface(
                selected_code,
                sender="staff",
                sender_name="Nhân viên",
            )


# =========================================================
# 18. CHÂN TRANG
# =========================================================

st.divider()
st.caption(
    "Hotel Booking | Đặt phòng khách sạn, sơ đồ phòng, "
    "Chatbox AI và hỗ trợ khách hàng"
)
