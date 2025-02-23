import os
import struct
import urllib
from datetime import datetime

from flask import Flask, request, flash, redirect, url_for, render_template, jsonify
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user
from sqlalchemy import create_engine, event, Column, Integer, String, ForeignKey, select
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

# Flask aplikace
app = Flask(__name__)
CORS(app, resources={r"/upload": {"origins": "*"}})

# 🔹 Připojení k Azure Blob Storage
blob_connect_str = os.environ.get("AZURE_BLOB_CONNECTION_STRING")
blob_service_client = BlobServiceClient.from_connection_string(blob_connect_str)
container_name = "photos"

# 🔹 Vytvoření kontejneru, pokud neexistuje
container_client = blob_service_client.get_container_client(container_name)
try:
    container_client.create_container()
except ResourceExistsError:
    pass

# 🔹 Nastavení Azure SQL Database připojení
server_name = 'phototrack-server.database.windows.net'
database_name = 'PhotoTrackDB'
driver_name = '{ODBC Driver 18 for SQL Server}'

# 🔹 Vytvoření connection stringu
connection_string = 'Driver={};Server=tcp:{}.database.windows.net,1433;Database={};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30'.format(driver_name, server_name, database_name)

# 🔹 Přidání tokenu pro Azure Managed Identity (Entra ID)
credential = DefaultAzureCredential()

def get_token():
    token_bytes = credential.get_token("https://database.windows.net/.default").token.encode("UTF-16-LE")
    return struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

# 🔹 Vytvoření SQLAlchemy engine
params = urllib.parse.quote_plus(connection_string)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

# 🔹 Přidání ověřovacího tokenu k připojení
@event.listens_for(engine, "do_connect")
def provide_token(dialect, conn_rec, cargs, cparams):
    SQL_COPT_SS_ACCESS_TOKEN = 1256  # Definováno Microsoftem
    cparams["attrs_before"] = {SQL_COPT_SS_ACCESS_TOKEN: get_token()}

# 🔹 Inicializace session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 🔹 Deklarativní základ pro SQLAlchemy modely
Base = declarative_base()

# 🔹 Inicializace Flask-Login
app.config["SECRET_KEY"] = "your_secret_key"
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# 🔹 Modely databáze

class User(UserMixin, Base):
    __tablename__ = "User"  # Odpovídá tabulce v Azure SQL
    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)

class Configuration(Base):
    __tablename__ = "Configuration"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("User.id"), nullable=False)
    wakeUp_time = Column(String(50), nullable=False)
    interval_shots = Column(String(50), nullable=False)
    photo_resolution = Column(String(50), nullable=False)
    photo_quality = Column(String(50), nullable=False)
    phone_number = Column(String(20), nullable=True)

# 🔹 Funkce pro načtení uživatele
@login_manager.user_loader
def load_user(user_id):
    with SessionLocal() as session:
        return session.get(User, int(user_id))

# 🔹 API endpoint pro načtení konfigurace
@app.route("/get_configuration", methods=["GET"])
@login_required
def get_configuration():
    with SessionLocal() as session:
        config = session.query(Configuration).filter_by(user_id=current_user.id).first()
        if not config:
            return jsonify({"message": "No configuration found"}), 404
        return jsonify({
            "wakeUp_time": config.wakeUp_time,
            "interval_shots": config.interval_shots,
            "photo_resolution": config.photo_resolution,
            "photo_quality": config.photo_quality,
            "phone_number": config.phone_number,
        })

# 🔹 API endpoint pro uložení konfigurace
@app.route("/save_configuration", methods=["POST"])
@login_required
def save_configuration():
    try:
        data = request.json
        with SessionLocal() as session:
            config = session.query(Configuration).filter_by(user_id=current_user.id).first()
            if config is None:
                config = Configuration(user_id=current_user.id)
                session.add(config)
            config.wakeUp_time = data.get("wakeUp_time", "60 s")
            config.interval_shots = data.get("interval_shots", "5 s")
            config.photo_resolution = data.get("photo_resolution", "1024x768")
            config.photo_quality = data.get("photo_quality", "High")
            config.phone_number = data.get("phone_number", "+420735009345")
            session.commit()
        return jsonify({"message": "Configuration saved successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Error saving configuration", "details": str(e)}), 500

# 🔹 Přihlašovací stránka
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        with SessionLocal() as session:
            user = session.query(User).filter_by(username=username).first()
            if user and user.password_hash == password:
                login_user(user)
                flash("Successfully logged in", "Success")
                return redirect(url_for("PhotoTrackCalendar"))
            else:
                flash("Invalid username or password", "danger")
    return render_template("login.html")

# 🔹 Spuštění aplikace a inicializace databáze
if __name__ == "__main__":
    with engine.begin() as conn:
        Base.metadata.create_all(conn)  # Vytvoření tabulek v Azure SQL
    app.run(debug=True)
