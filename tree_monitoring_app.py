import streamlit as st
import pandas as pd
import datetime
from geopy.distance import geodesic
from pathlib import Path
import re
import random
import os
import time
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import hashlib
from typing import Optional, Tuple, Dict, Any
from geopy.geocoders import Nominatim

# --- Custom CSS for Styling ---
def load_css():
    st.markdown("""
    <style>
        /* Main styling */
        body {
            font-family: 'Arial', sans-serif;
            background-color: #f5f5f5;
        }
        
        /* Header styling */
        .header-text {
            color: #2e8b57;
            font-weight: 700;
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        
        /* Sidebar styling */
        .sidebar .sidebar-content {
            background-color: #e8f5e9;
        }
        
        /* Button styling */
        .stButton>button {
            background-color: #4CAF50;
            color: white;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            border: none;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .stButton>button:hover {
            background-color: #388E3C;
            transform: scale(1.02);
        }
        
        /* Card styling */
        .card {
            background-color: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            margin-bottom: 1.5rem;
        }
        
        /* Tree visualization */
        .tree-visualization {
            text-align: center;
            margin: 2rem 0;
        }
        
        /* Progress bars */
        .progress-container {
            background-color: #e0e0e0;
            border-radius: 10px;
            height: 20px;
            margin: 1rem 0;
        }
        
        .progress-bar {
            background-color: #4CAF50;
            height: 100%;
            border-radius: 10px;
            transition: width 0.5s;
        }
        
        /* Custom tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        
        .stTabs [data-baseweb="tab"] {
            background-color: #e8f5e9;
            border-radius: 8px 8px 0 0 !important;
            padding: 10px 20px;
            transition: all 0.3s;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #4CAF50 !important;
            color: white !important;
        }
        
        /* Tree growth animation */
        @keyframes grow {
            0% { transform: scaleY(0.1); }
            100% { transform: scaleY(1); }
        }
        
        .tree-icon {
            font-size: 2rem;
            display: inline-block;
            animation: grow 1.5s ease-in-out;
        }
    </style>
    """, unsafe_allow_html=True)

# --- Configuration ---
DEFAULT_SPECIES = ["Acacia", "Eucalyptus", "Mango", "Neem", "Oak", "Pine"]
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
STORAGE_METHOD = "sqlite"

# --- Password Hashing ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# --- User Types ---
USER_TYPES = {
    "admin": "Administrator",
    "school": "School User",
    "public": "Public Viewer"
}

# --- Database Initialization ---
def initialize_data_files():
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    if STORAGE_METHOD == "sqlite":
        init_db()

