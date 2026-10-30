"""장보기 알림메모 — 실행: streamlit run app.py
Python 3.10+ / requirements.txt와 함께 GitHub에 업로드하세요.
Streamlit Community Cloud: Main file path = app.py.
선택 Secrets: APP_URL = "https://your-app.streamlit.app"
선택 환경변수 SHOPPING_DB: SQLite 파일 경로(기본 shopping.db).
주의: Cloud의 로컬 SQLite는 재시작/재배포 때 유실될 수 있습니다.
영구 보관/다중 서버 운영에는 외부 DB로 교체하세요.
QR/공유 주소는 해당 목록의 열쇠입니다. 아는 사람만 공유하세요.
"""
import io
import os
import sqlite3
import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import qrcode
import streamlit as st

st.set_page_config(page_title="장보기 알림메모", page_icon="🛒", layout="centered", initial_sidebar_state="collapsed")

DB_PATH = os.getenv("SHOPPING_DB", "shopping.db")
CATEGORIES = ["🥬 야채", "🍎 과일", "🥩 정육·계란", "🐟 수산", "🥛 유제품", "🍚 곡물·식재료", "🍪 간식·음료", "🧻 생활용품", "📦 기타"]
PRIORITIES = {1: "🔴 1 꼭 구매", 2: "🟡 2 가격 보고", 3: "🟢 3 저렴할 때"}
PAGE_SIZE = 3


def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def init_db():
    conn = connect()
    try:
        with conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY, list_id TEXT NOT NULL,
                    name TEXT NOT NULL, category TEXT NOT NULL,
                    priority INTEGER NOT NULL CHECK(priority BETWEEN 1 AND 3),
                    target INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS purchases (
                    id TEXT PRIMARY KEY, list_id TEXT NOT NULL,
                    item_id TEXT NOT NULL UNIQUE,
                    unit_price INTEGER NOT NULL, quantity TEXT NOT NULL,
                    total INTEGER NOT NULL,
                    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_items_list ON items(list_id, status);
                CREATE INDEX IF NOT EXISTS idx_purchase_list ON purchases(list_id);
            ''')
    finally:
        conn.close()


def rows(sql, args=()):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def execute(sql, args=()):
    conn = connect()
    try:
        with conn:
            conn.execute(sql, args)
    finally:
        conn.close()


def purchase(list_id, item_id, price, quantity):
    """중복 클릭/동시 구매 방지. 구매 내역과 목록 상태를 한 트랜잭션으로 저장."""
    qty = Decimal(str(quantity))
    if int(price) < 0 or qty <= 0 or not qty.is_finite():
        raise ValueError("가격은 0원 이상, 수량은 0보다 커야 합니다.")
    total = int((Decimal(int(price)) * qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            item = conn.execute("SELECT * FROM items WHERE id=? AND list_id=? AND status IN ('pending','deferred')", (item_id, list_id)).fetchone()
            if item is None:
                return False
            conn.execute("INSERT INTO purchases (id,list_id,item_id,unit_price,quantity,total) VALUES (?,?,?,?,?,?)", (uuid.uuid4().hex, list_id, item_id, int(price), str(qty), total))
            conn.execute("UPDATE items SET status='purchased' WHERE id=? AND list_id=?", (item_id, list_id))
        return True
    finally:
        conn.close()


def undo_purchase(list_id, purchase_id):
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            record = conn.execute("SELECT item_id FROM purchases WHERE id=? AND list_id=?", (purchase_id, list_id)).fetchone()
            if record:
                conn.execute("DELETE FROM purchases WHERE id=? AND list_id=?", (purchase_id, list_id))
                conn.execute("UPDATE items SET status='pending' WHERE id=? AND list_id=?", (record['item_id'], list_id))
    finally:
        conn.close()


init_db()
token = str(st.query_params.get("memo", ""))
try:
    if len(token) != 32:
        raise ValueError()
    uuid.UUID(hex=token)
except ValueError:
    token = uuid.uuid4().hex
    st.query_params["memo"] = token
LIST_ID = token

st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap');
:root {color-scheme:light;}
html,body,[class*="css"] {font-family:'Noto Sans KR',sans-serif;}
.stApp {background:#f5f7f4;}
header[data-testid="stHeader"] {display:none;}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {display:none;}
[data-testid="stMainBlockContainer"] {max-width:540px;padding:0.6rem 0.65rem 0.2rem!important;}
[data-testid="stVerticalBlock"] {gap:0.38rem;}
[data-testid="stHorizontalBlock"] {gap:0.35rem;}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width:0!important;}
[data-testid="stButton"] button {min-height:2.25rem;padding:0.2rem 0.35rem;font-size:0.8rem;white-space:nowrap;border-radius:12px;}
[data-testid="stButton"] button p {font-size:0.8rem;}
[data-testid="stMarkdownContainer"] p {margin-bottom:0.1rem;}
[data-testid="stCaptionContainer"] {font-size:0.7rem;}
[data-testid="stAlert"] {padding:0.4rem;}
.title {font-size:1.32rem;font-weight:700;letter-spacing:-0.06em;color:#173e2a;}
.total {background:#173e2a;color:white;border-radius:16px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;}
.total strong {font-size:1.5rem;}
.total small {color:#d7eadc;}
[data-testid="stVerticalBlockBorderWrapper"] > div {border-radius:12px!important;}
/* 본문은 3개 항목씩 페이지 이동. 작은 화면/큰 글씨에서는 접근성을 위해 스크롤 허용. */
@media (max-width:640px) {
 [data-testid="stHorizontalBlock"] {flex-wrap:nowrap!important;}
 [data-testid="stMainBlockContainer"] {padding-top:0.4rem!important;}
}
@media (max-height:700px) {
 [data-testid="stVerticalBlock"] {gap:0.22rem;}
 [data-testid="stButton"] button {min-height:2rem;}
 .total {padding:7px 12px;}
}
</style>''', unsafe_allow_html=True)


