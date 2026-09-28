
import os
from datetime import date, timedelta

import streamlit as st
import pandas as pd
import pymysql
from pymysql.cursors import DictCursor


# ============================================================
# 1. CẤU HÌNH KẾT NỐI MYSQL AIVEN
# ============================================================

st.set_page_config(
    page_title="Quản lý khách sạn",
    page_icon="🏨",
    layout="wide"
)

# Ưu tiên đọc thông tin từ Streamlit secrets,
# nếu không có thì đọc từ biến môi trường.

def get_config(key, default=""):
    try:
        value = st.secrets.get("mysql", {}).get(key)
        if value is not None:
            return value
    except Exception:
        pass

    return os.getenv(f"MYSQL_{key.upper()}", default)


DB_HOST = get_config("host", "mysql-329fe7e0-lh4016070-84b1.i.aivencloud.com")
DB_PORT = int(get_config("port", "21288"))
DB_USER = get_config("user", "avnadmin")
DB_PASSWORD = get_config("password", "AVNS_toNVDSjUweTtgkbREej")
DB_NAME = get_config("database", "defaultdb")
DB_SSL_CA = get_config("ssl_ca", "")


# ============================================================
# 2. KẾT NỐI DATABASE
# ============================================================

def connect():
    if (
        not DB_HOST
        or DB_HOST == "YOUR_AIVEN_HOST"
        or not DB_USER
        or DB_USER == "YOUR_AIVEN_USER"
        or not DB_PASSWORD
        or DB_PASSWORD == "YOUR_AIVEN_PASSWORD"
    ):
        raise ValueError(
            "Chưa cấu hình tài khoản MySQL Aiven. "
            "Vui lòng kiểm tra file .streamlit/secrets.toml."
        )

    ssl_config = {"ca": DB_SSL_CA} if DB_SSL_CA else {}

    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=15,
        ssl=ssl_config
    )


# ============================================================
# 3. KHỞI TẠO CÁC BẢNG MYSQL
# ============================================================