def init_db():
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS trees (
        tree_id TEXT PRIMARY KEY,
        school TEXT,
        species TEXT,
        student_name TEXT,
        date_planted TEXT,
        tree_stage TEXT,
        rcd_cm REAL,
        dbh_cm REAL,
        height_m REAL,
        latitude REAL,
        longitude REAL,
        co2_kg REAL,
        status TEXT,
        county TEXT,
        sub_county TEXT,
        ward TEXT,
        adopter_name TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS species (
        species TEXT PRIMARY KEY,
        wood_density REAL,
        importance TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        user_type TEXT,
        school TEXT
    )""")
    
    if c.execute("SELECT COUNT(*) FROM species").fetchone()[0] == 0:
        default_species = [
            ("Acacia", 0.65, "Drought-resistant"),
            ("Eucalyptus", 0.55, "Fast-growing"),
            ("Mango", 0.50, "Fruit-bearing"),
            ("Neem", 0.60, "Medicinal"),
            ("Oak", 0.75, "Long-term storage"),
            ("Pine", 0.45, "Reforestation")
        ]
        c.executemany("INSERT INTO species VALUES (?, ?, ?)", default_species)
    
    c.execute("""INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)""", 
             ("admin", hash_password("admin123"), "admin", "All Schools"))
    
    conn.commit()
    conn.close()

# --- Tree Management Functions ---
def load_tree_data() -> pd.DataFrame:
    conn = sqlite3.connect(SQLITE_DB)
    df = pd.read_sql("SELECT * FROM trees", conn)
    conn.close()
    return df

def load_species_data() -> pd.DataFrame:
    conn = sqlite3.connect(SQLITE_DB)
    df = pd.read_sql("SELECT * FROM species", conn)
    conn.close()
    return df

def save_tree_data(df: pd.DataFrame) -> bool:
    try:
        conn = sqlite3.connect(SQLITE_DB)
        df.to_sql("trees", conn, if_exists="replace", index=False)
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database error: {e}")
        return False

def generate_tree_id(school_name: str) -> str:
    prefix = school_name[:3].upper()
    trees = load_tree_data()
    
    if trees.empty:
        return f"{prefix}001"
    
    school_trees = trees[trees["school"].str.lower() == school_name.lower()]
    existing_ids = [id for id in school_trees["tree_id"] if str(id).startswith(prefix)]
    
    if not existing_ids:
        return f"{prefix}001"
    
    max_num = max([int(re.search(r'\d+$', str(id)).group()) for id in existing_ids])
    return f"{prefix}{max_num + 1:03d}"

def calculate_co2(species: str, rcd: Optional[float] = None, dbh: Optional[float] = None) -> float:
    species_data = load_species_data()
    try:
        density = species_data[species_data["species"] == species]["wood_density"].values[0]
    except:
        density = 0.6
    
    if dbh is not None:
        agb = 0.0509 * density * (dbh ** 2.5)
    elif rcd is not None:
        agb = 0.042 * (rcd ** 2.5)
    else:
        return 0.0
        
    bgb = 0.2 * agb
    carbon = 0.47 * (agb + bgb)
    return round(carbon * 3.67, 2)

# --- Authentication Function ---
def authenticate(username: str, password: str) -> Optional[Tuple]:
    try:
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        
        if not user:
            return None
            
        if hash_password(password) == user[1]:
            return user
        else:
            return None
            
    except Exception as e:
        print(f"Authentication error: {e}")
        return None
    finally:
        conn.close()

# --- Create Test Users Function ---
def create_test_users():
    test_users = [
        ("admin", hash_password("admin123"), "admin", "All Schools"),
        ("school1", hash_password("school123"), "school", "Greenwood High"),
        ("public1", hash_password("public123"), "public", "")
    ]
    
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    
    for user in test_users:
        try:
            c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?)", user)
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    conn.close()

# --- Visual Tree Growth Display ---
def display_tree_growth(height_m, max_height=30):
    growth_percentage = min((height_m / max_height) * 100, 100)
    
    st.markdown(f"""
    <div class="tree-visualization">
        <div style="font-size: 3rem; color: #2e8b57;">{'🌱' if height_m < 1 else '🌳' if height_m < 5 else '🌲'}</div>
        <div style="font-weight: bold; margin: 0.5rem 0;">Height: {height_m} meters</div>
        <div class="progress-container">
            <div class="progress-bar" style="width: {growth_percentage}%"></div>
        </div>
        <div style="display: flex; justify-content: space-between; margin-top: 0.5rem;">
            <span>0m</span>
            <span>{max_height}m</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Login Page ---
