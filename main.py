import os
import struct
import urllib
from datetime import datetime
import pytz

from flask import Flask, request, flash, redirect, url_for, render_template, jsonify
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user
from sqlalchemy import create_engine, event, Column, Integer, String, ForeignKey, select, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError
import re

# Flask aplikace
app = Flask(__name__)
CORS(app, resources={r"/upload": {"origins": "*"}})

CONFIG_SECRET = os.environ.get("CONFIG_SECRET")

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
server_name = "phototrack-server.database.windows.net"
database_name = "PhotoTrackDB"
driver_name = "ODBC Driver 18 for SQL Server"

# 🔹 Vytvoření connection stringu
connection_string = f"Driver={driver_name};Server=tcp:{server_name},1433;Database={database_name};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30"

# 🔹 Přidání tokenu pro Azure Managed Identity (Entra ID)
credential = DefaultAzureCredential()

def get_token():
    """ Získání autentizačního tokenu pro přístup k Azure SQL """
    try:
        token_bytes = credential.get_token("https://database.windows.net/.default").token.encode("UTF-16-LE")
        return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    except Exception as e:
        print(f"❌ Chyba při získávání tokenu: {e}")
        return None

# 🔹 Vytvoření SQLAlchemy engine
params = urllib.parse.quote_plus(connection_string)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

# 🔹 Přidání ověřovacího tokenu k připojení
@event.listens_for(engine, "do_connect")
def provide_token(dialect, conn_rec, cargs, cparams):
    SQL_COPT_SS_ACCESS_TOKEN = 1256  # Definováno Microsoftem
    token = get_token()
    if token:
        cparams["attrs_before"] = {SQL_COPT_SS_ACCESS_TOKEN: token}

# 🔹 Inicializace session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 🔹 Deklarativní základ pro SQLAlchemy modely
Base = declarative_base()

# 🔹 Inicializace Flask-Login
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "your_secret_key")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# 🔹 Modely databáze
class User(UserMixin, Base):
    __tablename__ = "User"
    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)

class Configuration(Base):
    __tablename__ = "Configuration"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("User.id"), nullable=False)
    wakeUp_time = Column(String(50), nullable=False)
    send_photo = Column(String(50), nullable=False)
    photo_resolution = Column(String(50), nullable=False)
    photo_quality = Column(String(50), nullable=False)
    phone_number = Column(String(20), nullable=True)

class CameraActions(Base):
    __tablename__ = "CameraActions"
    id = Column(Integer, primary_key=True)
    send_sms = Column(Boolean, default=False)
    phone_number = Column(String(20), nullable=True)
    take_photo = Column(Boolean, default=False)
    reset_trailCamera = Column(Boolean, default=False)


# 🔹 Funkce pro načtení uživatele
@login_manager.user_loader
def load_user(user_id):
    with SessionLocal() as session:
        return session.get(User, int(user_id))

# 🔹 API endpoint pro načtení konfigurace
@app.route("/get_configuration", methods=["GET"])
def get_configuration():
    token = request.headers.get("X-Api-Key")
    if token != CONFIG_SECRET:
        return jsonify({"error": "Unauthorized"}), 403  # Neoprávněný přístup

    with SessionLocal() as session:
        config = session.query(Configuration).filter_by(user_id=1).first()
        if not config:
            return jsonify({"message": "No update"}), 200

        response_data = {
            "wakeUp_time": config.wakeUp_time,
            "send_photo": config.send_photo,
            "photo_resolution": config.photo_resolution,
            "photo_quality": config.photo_quality,
            "phone_number": config.phone_number,
        }

        # Odstraníme konfiguraci z SQL
        session.delete(config)
        session.commit()

        return jsonify(response_data), 200  # Vrátíme konfiguraci

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
            config.send_photo = data.get("send_photo", "0")
            config.photo_resolution = data.get("photo_resolution", "1024x768")
            config.photo_quality = data.get("photo_quality", "High")
            config.phone_number = data.get("phone_number", "+420735009345")
            session.commit()
        return jsonify({"message": "Configuration saved successfully"}), 200
    except Exception as e:
        print(f"❌ Chyba při ukládání konfigurace: {e}")
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
                #flash("Successfully logged in", "Success")
                return redirect(url_for('PhotoTrackCalendar'))
            else:
                flash("Invalid username or password", "danger")
    return render_template("login.html")

