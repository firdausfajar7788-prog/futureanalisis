import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import certifi

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="📊 MongoDB CRUD Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# CSS KUSTOM
# =========================================================
st.markdown("""
<style>
    .stApp {
        background: #0a0a1a;
    }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #111827, #0b1220);
        border: 1px solid #1e293b;
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 4px 20px rgba(0,255,255,0.05);
    }
    .stButton > button {
        background: linear-gradient(145deg, #00ff88, #00cc66);
        color: #000;
        font-weight: 700;
        border: none;
        border-radius: 10px;
        padding: 10px 24px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: scale(1.03);
        box-shadow: 0 0 30px rgba(0,255,255,0.3);
    }
    .delete-btn > button {
        background: linear-gradient(145deg, #ff3b5c, #cc0033) !important;
    }
    .delete-btn > button:hover {
        box-shadow: 0 0 30px rgba(255,59,92,0.3) !important;
    }
    .update-btn > button {
        background: linear-gradient(145deg, #ffaa00, #cc8800) !important;
    }
    .update-btn > button:hover {
        box-shadow: 0 0 30px rgba(255,170,0,0.3) !important;
    }
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .status-active {
        background: rgba(0,255,136,0.15);
        color: #00ff88;
        border: 1px solid #00ff88;
    }
    .status-inactive {
        background: rgba(255,59,92,0.15);
        color: #ff3b5c;
        border: 1px solid #ff3b5c;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# MONGODB CONNECTION
# =========================================================
@st.cache_resource
def get_mongo_client():
    """Mendapatkan koneksi ke MongoDB Atlas"""
    try:
        connection_string = st.secrets["mongodb"]["connection_string"]
        client = MongoClient(
            connection_string,
            tls=True,
            tlsAllowInvalidCertificates=False,
            tlsCAFile=certifi.where()
        )
        client.admin.command('ping')
        return client
    except Exception as e:
        st.error(f"❌ Gagal konek ke MongoDB: {e}")
        return None

@st.cache_resource
def get_db():
    """Mendapatkan database"""
    client = get_mongo_client()
    if client:
        return client[st.secrets["mongodb"]["database_name"]]
    return None

# =========================================================
# CRUD FUNCTIONS
# =========================================================

# --- CREATE ---
def create_coin(symbol, name=None, category=None, active=True):
    """Tambah coin baru ke database"""
    db = get_db()
    if not db:
        return False, "Database tidak terhubung"
    
    collection = db["coins"]
    
    # Cek duplikat
    if collection.find_one({"symbol": symbol.upper()}):
        return False, f"Coin {symbol.upper()} sudah ada!"
    
    doc = {
        "symbol": symbol.upper(),
        "name": name or symbol.upper(),
        "category": category or "Crypto",
        "active": active,
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    try:
        collection.insert_one(doc)
        return True, f"✅ {symbol.upper()} berhasil ditambahkan!"
    except Exception as e:
        return False, f"❌ Gagal tambah: {e}"

# --- READ ---
def get_all_coins(active_only=True):
    """Ambil semua coin dari database"""
    db = get_db()
    if not db:
        return []
    
    collection = db["coins"]
    query = {"active": True} if active_only else {}
    
    try:
        docs = collection.find(query).sort("symbol", 1)
        return list(docs)
    except Exception as e:
        st.error(f"❌ Gagal ambil data: {e}")
        return []

def get_coin_by_symbol(symbol):
    """Ambil coin berdasarkan symbol"""
    db = get_db()
    if not db:
        return None
    
    collection = db["coins"]
    try:
        return collection.find_one({"symbol": symbol.upper()})
    except Exception as e:
        st.error(f"❌ Gagal ambil data: {e}")
        return None

# --- UPDATE ---
def update_coin(symbol, updates):
    """Update data coin"""
    db = get_db()
    if not db:
        return False, "Database tidak terhubung"
    
    collection = db["coins"]
    updates["updated_at"] = datetime.now()
    
    try:
        result = collection.update_one(
            {"symbol": symbol.upper()},
            {"$set": updates}
        )
        if result.modified_count > 0:
            return True, f"✅ {symbol.upper()} berhasil diupdate!"
        else:
            return False, f"⚠️ Tidak ada perubahan untuk {symbol.upper()}"
    except Exception as e:
        return False, f"❌ Gagal update: {e}"

# --- DELETE ---
def delete_coin(symbol):
    """Hapus coin dari database"""
    db = get_db()
    if not db:
        return False, "Database tidak terhubung"
    
    collection = db["coins"]
    try:
        result = collection.delete_one({"symbol": symbol.upper()})
        if result.deleted_count > 0:
            return True, f"🗑️ {symbol.upper()} berhasil dihapus!"
        else:
            return False, f"⚠️ {symbol.upper()} tidak ditemukan"
    except Exception as e:
        return False, f"❌ Gagal hapus: {e}"

# --- BULK OPERATIONS ---
def bulk_add_coins(symbols):
    """Tambah banyak coin sekaligus"""
    db = get_db()
    if not db:
        return False, "Database tidak terhubung"
    
    collection = db["coins"]
    added = 0
    errors = []
    
    for symbol in symbols:
        symbol = symbol.strip().upper()
        if not symbol:
            continue
            
        if collection.find_one({"symbol": symbol}):
            errors.append(f"{symbol} sudah ada")
            continue
            
        doc = {
            "symbol": symbol,
            "name": symbol,
            "category": "Crypto",
            "active": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        try:
            collection.insert_one(doc)
            added += 1
        except Exception as e:
            errors.append(f"{symbol}: {e}")
    
    msg = f"✅ {added} coin berhasil ditambahkan!"
    if errors:
        msg += f"\n⚠️ Gagal: {', '.join(errors)}"
    return True, msg

# =========================================================
# DASHBOARD UI
# =========================================================

st.title("📊 MongoDB CRUD Dashboard")
st.caption("Kelola data coin/watchlist dengan mudah")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Menu")
    
    menu = st.radio(
        "Pilih Menu",
        ["📋 Data Coin", "➕ Tambah Coin", "✏️ Update Coin", "🗑️ Hapus Coin", "📊 Statistik"]
    )
    
    st.divider()
    
    # Status Koneksi
    db = get_db()
    if db:
        st.success("✅ MongoDB Connected")
    else:
        st.error("❌ MongoDB Error")

# =========================================================
# MENU: DATA COIN
# =========================================================
if menu == "📋 Data Coin":
    st.subheader("📋 Daftar Coin")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        show_active = st.checkbox("Tampilkan hanya coin aktif", value=True)
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    coins = get_all_coins(active_only=show_active)
    
    if coins:
        # Convert ke DataFrame
        df = pd.DataFrame(coins)
        
        # Hapus field yang tidak perlu
        cols_to_drop = ["_id", "created_at", "updated_at"]
        for col in cols_to_drop:
            if col in df.columns:
                df = df.drop(columns=[col])
        
        # Format
        if "active" in df.columns:
            df["active"] = df["active"].apply(
                lambda x: '🟢 Active' if x else '🔴 Inactive'
            )
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Export CSV
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"coins_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("ℹ️ Belum ada data coin. Tambahkan coin baru!")

# =========================================================
# MENU: TAMBAH COIN
# =========================================================
elif menu == "➕ Tambah Coin":
    st.subheader("➕ Tambah Coin Baru")
    
    tab1, tab2 = st.tabs(["Tambah Satuan", "Tambah Banyak"])
    
    # --- Tab 1: Tambah Satuan ---
    with tab1:
        with st.form("add_coin_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                symbol = st.text_input("Symbol", placeholder="BTC", help="Contoh: BTC, ETH, SOL")
                name = st.text_input("Nama", placeholder="Bitcoin", help="Opsional")
            
            with col2:
                category = st.text_input("Kategori", placeholder="Crypto", help="Opsional")
                active = st.toggle("Aktif", value=True)
            
            submitted = st.form_submit_button("💾 Tambah Coin", use_container_width=True)
            
            if submitted:
                if symbol:
                    success, msg = create_coin(symbol, name, category, active)
                    if success:
                        st.success(msg)
                        st.balloons()
                    else:
                        st.error(msg)
                else:
                    st.warning("⚠️ Symbol wajib diisi!")
    
    # --- Tab 2: Tambah Banyak ---
    with tab2:
        st.caption("Masukkan satu simbol per baris")
        
        with st.form("bulk_add_form"):
            bulk_input = st.text_area(
                "Daftar Symbol",
                placeholder="BTC\nETH\nSOL\nDOGE\nPEPE",
                height=150
            )
            
            bulk_category = st.text_input("Kategori (opsional)", placeholder="Crypto")
            
            submitted_bulk = st.form_submit_button("💾 Tambah Semua", use_container_width=True)
            
            if submitted_bulk:
                if bulk_input:
                    symbols = [s.strip() for s in bulk_input.split('\n') if s.strip()]
                    if symbols:
                        with st.spinner("Menambahkan coin..."):
                            success, msg = bulk_add_coins(symbols)
                            if success:
                                st.success(msg)
                                st.balloons()
                            else:
                                st.error(msg)
                    else:
                        st.warning("⚠️ Tidak ada symbol yang valid!")
                else:
                    st.warning("⚠️ Masukkan minimal satu symbol!")

# =========================================================
# MENU: UPDATE COIN
# =========================================================
elif menu == "✏️ Update Coin":
    st.subheader("✏️ Update Data Coin")
    
    coins = get_all_coins(active_only=False)
    
    if not coins:
        st.warning("ℹ️ Belum ada data coin!")
        st.stop()
    
    # Pilih coin
    coin_options = [c["symbol"] for c in coins]
    selected_symbol = st.selectbox("Pilih Coin", coin_options)
    
    if selected_symbol:
        coin = get_coin_by_symbol(selected_symbol)
        
        if coin:
            st.divider()
            
            with st.form("update_coin_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    new_name = st.text_input("Nama", value=coin.get("name", ""))
                    new_symbol = st.text_input("Symbol (tidak bisa diubah)", value=coin.get("symbol", ""), disabled=True)
                
                with col2:
                    new_category = st.text_input("Kategori", value=coin.get("category", ""))
                    new_active = st.toggle("Aktif", value=coin.get("active", True))
                
                submitted_update = st.form_submit_button("💾 Update Coin", use_container_width=True)
                
                if submitted_update:
                    updates = {
                        "name": new_name or new_symbol,
                        "category": new_category or "Crypto",
                        "active": new_active
                    }
                    
                    success, msg = update_coin(selected_symbol, updates)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# =========================================================
# MENU: HAPUS COIN
# =========================================================
elif menu == "🗑️ Hapus Coin":
    st.subheader("🗑️ Hapus Coin")
    
    coins = get_all_coins(active_only=False)
    
    if not coins:
        st.warning("ℹ️ Belum ada data coin!")
        st.stop()
    
    # Pilih coin
    coin_options = [c["symbol"] for c in coins]
    selected_symbol = st.selectbox("Pilih Coin yang akan dihapus", coin_options)
    
    if selected_symbol:
        coin = get_coin_by_symbol(selected_symbol)
        
        if coin:
            st.divider()
            
            # Tampilkan info coin
            col1, col2, col3 = st.columns(3)
            col1.metric("Symbol", coin.get("symbol", "-"))
            col2.metric("Nama", coin.get("name", "-"))
            col3.metric("Status", "🟢 Active" if coin.get("active") else "🔴 Inactive")
            
            st.warning(f"⚠️ Anda yakin ingin menghapus **{selected_symbol}**?")
            
            col_del1, col_del2 = st.columns(2)
            with col_del1:
                if st.button("🗑️ Hapus Permanen", use_container_width=True, key="delete_btn"):
                    success, msg = delete_coin(selected_symbol)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            
            with col_del2:
                if st.button("❌ Batal", use_container_width=True):
                    st.rerun()

# =========================================================
# MENU: STATISTIK
# =========================================================
elif menu == "📊 Statistik":
    st.subheader("📊 Statistik Database")
    
    db = get_db()
    if not db:
        st.error("❌ Database tidak terhubung!")
        st.stop()
    
    # Ambil data
    coins = get_all_coins(active_only=False)
    total_coins = len(coins)
    active_coins = sum(1 for c in coins if c.get("active", True))
    inactive_coins = total_coins - active_coins
    
    # Kategori
    categories = {}
    for c in coins:
        cat = c.get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1
    
    # Tampilkan statistik
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 Total Coin", total_coins)
    col2.metric("🟢 Aktif", active_coins)
    col3.metric("🔴 Non-Aktif", inactive_coins)
    col4.metric("📂 Kategori", len(categories))
    
    st.divider()
    
    # Chart Kategori
    if categories:
        st.subheader("📊 Distribusi Kategori")
        
        cat_df = pd.DataFrame({
            "Kategori": list(categories.keys()),
            "Jumlah": list(categories.values())
        })
        cat_df = cat_df.sort_values("Jumlah", ascending=False)
        
        st.bar_chart(cat_df.set_index("Kategori"))
    
    # Daftar coin per kategori
    st.subheader("📋 Daftar Coin per Kategori")
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        with st.expander(f"📁 {cat} ({count} coin)"):
            coin_list = [c["symbol"] for c in coins if c.get("category", "Unknown") == cat]
            st.write(", ".join(coin_list))

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(f"""
🔄 Dashboard CRUD MongoDB | Database: {st.secrets["mongodb"]["database_name"]}  
📊 Total Coin: {len(get_all_coins(active_only=False))} | Terakhir update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""")