def login():
    st.markdown("<h1 class='header-text'>🌳 Tree Growth Tracker</h1>", unsafe_allow_html=True)
    st.markdown("""
    <div class="card">
        <h3>Track, Monitor, and Celebrate Your Trees</h3>
        <p>Join our community in growing a greener future, one tree at a time.</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("🔧 Troubleshooting Tools", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Reset Database"):
                initialize_data_files()
                st.success("Database reset! Default admin: admin/admin123")
        
        with col2:
            if st.button("Create Test Users"):
                create_test_users()
                st.success("Created test users: admin/admin123, school1/school123, public1/public123")
        
        if st.button("Show All Users"):
            conn = sqlite3.connect(SQLITE_DB)
            users = pd.read_sql("SELECT username, user_type, school FROM users", conn)
            conn.close()
            st.dataframe(users)

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.form_submit_button("Login"):
            if not username or not password:
                st.warning("Please enter both username and password")
                return
                
            user = authenticate(username, password)
            
            if user:
                st.session_state.user = {
                    "username": user[0],
                    "user_type": user[2],
                    "school": user[3]
                }
                st.success(f"Welcome {user[0]}!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Invalid username or password")
                if username == "admin":
                    st.info("Default admin password is 'admin123'")

# --- Admin Dashboard with Tree Adoption and User Management ---
def admin_dashboard():
    st.markdown("<h1 class='header-text'>🌳 Administrator Dashboard</h1>", unsafe_allow_html=True)
    
    # Add Logout Button
    if st.sidebar.button("Logout"):
        del st.session_state.user
        st.success("Logged out successfully!")
        time.sleep(1)
        st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["🌿 Manage Trees", "👥 Manage Users", "📊 Analytics"])
    
    # --- Manage Trees ---
    with tab1:
        st.subheader("All Trees")
        trees = load_tree_data()
        st.dataframe(trees)
        
        st.subheader("Add/Edit Tree")
        with st.form("admin_tree_form"):
            col1, col2 = st.columns(2)
            with col1:
                tree_id = st.text_input("Tree ID*").strip()
            
            if tree_id:
                tree_data = trees[trees['tree_id'] == tree_id]
                
                if not tree_data.empty:
                    tree = tree_data.iloc[0]
                    school = tree['school']
                    student = tree['student_name']
                    species = tree['species']
                    importance = tree['importance'] if 'importance' in tree else "Not provided"
                    
                    st.text_input("School Name", value=school, disabled=True)
                    st.text_input("Student Name", value=student, disabled=True)
                    
                    scientific_name = st.text_input("Scientific Name", value=species)  
                    importance = st.text_area("Importance", value=importance)
                    
                    county = tree.get('county', '')
                    sub_county = tree.get('sub_county', '')
                    ward = tree.get('ward', '')
                    
                    st.text_input("County", value=county, disabled=True)
                    st.text_input("Sub-County", value=sub_county, disabled=True)
                    st.text_input("Ward", value=ward, disabled=True)

                else:
                    st.error("Tree ID not found. Please make sure the ID is correct.")
            
            if st.form_submit_button("Save Tree"):
                if tree_id and scientific_name:
                    trees.loc[trees['tree_id'] == tree_id, ['species', 'importance']] = [scientific_name, importance]
                    if save_tree_data(trees):
                        st.success(f"Tree {tree_id} details updated successfully!")
                        st.rerun()

    # --- Manage Users ---
    with tab2:
        st.subheader("User Management")
        
        conn = sqlite3.connect(SQLITE_DB)
        users = pd.read_sql("SELECT username, user_type, school FROM users", conn)
        conn.close()
        st.dataframe(users)
        
        st.subheader("Add New User")
        with st.form("add_user_form"):
            username = st.text_input("Username*").strip()
            password = st.text_input("Password*", type="password").strip()
            user_type = st.selectbox("User Type", list(USER_TYPES.keys()))
            school = st.text_input("School (for school users)").strip()
            
            if st.form_submit_button("Add User"):
                if username and password:
                    try:
                        conn = sqlite3.connect(SQLITE_DB)
                        c = conn.cursor()
                        c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", 
                                 (username, hash_password(password), user_type, school))
                        conn.commit()
                        conn.close()
                        st.success("User added successfully!")
                    except sqlite3.IntegrityError:
                        st.error("Username already exists")
        
        st.subheader("Remove User")
        username_to_remove = st.selectbox("Select a user to remove", users["username"].values)
        
        if st.button("Remove Selected User"):
            try:
                conn = sqlite3.connect(SQLITE_DB)
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE username = ?", (username_to_remove,))
                conn.commit()
                conn.close()
                st.success(f"User {username_to_remove} removed successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error removing user: {e}")

    # --- Analytics Dashboard ---
    with tab3:
        st.subheader("Analytics Dashboard")
        trees = load_tree_data()
        
        # Metrics in cards
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            <div class="card">
                <h3>🌳 Total Trees</h3>
                <h2>{len(trees)}</h2>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div class="card">
                <h3>💚 Alive Trees</h3>
                <h2>{len(trees[trees["status"] == "Alive"])}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="card">
                <h3>🌍 CO₂ Sequestered</h3>
                <h2>{round(trees["co2_kg"].sum(), 2)} kg</h2>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div class="card">
                <h3>💀 Dead Trees</h3>
                <h2>{len(trees[trees["status"] == "Dead"])}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        st.subheader("CO₂ Sequestration by School")
        co2_by_school = trees.groupby("school")["co2_kg"].sum().reset_index()
        fig = px.bar(co2_by_school, x="school", y="co2_kg", 
                     title="CO₂ Sequestration by School",
                     color="co2_kg",
                     color_continuous_scale="Greens")
        st.plotly_chart(fig)
        
        st.subheader("Tree Status Distribution")
        status_counts = trees["status"].value_counts().reset_index()
        fig = px.pie(status_counts, values="count", names="status", 
                     title="Tree Status Distribution",
                     color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig)

# --- Donor "Adopt a Tree" Section ---
def get_location():
    geolocator = Nominatim(user_agent="tree_monitoring_app")
    try:
        location = geolocator.geocode("Kenya")  # Example location
        if location:
            return {"latitude": location.latitude, "longitude": location.longitude}
        else:
            raise Exception("Location could not be fetched")
    except Exception as e:
        raise Exception(f"Location detection failed: {str(e)}")

def donor_dashboard():
    st.markdown("<h1 class='header-text'>🌳 Adopt a Tree</h1>", unsafe_allow_html=True)
    
    # Add Logout Button
    if st.sidebar.button("Logout"):
        del st.session_state.user
        st.success("Logged out successfully!")
        time.sleep(1)
        st.rerun()
    
    st.markdown("""
    <div class="card">
        <h3>Make a Difference by Adopting a Tree</h3>
        <p>Your adoption helps schools maintain and monitor their trees while contributing to a greener planet.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.subheader("Select a School to Adopt a Tree")
    trees = load_tree_data()
    schools = trees["school"].unique()
    selected_school = st.selectbox("Select School", schools)
    
    if selected_school:
        school_trees = trees[trees["school"] == selected_school]
        
        # School metrics in cards
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class="card">
                <h4>Total Trees</h4>
                <h3>{len(school_trees)}</h3>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="card">
                <h4>Alive Trees</h4>
                <h3>{len(school_trees[school_trees["status"] == "Alive"])}</h3>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="card">
                <h4>CO₂ Sequestered</h4>
                <h3>{round(school_trees["co2_kg"].sum(), 2)} kg</h3>
            </div>
            """, unsafe_allow_html=True)
        
        adopt_tree = st.selectbox("Select Tree to Adopt", school_trees[school_trees["status"] == "Alive"]['tree_id'])
        
        if adopt_tree:
            tree_data = school_trees[school_trees["tree_id"] == adopt_tree].iloc[0]
            
            # Display tree visualization
            display_tree_growth(tree_data["height_m"])
            
            st.write(f"**Species:** {tree_data['species']}")
            st.write(f"**Planted by:** {tree_data['student_name']}")
            st.write(f"**Planted on:** {tree_data['date_planted']}")
            st.write(f"**CO₂ Sequestered:** {tree_data['co2_kg']} kg")
            
            donor_name = st.text_input("Enter Your Name to Adopt the Tree")
            
            if st.button("Adopt Tree") and donor_name:
                trees.loc[trees["tree_id"] == adopt_tree, "status"] = "Adopted"
                trees.loc[trees["tree_id"] == adopt_tree, "adopter_name"] = donor_name
                save_tree_data(trees)
                st.success(f"Thank you, {donor_name}, for adopting Tree {adopt_tree} at {selected_school}!")
                st.balloons()
            elif not donor_name:
                st.error("Please enter your name to adopt the tree.")

    # --- Find Nearby Trees ---
    st.subheader("Find Nearby Trees")

    if st.button("📡 Detect My Location"):
        try:
            loc = get_location()
            st.session_state.public_lat = loc['latitude']
            st.session_state.public_lon = loc['longitude']
            st.success(f"Location detected! Lat: {loc['latitude']:.6f}, Lon: {loc['longitude']:.6f}")
        except Exception as e:
            st.error(f"Location detection failed: {str(e)}")

    if 'public_lat' in st.session_state and 'public_lon' in st.session_state:
        lat = st.session_state.public_lat
        lon = st.session_state.public_lon

        radius = st.slider("Search radius (meters)", 1, 100, 3)
        
        if st.button(f"🔍 Find Nearby Trees ({radius}m radius)"):
            nearby_trees = []
            trees = load_tree_data()

            for _, tree in trees.iterrows():
                try:
                    if pd.isna(tree["latitude"]) or pd.isna(tree["longitude"]):
                        continue
                    dist = geodesic((lat, lon), (tree["latitude"], tree["longitude"])).meters
                    if dist <= radius:
                        nearby_trees.append({**tree.to_dict(), "distance_m": round(dist, 2)})
                except:
                    continue
            
            if nearby_trees:
                st.success(f"Found {len(nearby_trees)} nearby trees:")
                for tree in nearby_trees:
                    with st.expander(f"{tree['tree_id']} - {tree['distance_m']:.1f}m away"):
                        display_tree_growth(tree["height_m"])
                        st.write(f"**School:** {tree['school']}")
                        st.write(f"**Species:** {tree['species']}")
                        st.write(f"**Planted by:** {tree['student_name']}")
                        st.write(f"**Planted on:** {tree['date_planted']}")
                        st.write(f"**Status:** {tree['status']}")
                        st.write(f"**CO₂ Sequestered:** {tree['co2_kg']} kg")
                        
                        with st.form(f"update_form_{tree['tree_id']}"):
                            new_status = st.selectbox("Status", ["Alive", "Dead"], index=0 if tree['status'] == "Alive" else 1)
                            new_height = st.number_input("Tree Height (m)", value=tree["height_m"], min_value=0.1)
                            new_rcd = st.number_input("Root Collar Diameter (cm)", value=tree["rcd_cm"] if tree["tree_stage"] == "Young (RCD)" else 0.1)
                            new_dbh = st.number_input("Diameter at Breast Height (cm)", 
                                                  value=float(tree["dbh_cm"]) if pd.notna(tree["dbh_cm"]) else 0.1)
                            
                            if st.form_submit_button(f"Update Tree {tree['tree_id']}"):
                                trees.loc[trees['tree_id'] == tree['tree_id'], ['status', 'height_m', 'rcd_cm', 'dbh_cm']] = [new_status, new_height, new_rcd, new_dbh]
                                save_tree_data(trees)
                                st.success(f"Tree {tree['tree_id']} updated successfully!")

            else:
                st.info(f"No trees found within {radius} meters. Try increasing the search radius.")
        else:
            st.info("Click the '📡 Detect My Location' button to detect your location first.")
    else:
        st.info("Please detect your location using the '📡 Detect My Location' button.")

# --- School Dashboard ---
def school_dashboard(school_name: str):
    st.markdown(f"<h1 class='header-text'>🌳 {school_name} Dashboard</h1>", unsafe_allow_html=True)
    
    # Add Logout Button
    if st.sidebar.button("Logout"):
        del st.session_state.user
        st.success("Logged out successfully!")
        time.sleep(1)
        st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["🌿 My Trees", "🌱 Plant New Tree", "📊 School Analytics"])
    
    # --- My Trees ---
    with tab1:
        st.subheader("Our Trees")
        trees = load_tree_data()
        school_trees = trees[trees["school"].str.lower() == school_name.lower()]
        st.dataframe(school_trees)
        
        st.subheader("Monitor Tree")
        tree_id = st.text_input("Enter Tree ID to Monitor").strip()
        
        if tree_id and tree_id in school_trees["tree_id"].values:
            tree = school_trees[school_trees["tree_id"] == tree_id].iloc[0].to_dict()
            
            # Display tree visualization
            display_tree_growth(tree["height_m"])
            
            with st.form(f"monitor_form_{tree_id}"):
                st.write(f"**Species:** {tree['species']}")
                st.write(f"**Planted by:** {tree['student_name']}")
                st.write(f"**Planted on:** {tree['date_planted']}")

                status = st.selectbox(
                    "Status", 
                    ["Alive", "Dead"], 
                    index=0 if tree.get('status', "Alive") == "Alive" else 1
                )

                if status == "Alive":
                    tree_stage = st.radio(
                        "Tree Stage", 
                        ["Young (RCD)", "Mature (DBH)"], 
                        index=0 if tree.get('tree_stage', "Young (RCD)") == "Young (RCD)" else 1
                    )

                    if tree_stage == "Young (RCD)":
                        rcd = st.number_input(
                            "Root Collar Diameter (cm)", 
                            min_value=0.1, 
                            value=float(tree.get('rcd_cm', 0.1)),
                            step=0.1
                        )
                        dbh = None
                    else:
                        dbh = st.number_input(
                            "Diameter at Breast Height (cm)", 
                            min_value=0.1, 
                            value=float(tree.get('dbh_cm', 0.1)) if pd.notna(tree.get('dbh_cm')) else 0.1,
                            step=0.1
                        )
                        rcd = None

                    height = st.number_input(
                        "Height (meters)", 
                        min_value=0.1, 
                        value=float(tree.get('height_m', 0.1)),
                        step=0.1
                    )

                    co2 = calculate_co2(tree['species'], rcd=rcd, dbh=dbh)
                    st.metric("CO₂ Sequestered (kg)", f"{co2}")

                if st.form_submit_button("Update Tree"):
                    idx = trees[trees["tree_id"] == tree['tree_id']].index
                    
                    update_data = {
                        "tree_stage": tree_stage if status == "Alive" else tree['tree_stage'],
                        "rcd_cm": rcd if (status == "Alive" and tree_stage == "Young (RCD)") else tree['rcd_cm'],
                        "dbh_cm": dbh if (status == "Alive" and tree_stage == "Mature (DBH)") else tree['dbh_cm'],
                        "height_m": height if status == "Alive" else tree['height_m'],
                        "co2_kg": co2 if status == "Alive" else tree['co2_kg'],
                        "status": status
                    }
                    
                    trees.loc[idx, list(update_data.keys())] = list(update_data.values())
                    
                    if save_tree_data(trees):
                        st.success("Tree updated successfully!")
                        st.rerun()

    # --- Plant New Tree ---
    with tab2:
        st.subheader("Plant New Tree")
        
        if st.button("📡 Detect My Location"):
            try:
                loc = get_location()
                st.session_state.school_lat = loc['latitude']
                st.session_state.school_lon = loc['longitude']
                st.success(f"Location detected! Lat: {loc['latitude']:.6f}, Lon: {loc['longitude']:.6f}")
            except Exception as e:
                st.error(f"Location detection failed: {str(e)}")
        
        with st.form("school_new_tree_form"):
            student = st.text_input("Student Name*").strip()
            species = st.selectbox("Species*", DEFAULT_SPECIES)
            date_planted = st.date_input("Planting Date", datetime.date.today())
            
            if 'school_lat' in st.session_state and 'school_lon' in st.session_state:
                lat = st.session_state.school_lat
                lon = st.session_state.school_lon
            else:
                lat = None
                lon = None
            
            county = st.text_input("County*")
            sub_county = st.text_input("Sub-County*")
            ward = st.text_input("Ward*")
            
            if st.form_submit_button("🌱 Plant Tree"):
                if student and county and sub_county and ward and lat and lon:
                    trees = load_tree_data()
                    tree_id = generate_tree_id(school_name)
                    new_tree = {
                        "tree_id": tree_id,
                        "school": school_name,
                        "species": species,
                        "student_name": student,
                        "date_planted": str(date_planted),
                        "tree_stage": "Young (RCD)",
                        "rcd_cm": 0.1,
                        "dbh_cm": None,
                        "height_m": 0.5,
                        "latitude": lat,
                        "longitude": lon,
                        "co2_kg": 0.0,
                        "status": "Alive",
                        "county": county,
                        "sub_county": sub_county,
                        "ward": ward
                    }
                    
                    updated_trees = pd.concat([trees, pd.DataFrame([new_tree])], ignore_index=True)
                    if save_tree_data(updated_trees):
                        st.success(f"Tree {tree_id} planted successfully!")
                        st.balloons()
                else:
                    st.error("Please fill all the required fields including location.")

    # --- School Analytics ---
    with tab3:
        st.subheader("School Analytics")
        trees = load_tree_data()
        school_trees = trees[trees["school"].str.lower() == school_name.lower()]
        
        # Metrics in cards
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            <div class="card">
                <h3>🌳 Total Trees</h3>
                <h2>{len(school_trees)}</h2>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div class="card">
                <h3>💚 Alive Trees</h3>
                <h2>{len(school_trees[school_trees["status"] == "Alive"])}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="card">
                <h3>🌍 CO₂ Sequestered</h3>
                <h2>{round(school_trees["co2_kg"].sum(), 2)} kg</h2>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div class="card">
                <h3>💀 Dead Trees</h3>
                <h2>{len(school_trees[school_trees["status"] == "Dead"])}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        st.subheader("Tree Growth Over Time")
        school_trees["date_planted"] = pd.to_datetime(school_trees["date_planted"])
        timeline = school_trees.groupby("date_planted").size().cumsum().reset_index()
        timeline.columns = ["Date", "Total Trees"]
        fig = px.line(timeline, x="Date", y="Total Trees", 
                      title="Tree Planting Timeline",
                      line_shape="spline",
                      color_discrete_sequence=["#2e8b57"])
        st.plotly_chart(fig)
        
        # Tree height distribution
        st.subheader("Tree Height Distribution")
        fig = px.histogram(school_trees, x="height_m", 
                          title="Distribution of Tree Heights",
                          color_discrete_sequence=["#4CAF50"],
                          nbins=20)
        st.plotly_chart(fig)

# --- Main Application ---
def main():
    load_css()  # Load custom CSS
    initialize_data_files()
    
    if "user" not in st.session_state:
        login()
    else:
        user_type = st.session_state.user["user_type"]
        
        if user_type == "admin":
            admin_dashboard()
        elif user_type == "school":
            school_dashboard(st.session_state.user["school"])
        elif user_type == "public":
            donor_dashboard()

if __name__ == "__main__":
    main()