# Upload obrázku a metadat
@app.route('/upload', methods=['POST'])
def upload_photo():
    token = request.headers.get("X-Api-Key")
    if token != CONFIG_SECRET:
        return jsonify({"error": "Unauthorized"}), 403  # Neoprávněný přístup

    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    # Přidání časové značky k názvu souboru a přípony .jpg
    jpgExtension = ".jpg"
    czech_tz = pytz.timezone("Europe/Prague")
    now_czech = datetime.now(czech_tz)

    timestamp = now_czech.strftime('%Y%m%d%H%M%S')
    new_filename = f"{timestamp}_{file.filename}{jpgExtension}"

    # Metadata z požadavku
    battery_level = request.form.get('battery_level', 'Unknown')
    charging_status = request.form.get('charging_status', 'Unknown')
    time_to_dead = request.form.get('time_to_dead', 'Unknown')
    date_taken = now_czech.strftime('%Y-%m-%dT%H:%M:%S')

    # Nahrání souboru do Azure Blob Storage
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=new_filename)
    blob_client.upload_blob(file.read(), overwrite=False, metadata={
        "date_taken": date_taken,
        "battery_level": battery_level,
        "charging_status": charging_status,
        "time_to_dead": time_to_dead
    })
    return "File and metadata uploaded successfully", 200

# Načítání fotografií a metadat
@app.route('/get_events', methods=['GET'])
@login_required
def get_events():
    events = []
    blobs = container_client.list_blobs()

    for blob in blobs:
        blob_client = container_client.get_blob_client(blob)
        blob_properties = blob_client.get_blob_properties()

        events.append({
            "title": blob.name,
            "start": blob_properties.metadata.get("date_taken", ""),
            "image": blob_client.url,
            "battery_level": blob_properties.metadata.get("battery_level", "Unknown"),
            "charging_status": blob_properties.metadata.get("charging_status", "Unknown"),
            "time_to_dead": blob_properties.metadata.get("time_to_dead", "Unknown")
        })

    return jsonify(events)

@app.route("/send_sms", methods=["POST"])
def send_sms():
    data = request.json
    phone_number = data.get("phone_number", "").strip()

    # ✅ Validace telefonního čísla (musí mít správný formát)
    phone_pattern = re.compile(r"^\+\d{10,15}$")
    if not phone_pattern.match(phone_number):
        return jsonify({"error": "Invalid phone number format. Use +420XXXXXXXXX"}), 400

    with SessionLocal() as session:
        camera_action = session.query(CameraActions).first()
        if not camera_action:
            camera_action = CameraActions()
            session.add(camera_action)

        camera_action.phone_number = phone_number
        camera_action.send_sms = True  # Aktivujeme požadavek na SMS
        session.commit()

    return jsonify({"message": "SMS request saved", "phone_number": phone_number}), 200

@app.route("/take_photo", methods=["POST"])
def take_photo():
    with SessionLocal() as session:
        camera_action = session.query(CameraActions).first()
        if not camera_action:
            camera_action = CameraActions()
            session.add(camera_action)

        camera_action.take_photo = True  # Aktivujeme požadavek na fotku
        session.commit()

    return jsonify({"message": "Photo request saved"}), 200

@app.route("/reset_camera", methods=["POST"])
def reset_camera():
    with SessionLocal() as session:
        camera_action = session.query(CameraActions).first()
        if not camera_action:
            camera_action = CameraActions()
            session.add(camera_action)

        camera_action.reset_trailCamera = True  # Aktivujeme požadavek na reset kamery
        session.commit()

    return jsonify({"message": "Camera reset request saved"}), 200


@app.route("/get_commands", methods=["GET"])
def get_commands():
    token = request.headers.get("X-Api-Key")
    if token != CONFIG_SECRET:
        return jsonify({"error": "Unauthorized"}), 403  # Neoprávněný přístup

    with SessionLocal() as session:
        try:
            command = session.query(CameraActions).filter_by(id=1).first()
            if not command:
                return jsonify({"message": "No update"}), 200

            # ✅ Pokud žádný příkaz není aktivní, vrátíme "No update"
            if not (command.send_sms or command.take_photo or command.reset_trailCamera):
                return jsonify({"message": "No update"}), 200

            response = {
                "send_sms": command.send_sms,
                "phone_number": command.phone_number if command.send_sms else None,
                "take_photo": command.take_photo,
                "reset_trailCamera": command.reset_trailCamera
            }

            # ✅ Po úspěšném přečtení resetujeme hodnoty na False/NULL
            command.send_sms = False
            command.take_photo = False
            command.reset_trailCamera = False
            command.phone_number = None
            session.commit()

            return jsonify(response)

        except Exception as e:
            return jsonify({"error": "Internal server error"}), 500


# Konfigurační stránka
@app.route('/configuration')
@login_required
def configuration():
    return render_template('configuration.html')

# Kalendářová stránka
@app.route('/PhotoTrackCalendar')
@login_required
def PhotoTrackCalendar():
    return render_template('phototrackcalendar.html')

# 🔹 Spuštění aplikace a inicializace databáze
if __name__ == "__main__":
    with engine.begin() as conn:
        Base.metadata.create_all(conn)  # Vytvoření tabulek v Azure SQL
    app.run(host="0.0.0.0", port=5000, debug=True)