@st.dialog("➕ 장볼 물건", width="small")
def add_dialog():
    with st.form("add_form", clear_on_submit=False):
        category = st.selectbox("카테고리", CATEGORIES)
        name = st.text_input("상품명", placeholder="예: 양파 1망 / 사과 3개", max_chars=60)
        priority = st.select_slider("중요도", options=[1, 2, 3], value=2, format_func=lambda v: PRIORITIES[v])
        target = st.number_input("희망 단가(원) · 0이면 미지정", min_value=0, max_value=100000000, step=100, value=0)
        note = st.text_input("짧은 메모", placeholder="예: 국내산 / 5천 원 넘으면 보류", max_chars=100)
        submit = st.form_submit_button("메모 저장", use_container_width=True, type="primary")
    if submit:
        if not name.strip():
            st.error("상품명을 입력해주세요.")
        else:
            execute("INSERT INTO items (id,list_id,name,category,priority,target,note) VALUES (?,?,?,?,?,?,?)", (uuid.uuid4().hex, LIST_ID, name.strip(), category, priority, target, note.strip()))
            st.rerun()


@st.dialog("🛒 카트에 담기", width="small")
def buy_dialog(item):
    st.write(f"**{item['name']}**")
    st.caption(PRIORITIES[item['priority']] + " · 가격은 수량 1단위 기준으로 입력")
    if item['note']:
        st.info(item['note'])
    price = st.number_input("실제 단가(원)", min_value=0, max_value=100000000, value=int(item['target']), step=100, key=f"price_{item['id']}")
    qty = st.number_input("수량 (개·팩·kg 등 동일 단위)", min_value=0.01, max_value=100000.0, value=1.0, step=0.5, format="%.2f", key=f"qty_{item['id']}")
    cost = int((Decimal(price) * Decimal(str(qty))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    st.write(f"이번에 담을 금액 **{cost:,}원**")
    if item['target'] and price > item['target']:
        st.warning(f"희망 단가보다 {price-item['target']:,}원 비싸요. 구매하지 않고 보류할 수 있어요.")
    elif item['priority'] > 1:
        st.caption("비싸면 안 사도 괜찮아요. 보류해도 메모는 남습니다.")
    left, right = st.columns(2)
    if left.button("구매 확정", type="primary", use_container_width=True):
        if purchase(LIST_ID, item['id'], price, qty):
            st.session_state['flash'] = f"{item['name']} · {cost:,}원 담았어요"
        else:
            st.session_state['flash'] = "이미 처리된 항목이에요. 목록을 새로 확인했어요."
        st.rerun()
    if right.button("비싸요 · 보류", use_container_width=True):
        execute("UPDATE items SET status='deferred' WHERE id=? AND list_id=? AND status='pending'", (item['id'], LIST_ID))
        st.rerun()


@st.dialog("물건 관리", width="small")
def manage_dialog(item):
    st.write(f"**{item['name']}**")
    with st.form("edit_item"):
        name = st.text_input("상품명", value=item['name'], max_chars=60)
        category = st.selectbox("카테고리", CATEGORIES, index=CATEGORIES.index(item['category']) if item['category'] in CATEGORIES else 8)
        priority = st.select_slider("중요도", options=[1,2,3], value=item['priority'], format_func=lambda v: PRIORITIES[v])
        target = st.number_input("희망 단가(원)", min_value=0, max_value=100000000, step=100, value=item['target'])
        note = st.text_input("메모", value=item['note'], max_chars=100)
        saved = st.form_submit_button("변경 저장", use_container_width=True)
    if saved:
        if not name.strip():
            st.error("상품명을 입력해주세요.")
        else:
            execute("UPDATE items SET name=?,category=?,priority=?,target=?,note=? WHERE id=? AND list_id=? AND status!='purchased'", (name.strip(),category,priority,target,note.strip(),item['id'],LIST_ID))
            st.rerun()
    confirm = st.checkbox("구매 없이 이 메모를 영구 삭제합니다")
    if st.button("메모 삭제", disabled=not confirm, use_container_width=True):
        execute("DELETE FROM items WHERE id=? AND list_id=? AND status!='purchased'", (item['id'],LIST_ID))
        st.rerun()


def default_url():
    try:
        configured = st.secrets.get("APP_URL", "")
    except Exception:
        configured = ""
    if configured:
        return configured
    try:
        headers = st.context.headers
        host = headers.get("X-Forwarded-Host") or headers.get("Host", "")
        if host and not any(x in host for x in ["localhost", "127.0.0.1", "0.0.0.0"]):
            return "https://" + host.split(",")[0].strip()
    except Exception:
        pass
    return ""


@st.dialog("📱 QR로 이 목록 열기", width="small")
def share_dialog():
    st.caption("QR은 스마트폰에서 배포된 앱을 여는 용도입니다. 로컬 PC 주소는 밖에서 열리지 않아요.")
    base = st.text_input("배포 앱 주소", value=default_url(), placeholder="https://your-app.streamlit.app")
    parsed = urlsplit(base.strip())
    if parsed.scheme in ('https','http') and parsed.netloc:
        link = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode({'memo':LIST_ID}), ''))
        img = qrcode.make(link)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        st.image(buf.getvalue(), width=210)
        st.link_button("이 목록 열기", link, use_container_width=True)
        st.code(link, language=None)
        st.download_button("QR 이미지 저장", buf.getvalue(), file_name="shopping-qr.png", mime="image/png", use_container_width=True)
        st.warning("이 링크를 가진 사람은 목록을 보거나 수정할 수 있어요. 공개 게시하지 마세요.")
    elif base:
        st.error("https://로 시작하는 올바른 배포 주소를 입력해주세요.")
    st.caption("현재 목록 주소를 북마크하면 같은 목록으로 돌아옵니다. 기기 간 공유는 같은 앱 서버에서 동작합니다.")