def init_db():
    conn = connect()

    try:
        with conn.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    room_number VARCHAR(50) NOT NULL UNIQUE,
                    room_type VARCHAR(100) NOT NULL,
                    price DECIMAL(15,2) NOT NULL DEFAULT 0,
                    status VARCHAR(50) NOT NULL DEFAULT 'Trống'
                ) ENGINE=InnoDB
                  DEFAULT CHARSET=utf8mb4
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guest_name VARCHAR(255) NOT NULL,
                    phone VARCHAR(50) NOT NULL,
                    room_id INT NOT NULL,
                    check_in DATE NOT NULL,
                    check_out DATE NOT NULL,
                    guests INT NOT NULL DEFAULT 1,
                    total DECIMAL(15,2) NOT NULL DEFAULT 0,
                    status VARCHAR(50) NOT NULL DEFAULT 'Đã đặt',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    CONSTRAINT fk_bookings_rooms
                    FOREIGN KEY (room_id)
                    REFERENCES rooms(id)
                    ON DELETE RESTRICT,

                    INDEX idx_booking_dates
                    (room_id, check_in, check_out, status)
                ) ENGINE=InnoDB
                  DEFAULT CHARSET=utf8mb4
            """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ============================================================
# 4. HÀM TRUY VẤN DATABASE
# ============================================================

def query(sql, params=()):
    conn = connect()

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        return pd.DataFrame(rows)

    finally:
        conn.close()


def execute(sql, params=()):
    conn = connect()

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            last_id = cursor.lastrowid

        conn.commit()
        return last_id

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ============================================================
# 5. KHỞI TẠO DATABASE VÀ CẬP NHẬT TRẠNG THÁI PHÒNG
# ============================================================

try:
    init_db()

except Exception as e:
    st.error("Không thể kết nối hoặc khởi tạo MySQL Aiven.")
    st.code(str(e))
    st.info(
        "Hãy kiểm tra HOST, PORT, USER, PASSWORD, DATABASE "
        "và chứng chỉ SSL của Aiven."
    )
    st.stop()


def update_room_status():
    today = date.today()

    conn = connect()

    try:
        with conn.cursor() as cursor:

            # Phòng đang có khách lưu trú
            cursor.execute("""
                UPDATE rooms
                SET status = 'Đang sử dụng'
                WHERE status != 'Bảo trì'
                  AND id IN (
                      SELECT room_id
                      FROM bookings
                      WHERE status = 'Đang ở'
                        AND check_in <= %s
                        AND check_out > %s
                  )
            """, (today, today))

            # Phòng đã đặt và sắp đến ngày nhận
            cursor.execute("""
                UPDATE rooms
                SET status = 'Đã đặt'
                WHERE status NOT IN ('Bảo trì', 'Đang dọn dẹp')
                  AND id IN (
                      SELECT room_id
                      FROM bookings
                      WHERE status = 'Đã đặt'
                        AND check_in <= %s
                        AND check_out > %s
                  )
                  AND id NOT IN (
                      SELECT room_id
                      FROM bookings
                      WHERE status = 'Đang ở'
                        AND check_in <= %s
                        AND check_out > %s
                  )
            """, (today, today, today, today))

            # Các phòng không có khách đang ở hoặc đặt trong ngày
            cursor.execute("""
                UPDATE rooms
                SET status = 'Trống'
                WHERE status NOT IN ('Bảo trì', 'Đang dọn dẹp')
                  AND id NOT IN (
                      SELECT room_id
                      FROM bookings
                      WHERE status IN ('Đã đặt', 'Đang ở')
                        AND check_in <= %s
                        AND check_out > %s
                  )
            """, (today, today))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


try:
    update_room_status()
except Exception as e:
    st.warning(f"Không thể cập nhật trạng thái phòng: {e}")


# ============================================================
# 6. TIÊU ĐỀ VÀ TẢI DỮ LIỆU
# ============================================================

st.title("🏨 HỆ THỐNG QUẢN LÝ KHÁCH SẠN")

st.caption(
    "Quản lý phòng, đặt phòng, khách hàng và doanh thu "
    "với cơ sở dữ liệu MySQL Aiven."
)

rooms = query("SELECT * FROM rooms ORDER BY room_number")

bookings = query("""
    SELECT
        b.id,
        b.guest_name AS 'Khách hàng',
        b.phone AS 'Số điện thoại',
        r.room_number AS 'Phòng',
        r.room_type AS 'Loại phòng',
        b.check_in AS 'Ngày nhận',
        b.check_out AS 'Ngày trả',
        b.guests AS 'Số khách',
        b.total AS 'Tổng tiền',
        b.status AS 'Trạng thái'
    FROM bookings b
    JOIN rooms r ON b.room_id = r.id
    ORDER BY b.id DESC
""")


# ============================================================
# 7. THỐNG KÊ TỔNG QUAN
# ============================================================

total_rooms = len(rooms)

vacant = (
    int((rooms["status"] == "Trống").sum())
    if total_rooms else 0
)

occupied = (
    int((rooms["status"] == "Đang sử dụng").sum())
    if total_rooms else 0
)

reserved = (
    int((rooms["status"] == "Đã đặt").sum())
    if total_rooms else 0
)

revenue_df = query("""
    SELECT COALESCE(SUM(total), 0) AS amount
    FROM bookings
    WHERE status IN ('Đang ở', 'Đã trả')