@st.dialog("사용 안내 · 데이터", width="small")
def help_dialog():
    st.markdown("""**1 꼭 구매 / 2 가격 보고 / 3 저렴할 때**

- `담기`: 실제 단가 × 수량을 입력해야 구매로 기록됩니다.
- `보류`: 메모는 보존하고 구매 대기에서만 잠시 제외합니다.
- `카트`: 구매 내역과 합계를 확인하고 잘못 담은 물건은 되돌립니다.
- 가격은 원 단위, 수량은 소수 둘째 자리까지이며 합계는 원 단위 반올림입니다.
- 대기 목록은 중요도 순서, 카트는 최신 구매 순서입니다.
- 한 화면 3개씩 표시합니다. 아주 작은 화면·확대 글씨·입력 팝업에서는 스크롤이 생길 수 있습니다.

**보관 주의**: 현재 버전은 서버의 SQLite에 저장합니다. Community Cloud의 재시작·재배포로 데이터가 초기화될 수 있습니다. 장기 보관용은 외부 DB 연결이 필요합니다. QR 링크는 비밀번호와 같은 역할입니다.
""")
    data = rows("SELECT i.name AS 상품명,i.category AS 카테고리,i.priority AS 중요도,p.unit_price AS 단가,p.quantity AS 수량,p.total AS 금액,p.created AS 구매시각 FROM purchases p JOIN items i ON i.id=p.item_id WHERE p.list_id=? ORDER BY p.created", (LIST_ID,))
    import csv
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["상품명","카테고리","중요도","단가","수량","금액","구매시각(UTC)"])
    for r in data:
        # Excel 등에서 상품명/메모를 수식으로 실행하지 않도록 보호
        writer.writerow([("'"+str(v)) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in r.values()])
    st.download_button("구매 내역 CSV 백업", out.getvalue().encode('utf-8-sig'), file_name="shopping-history.csv", mime="text/csv", use_container_width=True)


if 'flash' in st.session_state:
    st.toast(st.session_state.pop('flash'))
head, qr, helpcol = st.columns([6,1.25,1.25])
head.markdown('<div class="title">🛒 장보기 알림메모</div>', unsafe_allow_html=True)
if qr.button("QR", use_container_width=True):
    share_dialog()
if helpcol.button("안내", use_container_width=True):
    help_dialog()

cart = rows("SELECT p.*,i.name,i.category FROM purchases p JOIN items i ON i.id=p.item_id WHERE p.list_id=? ORDER BY p.created DESC,p.rowid DESC", (LIST_ID,))
items = rows("SELECT * FROM items WHERE list_id=? AND status!='purchased' ORDER BY priority,created,rowid", (LIST_ID,))
total = sum(r['total'] for r in cart)
pending = sum(r['status']=='pending' for r in items)
deferred = sum(r['status']=='deferred' for r in items)
st.markdown(f'<div class="total"><div><small>현재 카트 · {len(cart)}종</small><br><strong>{total:,}원</strong></div><div><small>남은 메모 {pending} · 보류 {deferred}</small></div></div>', unsafe_allow_html=True)

modecol, addcol = st.columns([3,1])
mode = modecol.selectbox("목록", ["살 것", "보류", "카트"], label_visibility="collapsed")
if addcol.button("＋ 추가", type="primary", use_container_width=True):
    add_dialog()

if mode == "카트":
    visible = cart
else:
    filters = st.columns([2.3,1.7])
    category = filters[0].selectbox("카테고리 필터", ["모든 카테고리"]+CATEGORIES, label_visibility="collapsed")
    priority = filters[1].selectbox("중요도 필터", ["중요도 전체", "1 꼭 구매", "2 가격 보고", "3 저렴할 때"], label_visibility="collapsed")
    status = 'pending' if mode == '살 것' else 'deferred'
    visible = [r for r in items if r['status']==status and (category=='모든 카테고리' or r['category']==category) and (priority=='중요도 전체' or r['priority']==int(priority[0]))]

signature = (mode, category if mode!='카트' else '', priority if mode!='카트' else '')
if st.session_state.get('signature') != signature:
    st.session_state['page'] = 0
    st.session_state['signature'] = signature
pages = max(1, (len(visible)+PAGE_SIZE-1)//PAGE_SIZE)
page = min(st.session_state.get('page',0), pages-1)
st.session_state['page'] = page

if not visible:
    st.info({"살 것":"메모가 없어요. ＋ 추가로 시작하세요.", "보류":"보류한 물건이 없어요.", "카트":"아직 담은 물건이 없어요."}[mode])

for item in visible[page*PAGE_SIZE:(page+1)*PAGE_SIZE]:
    with st.container(border=True):
        if mode == '카트':
            label, undo = st.columns([4,1.2])
            label.text(item['name'])
            label.caption(f"{item['unit_price']:,}원 × {item['quantity']} = {item['total']:,}원")
            if undo.button("되돌림", key='undo_'+item['id'], use_container_width=True):
                undo_purchase(LIST_ID,item['id'])
                st.rerun()
        else:
            text, buy, defer, manage = st.columns([3.4,1.15,1.15,0.8])
            text.text(item['name'])
            target = f" · {item['target']:,}원 이하" if item['target'] else ''
            text.caption(f"{PRIORITIES[item['priority']]} · {item['category']}{target}")
            if item['note']:
                text.caption(item['note'][:32]+('…' if len(item['note'])>32 else ''))
            if buy.button("담기", key='buy_'+item['id'], use_container_width=True):
                buy_dialog(item)
            if defer.button("보류" if mode=='살 것' else '복귀', key='defer_'+item['id'], use_container_width=True):
                newstatus = 'deferred' if mode=='살 것' else 'pending'
                execute("UPDATE items SET status=? WHERE id=? AND list_id=? AND status IN ('pending','deferred')", (newstatus,item['id'],LIST_ID))
                st.rerun()
            if manage.button("⋯", key='manage_'+item['id'], use_container_width=True):
                manage_dialog(item)

prev, counter, nxt = st.columns([1,2,1])
if prev.button("◀ 이전", disabled=page==0, use_container_width=True):
    st.session_state['page'] = page-1
    st.rerun()
counter.markdown(f"<div style='text-align:center;padding-top:5px;font-size:12px;color:#64736a'>{page+1} / {pages} 페이지 · {len(visible)}개</div>", unsafe_allow_html=True)
if nxt.button("다음 ▶", disabled=page>=pages-1, use_container_width=True):
    st.session_state['page'] = page+1
    st.rerun()
st.caption("1 꼭 구매 · 2 가격 보고 · 3 저렴할 때  |  담은 물건은 카트로 이동")