""")

revenue = float(revenue_df.iloc[0]["amount"])

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric("Tổng số phòng", total_rooms)
m2.metric("Phòng trống", vacant)
m3.metric("Đang sử dụng", occupied)
m4.metric("Đã đặt", reserved)
m5.metric("Doanh thu ghi nhận", f"{revenue:,.0f} đ")


# ============================================================
# 8. CÁC TAB CHỨC NĂNG
# ============================================================

tabs = st.tabs([
    "📊 Tổng quan",
    "🛏️ Quản lý phòng",
    "📝 Đặt phòng",
    "👥 Khách hàng & lưu trú"
])


# ============================================================
# TAB 1: TỔNG QUAN
# ============================================================

with tabs[0]:

    left, right = st.columns(2)

    with left:
        st.subheader("Tình trạng phòng")

        if not rooms.empty:
            status_counts = (
                rooms["status"]
                .value_counts()
                .rename_axis("Trạng thái")
                .reset_index(name="Số phòng")
            )

            st.bar_chart(
                status_counts.set_index("Trạng thái")
            )

        else:
            st.info(
                "Chưa có phòng. Hãy thêm phòng trong mục Quản lý phòng."
            )

    with right:
        st.subheader("Đặt phòng gần đây")

        if bookings.empty:
            st.info("Chưa có lượt đặt phòng.")

        else:
            st.dataframe(
                bookings.drop(columns=["id"]).head(8),
                use_container_width=True,
                hide_index=True
            )


# ============================================================
# TAB 2: QUẢN LÝ PHÒNG
# ============================================================

with tabs[1]:

    st.subheader("Danh sách phòng")

    if rooms.empty:
        st.info("Chưa có phòng. Thêm phòng bằng biểu mẫu bên dưới.")

    else:
        st.dataframe(
            rooms,
            use_container_width=True,
            hide_index=True
        )

    # --------------------------------------------------------
    # THÊM PHÒNG
    # --------------------------------------------------------

    st.markdown("### ➕ Thêm phòng")

    with st.form("add_room_form", clear_on_submit=True):

        c1, c2, c3 = st.columns(3)

        room_number = c1.text_input(
            "Số phòng (ví dụ 101)"
        )

        room_type = c2.selectbox(
            "Loại phòng",
            [
                "Phòng đơn",
                "Phòng đôi",
                "Phòng gia đình",
                "Phòng VIP"
            ]
        )

        price = c3.number_input(
            "Giá phòng / đêm (VNĐ)",
            min_value=0,
            value=500000,
            step=50000
        )

        add_room = st.form_submit_button(
            "➕ Thêm phòng",
            use_container_width=True
        )

        if add_room:

            if not room_number.strip():
                st.error("Vui lòng nhập số phòng.")

            else:
                try:
                    execute("""
                        INSERT INTO rooms
                        (room_number, room_type, price, status)
                        VALUES (%s, %s, %s, 'Trống')
                    """, (
                        room_number.strip(),
                        room_type,
                        price
                    ))

                    st.success(
                        f"Đã thêm phòng {room_number.strip()}."
                    )

                    st.rerun()

                except pymysql.err.IntegrityError:
                    st.error("Số phòng đã tồn tại.")

                except Exception as e:
                    st.error(f"Lỗi khi thêm phòng: {e}")

    # --------------------------------------------------------
    # CHỈNH SỬA VÀ XÓA PHÒNG
    # --------------------------------------------------------

    if not rooms.empty:

        st.markdown("### ✏️ Chỉnh sửa / xóa phòng")

        room_map = {
            f"{r['room_number']} — {r['room_type']}":
            int(r["id"])
            for _, r in rooms.iterrows()
        }

        chosen_label = st.selectbox(
            "Chọn phòng",
            list(room_map.keys()),
            key="edit_room_select"
        )

        chosen_id = room_map[chosen_label]

        selected = rooms[
            rooms["id"] == chosen_id
        ].iloc[0]

        with st.form("edit_room_form"):

            e1, e2, e3 = st.columns(3)

            new_number = e1.text_input(
                "Số phòng",
                value=str(selected["room_number"])
            )

            types = [
                "Phòng đơn",
                "Phòng đôi",
                "Phòng gia đình",
                "Phòng VIP"
            ]

            current_type = str(selected["room_type"])

            new_type = e2.selectbox(
                "Loại phòng",
                types,
                index=(
                    types.index(current_type)
                    if current_type in types else 0
                )
            )

            new_price = e3.number_input(
                "Giá / đêm (VNĐ)",
                min_value=0,
                value=int(selected["price"]),
                step=50000
            )

            status_options = [
                "Trống",
                "Đã đặt",
                "Đang sử dụng",
                "Đang dọn dẹp",
                "Bảo trì"
            ]

            current_status = str(selected["status"])

            new_status = st.selectbox(
                "Trạng thái phòng",
                status_options,
                index=(
                    status_options.index(current_status)
                    if current_status in status_options else 0
                )
            )

            save_room = st.form_submit_button(
                "💾 Lưu thay đổi"
            )

        if save_room:

            if not new_number.strip():
                st.error("Vui lòng nhập số phòng.")

            else:
                try:
                    execute("""
                        UPDATE rooms
                        SET room_number=%s,
                            room_type=%s,
                            price=%s,
                            status=%s
                        WHERE id=%s
                    """, (
                        new_number.strip(),
                        new_type,
                        new_price,
                        new_status,
                        chosen_id
                    ))

                    st.success("Đã cập nhật phòng.")
                    st.rerun()

                except pymysql.err.IntegrityError:
                    st.error(
                        "Số phòng đã được sử dụng bởi phòng khác."
                    )

                except Exception as e:
                    st.error(f"Lỗi cập nhật phòng: {e}")

        if st.button(
            "🗑️ Xóa phòng đang chọn",
            type="secondary"
        ):

            count = query("""
                SELECT COUNT(*) AS n
                FROM bookings
                WHERE room_id=%s
            """, (chosen_id,)).iloc[0]["n"]

            if count:
                st.error(
                    "Không thể xóa phòng đã có lịch sử đặt phòng."
                )

            else:
                try:
                    execute(
                        "DELETE FROM rooms WHERE id=%s",
                        (chosen_id,)
                    )

                    st.success("Đã xóa phòng.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Lỗi xóa phòng: {e}")


# ============================================================
# TAB 3: ĐẶT PHÒNG
# ============================================================

with tabs[2]:

    st.subheader("📝 Tạo đặt phòng mới")

    available_rooms = query("""
        SELECT *
        FROM rooms
        WHERE status NOT IN ('Bảo trì', 'Đang dọn dẹp')
        ORDER BY room_number
    """)

    if available_rooms.empty:

        st.warning(
            "Chưa có phòng phù hợp. Hãy thêm phòng trước."
        )

    else:

        room_options = {
            (
                f"{r['room_number']} | {r['room_type']} | "
                f"{float(r['price']):,.0f} đ/đêm "
                f"({r['status']})"
            ): int(r["id"])
            for _, r in available_rooms.iterrows()
        }

        with st.form(
            "booking_form",
            clear_on_submit=True
        ):

            guest_name = st.text_input(
                "Họ và tên khách"
            )

            phone = st.text_input(
                "Số điện thoại"
            )

            room_label = st.selectbox(
                "Chọn phòng",
                list(room_options.keys())
            )

            c1, c2, c3 = st.columns(3)

            check_in = c1.date_input(
                "Ngày nhận phòng",
                value=date.today(),
                min_value=date.today()
            )

            check_out = c2.date_input(
                "Ngày trả phòng",
                value=date.today() + timedelta(days=1),
                min_value=date.today() + timedelta(days=1)
            )

            guests = c3.number_input(
                "Số khách",
                min_value=1,
                max_value=20,
                value=1
            )

            submit_booking = st.form_submit_button(
                "✅ Tạo đặt phòng",
                use_container_width=True
            )

            if submit_booking:

                if not guest_name.strip() or not phone.strip():

                    st.error(
                        "Vui lòng nhập họ tên và số điện thoại."
                    )

                elif check_out <= check_in:

                    st.error(
                        "Ngày trả phòng phải sau ngày nhận phòng."
                    )

                else:

                    room_id = room_options[room_label]

                    room_row = available_rooms[
                        available_rooms["id"] == room_id
                    ].iloc[0]

                    nights = (check_out - check_in).days

                    total = nights * float(room_row["price"])

                    # Kiểm tra trùng lịch đặt phòng
                    overlap = query("""
                        SELECT COUNT(*) AS n
                        FROM bookings
                        WHERE room_id=%s
                          AND status IN ('Đã đặt', 'Đang ở')
                          AND NOT (
                              check_out <= %s
                              OR check_in >= %s
                          )
                    """, (
                        room_id,
                        check_in,
                        check_out
                    )).iloc[0]["n"]

                    if overlap:

                        st.error(
                            "Phòng đã có đặt phòng trùng thời gian. "
                            "Vui lòng chọn phòng hoặc ngày khác."
                        )

                    else:

                        try:
                            execute("""
                                INSERT INTO bookings (
                                    guest_name,
                                    phone,
                                    room_id,
                                    check_in,
                                    check_out,
                                    guests,
                                    total,
                                    status
                                )
                                VALUES (
                                    %s, %s, %s, %s,
                                    %s, %s, %s, 'Đã đặt'
                                )
                            """, (
                                guest_name.strip(),
                                phone.strip(),
                                room_id,
                                check_in,
                                check_out,
                                int(guests),
                                total
                            ))

                            st.success(
                                f"Đã tạo đặt phòng. "
                                f"Tổng tiền dự kiến: "
                                f"{total:,.0f} đ "
                                f"({nights} đêm)."
                            )

                            st.rerun()

                        except Exception as e:
                            st.error(
                                f"Lỗi khi tạo đặt phòng: {e}"
                            )


# ============================================================
# TAB 4: KHÁCH HÀNG VÀ LƯU TRÚ
# ============================================================

with tabs[3]:

    st.subheader("👥 Danh sách khách hàng và đặt phòng")

    all_bookings = query("""
        SELECT
            b.id,
            b.guest_name AS 'Khách hàng',
            b.phone AS 'Số điện thoại',
            r.room_number AS 'Phòng',
            r.room_type AS 'Loại phòng',
            b.check_in AS 'Ngày nhận',
            b.check_out AS 'Ngày trả',
            b.guests AS 'Số khách',
            b.total AS 'Tổng tiền',
            b.status AS 'Trạng thái'
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        ORDER BY b.id DESC
    """)

    if all_bookings.empty:

        st.info("Chưa có thông tin khách hàng.")

    else:

        # ----------------------------------------------------
        # TÌM KIẾM KHÁCH HÀNG
        # ----------------------------------------------------

        search = st.text_input(
            "🔎 Tìm theo tên khách, số điện thoại hoặc số phòng"
        )

        filtered = all_bookings.copy()

        if search.strip():

            mask = filtered.astype(str).apply(
                lambda col: col.str.contains(
                    search.strip(),
                    case=False,
                    na=False,
                    regex=False
                )
            ).any(axis=1)

            filtered = filtered[mask]

        st.dataframe(
            filtered.drop(columns=["id"]),
            use_container_width=True,
            hide_index=True
        )

        # ----------------------------------------------------
        # CẬP NHẬT TRẠNG THÁI ĐẶT PHÒNG
        # ----------------------------------------------------

        st.markdown("### 🔄 Cập nhật trạng thái đặt phòng")

        booking_map = {
            (
                f"#{int(r['id'])} — {r['Khách hàng']} — "
                f"phòng {r['Phòng']} "
                f"({r['Ngày nhận']} → {r['Ngày trả']})"
            ): int(r["id"])
            for _, r in all_bookings.iterrows()
        }

        selected_booking_label = st.selectbox(
            "Chọn lượt đặt phòng",
            list(booking_map.keys())
        )

        selected_booking_id = booking_map[
            selected_booking_label
        ]

        current_booking_status = str(
            all_bookings[
                all_bookings["id"] == selected_booking_id
            ].iloc[0]["Trạng thái"]
        )

        booking_statuses = [
            "Đã đặt",
            "Đang ở",
            "Đã trả",
            "Đã hủy"
        ]

        with st.form("booking_status_form"):

            new_booking_status = st.selectbox(
                "Trạng thái mới",
                booking_statuses,
                index=(
                    booking_statuses.index(current_booking_status)
                    if current_booking_status in booking_statuses
                    else 0
                )
            )

            update_booking = st.form_submit_button(
                "💾 Cập nhật trạng thái"
            )

        if update_booking:

            try:
                execute("""
                    UPDATE bookings
                    SET status=%s
                    WHERE id=%s
                """, (
                    new_booking_status,
                    selected_booking_id
                ))

                st.success(
                    "Đã cập nhật trạng thái đặt phòng."
                )

                st.rerun()

            except Exception as e:
                st.error(
                    f"Lỗi cập nhật trạng thái: {e}"
                )


# ============================================================
# 9. CHÂN TRANG
# ============================================================

st.divider()

st.caption(
    "Hệ thống quản lý khách sạn sử dụng Streamlit và MySQL Aiven. "
    "Doanh thu được tính từ các lượt 'Đang ở' và 'Đã trả'. "
    "Tiền phòng = số đêm × giá phòng mỗi đêm."
)
